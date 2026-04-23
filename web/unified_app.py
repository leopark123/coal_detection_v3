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
from fastapi.responses import HTMLResponse, JSONResponse, Response
from loguru import logger

# 项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config
from config.devices_config import DevicesConfig
from web.common import (
    StreamAppState,
    mount_static_and_templates,
    append_bounded,
    encode_frame_jpeg_base64,
)
from web.state_manager import StateManager
from web.admin_api import create_admin_router, verify_admin

# 日志配置：stderr（uvicorn 可见）+ 文件（崩溃后可追溯）
logger.remove()
logger.add(sys.stderr, level="DEBUG")
logger.add(
    str(Path(__file__).parent.parent / "logs" / "unified_{time:YYYY-MM-DD}.log"),
    rotation="00:00",    # 每天零点切割
    retention="30 days", # 保留 30 天
    level="INFO",
    encoding="utf-8",
)

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

    # 启动后台检测 worker（独立于 WebSocket，确保无人看页面时也能检测）
    state_manager.start_background_workers()

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
            try:
                await asyncio.wait_for(
                    websocket.send_json({"machines": data}),
                    timeout=5.0,
                )
            except asyncio.TimeoutError:
                logger.warning("[UnifiedApp] 总览 WebSocket 发送超时")
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        logger.info("[UnifiedApp] 总览 WebSocket 已断开")
    except Exception as e:
        logger.error(f"[UnifiedApp] 总览 WebSocket 错误: {e}")


@app.websocket("/ws/funnel/{machine_id}/{funnel_id}")
async def funnel_ws(websocket: WebSocket, machine_id: str, funnel_id: str):
    """
    单漏斗视频流（纯展示模式）

    检测由后台 worker 驱动，WebSocket 只负责：
    1. 读取后台 worker 产出的 last_frame 和 last_result
    2. 渲染叠加层并推送给浏览器
    不抓帧、不检测、不驱动状态机。
    """
    from web.common import encode_frame_jpeg_base64

    fs = state_manager.get_funnel_state(machine_id, funnel_id)
    if not fs:
        await websocket.close(code=4004)
        return

    app_tag = f"[{machine_id}/{funnel_id}]"
    await websocket.accept()
    logger.info(f"{app_tag} WebSocket 展示流已连接")

    last_seen_id = 0
    try:
        while True:
            frame = fs.last_frame
            result = fs.last_result
            current_id = fs._last_result_id

            if frame is not None:
                is_new = result is not None and current_id != last_seen_id
                if is_new:
                    last_seen_id = current_id

                # 始终用最新的 result 做叠加（窗口外保持上次的检测框）
                vis = frame
                if result is not None and fs.detector and hasattr(fs.detector, "visualize_device"):
                    try:
                        vis = fs.detector.visualize_device(frame, result)
                    except Exception:
                        vis = frame

                quality = 85 if is_new else 50
                img_b64 = encode_frame_jpeg_base64(vis, quality=quality)

                resp = {
                    "image": img_b64,
                    "detection_count": fs.detection_count,
                    "coal_detections": fs.coal_detections,
                }
                if result is not None and hasattr(result, "to_dict"):
                    resp["result"] = result.to_dict()
                if fs.detector and hasattr(fs.detector, "get_device_statistics"):
                    resp["statistics"] = fs.detector.get_device_statistics()
                cc = fs.capture_controller
                if cc:
                    resp["capture_phase"] = cc.phase.value
                if not is_new:
                    resp["idle"] = True

                try:
                    await asyncio.wait_for(
                        websocket.send_json(resp), timeout=5.0
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"{app_tag} WebSocket 发送超时")

            await asyncio.sleep(0.2)  # 5 FPS 展示帧率

    except WebSocketDisconnect:
        logger.info(f"{app_tag} WebSocket 展示流已断开")
    except asyncio.TimeoutError:
        logger.warning(f"{app_tag} WebSocket 发送超时")
    except Exception as e:
        logger.error(f"{app_tag} WebSocket 错误: {e}")


# ═══════════════════════════════════════════════════════════════
# REST API
# ═══════════════════════════════════════════════════════════════
_app_start_time = time.time()


@app.get("/api/health")
async def api_health():
    """系统健康检查（用于外部监控/负载均衡）"""
    import gc
    uptime = time.time() - _app_start_time

    health = {
        "status": "ok",
        "uptime_s": round(uptime),
        "uptime_h": round(uptime / 3600, 1),
        "machines": len(state_manager.machines),
    }

    # 内存
    try:
        import psutil
        proc = psutil.Process()
        mem = proc.memory_info()
        health["rss_mb"] = round(mem.rss / 1024 / 1024, 1)
        health["threads"] = proc.num_threads()
        health["cpu_percent"] = proc.cpu_percent(interval=0.1)
    except ImportError:
        pass

    # PLC 状态（区分未初始化和已断连）
    plc_missing = []   # 创建失败，plc=None
    plc_disconnected = []  # 创建成功但断连
    for mid, ms in state_manager.machines.items():
        if not ms.plc:
            plc_missing.append(mid)
        elif not ms.plc_connected:
            plc_disconnected.append(mid)
    if plc_missing:
        health["plc_not_initialized"] = plc_missing
        health["status"] = "degraded"
    if plc_disconnected:
        health["plc_disconnected"] = plc_disconnected
        health["status"] = "degraded"

    # 相机状态（区分未初始化和已断连）
    cam_missing = []
    cam_disconnected = []
    for mid, ms in state_manager.machines.items():
        for fid, fs in ms.funnels.items():
            if not fs.camera:
                cam_missing.append(f"{mid}/{fid}")
            elif not getattr(fs.camera, 'is_connected', False):
                cam_disconnected.append(f"{mid}/{fid}")
    if cam_missing:
        health["camera_not_initialized"] = cam_missing
        health["status"] = "degraded"
    if cam_disconnected:
        health["camera_disconnected"] = cam_disconnected
        health["status"] = "degraded"

    # GC 统计
    gc_stats = gc.get_stats()
    health["gc_collections"] = sum(s.get('collections', 0) for s in gc_stats)

    return health


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


