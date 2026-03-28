"""
翻车机积煤检测系统 V3.0 - 统一 Web 应用

替代原有 3 个独立 app，支持多翻车机多漏斗。

启动方式：
    python -m uvicorn web.unified_app:app --host 0.0.0.0 --port 8080
"""

import os
import sys
import time
import asyncio
import atexit
import signal
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from loguru import logger

# 项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config
from config.devices_config import DevicesConfig
from web.common import (
    StreamAppState,
    run_websocket_stream,
    mount_static_and_templates,
    append_bounded,
    encode_frame_jpeg_base64,
)
from web.state_manager import StateManager
from web.admin_api import create_admin_router, verify_admin

# 确保 loguru 输出到 stderr（uvicorn 可见）
logger.remove()
logger.add(sys.stderr, level="DEBUG")

# ═══════════════════════════════════════════════════════════════
# 全局状态
# ═══════════════════════════════════════════════════════════════
state_manager = StateManager()

DEVICES_YAML = os.getenv(
    "DEVICES_YAML",
    str(Path(__file__).parent.parent / "config" / "devices.yaml"),
)


# ═══════════════════════════════════════════════════════════════
# FastAPI Lifespan
# ═══════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("[UnifiedApp] 启动中...")

    # 加载基础配置
    base_config = Config()

    # 加载多机拓扑
    yaml_path = DEVICES_YAML
    if not Path(yaml_path).exists():
        logger.error(f"[UnifiedApp] 设备配置文件不存在: {yaml_path}")
        yield
        return

    devices_config = DevicesConfig.from_yaml(yaml_path)
    logger.info(
        f"[UnifiedApp] 加载配置: {len(devices_config.machines)} 台翻车机"
    )

    # 初始化所有硬件
    state_manager.initialize(devices_config, base_config, yaml_path=yaml_path)

    # 注册 atexit 确保崩溃时也释放硬件
    def _emergency_shutdown():
        logger.warning("[UnifiedApp] atexit: 紧急释放硬件资源")
        try:
            state_manager.shutdown()
        except Exception:
            pass
    atexit.register(_emergency_shutdown)

    yield

    # 关闭
    logger.info("[UnifiedApp] 关闭中...")
    state_manager.shutdown()


# ═══════════════════════════════════════════════════════════════
# FastAPI App
# ═══════════════════════════════════════════════════════════════
app = FastAPI(title="翻车机积煤检测系统", lifespan=lifespan)
templates = mount_static_and_templates(app)

# 挂载管理员 API
app.include_router(create_admin_router(state_manager))


# ═══════════════════════════════════════════════════════════════
# 页面路由
# ═══════════════════════════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
async def overview_page(request: Request):
    """总览页"""
    return templates.TemplateResponse("overview.html", {"request": request})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """管理员设置页"""
    return templates.TemplateResponse("settings.html", {"request": request})


@app.get("/machine/{machine_id}", response_class=HTMLResponse)
async def machine_detail_page(request: Request, machine_id: str):
    """翻车机详情页"""
    ms = state_manager.get_machine_state(machine_id)
    if not ms:
        return HTMLResponse(content="翻车机不存在", status_code=404)

    mc = ms.machine_config
    funnels_data = []
    for fc in mc.funnels:
        funnels_data.append({"id": fc.id, "name": fc.name})

    return templates.TemplateResponse("machine_detail.html", {
        "request": request,
        "machine_id": machine_id,
        "machine_name": mc.name,
        "plc_ip": mc.plc_ip,
        "funnels": funnels_data,
    })


@app.get("/machine/{machine_id}/funnel/{funnel_id}", response_class=HTMLResponse)
async def funnel_detail_page(request: Request, machine_id: str, funnel_id: str):
    """漏斗详情页"""
    fs = state_manager.get_funnel_state(machine_id, funnel_id)
    if not fs:
        return HTMLResponse(content="漏斗不存在", status_code=404)

    ms = state_manager.get_machine_state(machine_id)
    mc = ms.machine_config
    fc = next((f for f in mc.funnels if f.id == funnel_id), None)

    return templates.TemplateResponse("funnel_detail.html", {
        "request": request,
        "machine_id": machine_id,
        "machine_name": mc.name,
        "funnel_id": funnel_id,
        "funnel_name": fc.name if fc else funnel_id,
        "grid_count": fc.grid_count if fc else 0,
    })