@app.get("/api/faults/all")
async def api_all_faults():
    """全局故障详情（所有翻车机+系统状态+事件日志）"""
    return state_manager.get_all_faults()


@app.get("/api/archive/stats")
async def api_archive_stats():
    """
    归档模块运行统计（worker 队列 + janitor 磁盘水位）

    返回字段：
      - enabled: 归档是否启用
      - worker: {queue_depth, total_saved, alarm_saved, io_errors, p95_save_ms, ...}
      - janitor: {retention_days, disk_usage_pct, total_cleaned_by_date, ...}
    """
    worker = getattr(state_manager, "archive_worker", None)
    janitor = getattr(state_manager, "archive_janitor", None)

    if worker is None:
        return {
            "enabled": False,
            "reason": "归档未启用或启动失败（检查 archive_enable 配置与目录可写性）",
        }

    return {
        "enabled": True,
        "worker": worker.get_stats(),
        "janitor": janitor.get_stats() if janitor is not None else {"enabled": False},
    }


@app.get("/api/machine/{machine_id}/faults")
async def api_machine_faults(machine_id: str):
    """翻车机及其漏斗的故障详情"""
    ms = state_manager.get_machine_state(machine_id)
    if not ms:
        return JSONResponse({"error": "翻车机不存在"}, status_code=404)

    faults = []
    # PLC 故障
    if not ms.plc_connected:
        plc_err = ms.fault_info.get("plc", {}).get("error", "连接断开")
        plc_since = ms.fault_info.get("plc", {}).get("since")
        faults.append({
            "type": "plc", "device": ms.machine_config.name,
            "message": f"PLC 离线: {plc_err or '连接断开'}",
            "since": plc_since,
        })

    # 漏斗故障
    for fid, fs in ms.funnels.items():
        fc = next((f for f in ms.machine_config.funnels if f.id == fid), None)
        fname = fc.name if fc else fid
        cam_info = fs.fault_info.get("camera", {})
        if cam_info.get("status") == "disconnected":
            faults.append({
                "type": "camera", "device": fname,
                "message": f"相机断开: {cam_info.get('error', '未知')}",
                "since": cam_info.get("since"),
                "reconnect_attempts": cam_info.get("reconnect_attempts", 0),
            })

    return {"machine_id": machine_id, "faults": faults, "fault_count": len(faults)}


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


@app.get("/api/machine/{machine_id}/funnel/{funnel_id}/snapshot")
async def api_snapshot(machine_id: str, funnel_id: str):
    """漏斗最新帧快照（JPEG，用于总览页缩略图）"""
    import cv2
    fs = state_manager.get_funnel_state(machine_id, funnel_id)
    if not fs or fs.last_frame is None:
        return Response(status_code=204)
    try:
        _, buf = cv2.imencode('.jpg', fs.last_frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
        return Response(content=buf.tobytes(), media_type="image/jpeg")
    except Exception:
        return Response(status_code=204)


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
        if "error" in result:
            return JSONResponse(result, status_code=503)
        return result
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


@app.post("/api/machine/{machine_id}/vision/disable")
async def api_vision_disable(machine_id: str, _=Depends(verify_admin)):
    """停用视觉采集（PLC 侧 Allow_Tip 强制=1，需管理员鉴权）"""
    try:
        result = state_manager.set_vision_enabled(machine_id, False)
        if "error" in result:
            return JSONResponse(result, status_code=503)
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
async def api_update_capture_config(request: Request, machine_id: str, funnel_id: str, _=Depends(verify_admin)):
    """更新漏斗的窗口采集参数"""
    fs = state_manager.get_funnel_state(machine_id, funnel_id)
    if not fs:
        return JSONResponse({"error": "漏斗不存在"}, status_code=404)
    if not fs.capture_controller:
        return JSONResponse({"error": "窗口采集未初始化"}, status_code=400)

    body = await request.json()
    # 采集时长由 PLC 控制，服务器侧只能调投票阈值
    allowed = {"vote_threshold"}
    try:
        params = {k: float(v) for k, v in body.items() if k in allowed}
    except (ValueError, TypeError) as e:
        return JSONResponse({"error": f"参数格式错误: {e}"}, status_code=400)
    # 校验
    vt = params.get("vote_threshold")
    if vt is not None and not (0.0 < vt <= 1.0):
        return JSONResponse({"error": f"vote_threshold={vt} 必须在 (0, 1] 之间"}, status_code=400)
    fs.capture_controller.update_config(**params)
    return {"status": "ok", "updated": params}


@app.post("/api/machine/{machine_id}/funnel/{funnel_id}/reset_stats")
async def api_funnel_reset_stats(machine_id: str, funnel_id: str, _=Depends(verify_admin)):
    """重置漏斗统计"""
    fs = state_manager.get_funnel_state(machine_id, funnel_id)
    if not fs:
        return JSONResponse({"error": "漏斗不存在"}, status_code=404)

    fs.reset_stream_counters()
    fs.coal_detections = 0
    if fs.detector and hasattr(fs.detector, "reset_statistics"):
        fs.detector.reset_statistics()

    return {"status": "ok", "message": "统计已重置"}