# ═══════════════════════════════════════════════════════════════
# WebSocket 路由
# ═══════════════════════════════════════════════════════════════
@app.websocket("/ws/overview")
async def overview_ws(websocket: WebSocket):
    """总览状态推送（2s 间隔，无视频）"""
    await websocket.accept()
    logger.info("[UnifiedApp] 总览 WebSocket 已连接")
    try:
        while True:
            data = state_manager.get_overview_data()
            await websocket.send_json({"machines": data})
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        logger.info("[UnifiedApp] 总览 WebSocket 已断开")
    except Exception as e:
        logger.error(f"[UnifiedApp] 总览 WebSocket 错误: {e}")


@app.websocket("/ws/funnel/{machine_id}/{funnel_id}")
async def funnel_ws(websocket: WebSocket, machine_id: str, funnel_id: str):
    """单漏斗视频流（复用 run_websocket_stream）"""
    fs = state_manager.get_funnel_state(machine_id, funnel_id)
    if not fs:
        await websocket.close(code=4004)
        return

    app_tag = f"[{machine_id}/{funnel_id}]"

    def _detect_frame(frame, frame_id):
        # 视觉停用时不检测
        if not fs.vision_enabled:
            return None
        # 驱动窗口状态机，必须由 PLC 触发才采集
        cc = fs.capture_controller
        if cc:
            cc.tick()
            if not cc.should_capture():
                return None
        else:
            # 没有采集控制器 = 不采集
            return None
        return fs.detector.detect_device(frame, frame_id)

    def _on_result(result):
        if result is None:
            return  # 窗口外跳过
        fs.detection_count += 1
        if getattr(result, "device_has_coal", False):
            fs.coal_detections += 1
        fs.last_result = result

        # 喂入窗口控制器
        cc = fs.capture_controller
        if cc and cc.should_capture():
            cc.feed_result({
                "has_coal": getattr(result, "device_has_coal", False),
                "coal_grids": getattr(result, "coal_grids", 0),
                "alert_level": getattr(result, "device_alert_level", "UNKNOWN"),
                "fault_code": getattr(result, "fault_code", 0),
            })

    def _build_history(result, frame_id):
        return {
            "frame_id": frame_id,
            "timestamp": time.time(),
            "device_has_coal": getattr(result, "device_has_coal", False),
            "coal_grids": getattr(result, "coal_grids", 0),
            "coal_percentage": getattr(result, "coal_percentage", 0.0),
            "alert_level": getattr(result, "device_alert_level", "UNKNOWN"),
            "process_time": getattr(result, "process_time_ms", 0.0),
        }

    def _render_frame(frame, result):
        if hasattr(fs.detector, "visualize_device"):
            return fs.detector.visualize_device(frame, result)
        return frame

    def _build_response(result, image_base64):
        resp = {
            "image": image_base64,
            "detection_count": fs.detection_count,
            "coal_detections": fs.coal_detections,
        }
        if hasattr(result, "to_dict"):
            resp["result"] = result.to_dict()
        if hasattr(fs.detector, "get_device_statistics"):
            resp["statistics"] = fs.detector.get_device_statistics()
        return resp

    await run_websocket_stream(
        websocket,
        app_tag=app_tag,
        state=fs,
        detect_frame=_detect_frame,
        on_result=_on_result,
        build_history_entry=_build_history,
        render_frame=_render_frame,
        build_response_data=_build_response,
    )


# ═══════════════════════════════════════════════════════════════
# REST API
# ═══════════════════════════════════════════════════════════════
@app.get("/api/overview")
async def api_overview():
    """全局状态概览"""
    return {"machines": state_manager.get_overview_data()}


@app.get("/api/machine/{machine_id}/status")
async def api_machine_status(machine_id: str):
    """翻车机状态"""
    ms = state_manager.get_machine_state(machine_id)
    if not ms:
        return JSONResponse({"error": "翻车机不存在"}, status_code=404)

    return {
        "machine_id": machine_id,
        "name": ms.machine_config.name,
        "plc_ip": ms.machine_config.plc_ip,
        "plc_connected": ms.plc_connected,
        "alert_level": ms.worst_alert_level,
        "funnel_count": len(ms.funnels),
        "is_any_alarm": ms.is_any_alarm,
    }


@app.get("/api/machine/{machine_id}/funnel/{funnel_id}/status")
async def api_funnel_status(machine_id: str, funnel_id: str):
    """漏斗状态"""
    fs = state_manager.get_funnel_state(machine_id, funnel_id)
    if not fs:
        return JSONResponse({"error": "漏斗不存在"}, status_code=404)

    return {
        "machine_id": machine_id,
        "funnel_id": funnel_id,
        "is_running": fs.is_running,
        "detection_count": fs.detection_count,
        "coal_detections": fs.coal_detections,
    }


@app.get("/api/machine/{machine_id}/funnel/{funnel_id}/statistics")
async def api_funnel_statistics(machine_id: str, funnel_id: str):
    """漏斗检测统计"""
    fs = state_manager.get_funnel_state(machine_id, funnel_id)
    if not fs:
        return JSONResponse({"error": "漏斗不存在"}, status_code=404)

    stats = {}
    if fs.detector and hasattr(fs.detector, "get_device_statistics"):
        stats = fs.detector.get_device_statistics()

    stats.update({
        "detection_count": fs.detection_count,
        "coal_detections": fs.coal_detections,
        "coal_rate": fs.coal_detections / max(fs.detection_count, 1),
    })
    return stats


@app.get("/api/machine/{machine_id}/funnel/{funnel_id}/history")
async def api_funnel_history(machine_id: str, funnel_id: str):
    """漏斗检测历史"""
    fs = state_manager.get_funnel_state(machine_id, funnel_id)
    if not fs:
        return JSONResponse({"error": "漏斗不存在"}, status_code=404)

    return {
        "total_records": len(fs.detection_history),
        "history": fs.detection_history[-50:],
    }


@app.post("/api/machine/{machine_id}/vision/enable")
async def api_vision_enable(machine_id: str, _=Depends(verify_admin)):
    """启用视觉采集（需管理员鉴权）"""
    try:
        result = state_manager.set_vision_enabled(machine_id, True)
        return result
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


@app.post("/api/machine/{machine_id}/vision/disable")
async def api_vision_disable(machine_id: str, _=Depends(verify_admin)):
    """停用视觉采集（PLC 侧 Allow_Tip 强制=1，需管理员鉴权）"""
    try:
        result = state_manager.set_vision_enabled(machine_id, False)
        return result
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


@app.get("/api/machine/{machine_id}/vision/status")
async def api_vision_status(machine_id: str):
    """获取视觉采集状态"""
    ms = state_manager.get_machine_state(machine_id)
    if not ms:
        return JSONResponse({"error": "翻车机不存在"}, status_code=404)
    return {
        "machine_id": machine_id,
        "vision_enabled": state_manager.get_vision_enabled(machine_id),
    }


@app.get("/api/machine/{machine_id}/funnel/{funnel_id}/capture_status")
async def api_capture_status(machine_id: str, funnel_id: str):
    """获取漏斗的窗口采集状态"""
    fs = state_manager.get_funnel_state(machine_id, funnel_id)
    if not fs:
        return JSONResponse({"error": "漏斗不存在"}, status_code=404)
    if not fs.capture_controller:
        return {"error": "窗口采集未初始化"}
    return fs.capture_controller.get_status()


@app.post("/api/machine/{machine_id}/funnel/{funnel_id}/capture_config")
async def api_update_capture_config(request: Request, machine_id: str, funnel_id: str):
    """更新漏斗的窗口采集参数"""
    fs = state_manager.get_funnel_state(machine_id, funnel_id)
    if not fs:
        return JSONResponse({"error": "漏斗不存在"}, status_code=404)
    if not fs.capture_controller:
        return JSONResponse({"error": "窗口采集未初始化"}, status_code=400)

    body = await request.json()
    allowed = {"cycle_interval_s", "window_duration_s", "pre_delay_s", "vote_threshold"}
    params = {k: float(v) for k, v in body.items() if k in allowed}
    fs.capture_controller.update_config(**params)
    return {"status": "ok", "updated": params}


@app.post("/api/machine/{machine_id}/funnel/{funnel_id}/reset_stats")
async def api_funnel_reset_stats(machine_id: str, funnel_id: str):
    """重置漏斗统计"""
    fs = state_manager.get_funnel_state(machine_id, funnel_id)
    if not fs:
        return JSONResponse({"error": "漏斗不存在"}, status_code=404)

    fs.reset_stream_counters()
    fs.coal_detections = 0
    if fs.detector and hasattr(fs.detector, "reset_statistics"):
        fs.detector.reset_statistics()

    return {"status": "ok", "message": "统计已重置"}
