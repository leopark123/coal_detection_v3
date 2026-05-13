#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
设备级检测Web应用

设备1: 125个格栅口的完整检测系统
"""

import os
import time
from contextlib import asynccontextmanager
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from loguru import logger

# 添加项目路径
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from config.config import Config
from drivers.factory import create_camera
from algo.device_detector import DeviceDetector, DeviceResult
from web.common import (
    apply_mock_source_from_env,
    apply_sample_resolution,
    mount_static_and_templates,
    read_bool_env,
    run_websocket_stream,
    StreamAppState,
)

# 创建应用
@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan hook."""
    await startup()
    try:
        yield
    finally:
        await shutdown()


app = FastAPI(
    title="设备级检测系统",
    description="设备1: 125个格栅口检测",
    lifespan=lifespan
)

# 静态文件和模板
templates = mount_static_and_templates(
    app,
    static_dir=str(PROJECT_ROOT / "web" / "static"),
    templates_dir=str(Path(__file__).parent / "templates"),
    create_dirs=False,
)

class DeviceAppState(StreamAppState):
    """设备级应用状态"""
    def __init__(self):
        super().__init__()
        self.detector: Optional[DeviceDetector] = None
        self.device_id: str = "device-1"

        # 检测统计
        self.device_coal_detections: int = 0
        self.last_result: Optional[DeviceResult] = None

state = DeviceAppState()

async def startup():
    """应用启动"""
    logger.info("[DeviceApp] 启动设备级检测应用")

    state.config = Config()
    state.config.USE_REAL_GRID_IN_DEV = read_bool_env("USE_REAL_GRID_IN_DEV", default=True)
    state.device_id = os.getenv("DEVICE_ID", "device-1").strip() or "device-1"

    apply_mock_source_from_env(state.config, app_tag="[DeviceApp]")
    apply_sample_resolution(state.config, width=462, height=603)

    # 初始化相机和检测器
    try:
        state.camera = create_camera(state.config)
        # 创建设备1检测器（125个格栅口）
        state.detector = DeviceDetector(state.config, device_id=state.device_id, grid_count=125)
        state.is_running = True

        logger.info(f"[DeviceApp] 初始化完成")
        logger.info(f"[DeviceApp] 设备ID: {state.device_id}")
        logger.info(f"[DeviceApp] 格栅口数量: {len(state.detector.device_grids)}")

    except Exception as e:
        logger.error(f"[DeviceApp] 初始化失败: {e}")
        state.is_running = False

async def shutdown():
    """应用关闭"""
    state.stop_runtime(app_tag="[DeviceApp]")
    logger.info("[DeviceApp] 服务已关闭")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """设备检测主页"""
    return templates.TemplateResponse("device_detection.html", {
        "request": request,
        "device_id": state.device_id,
        "total_grids": len(state.detector.device_grids) if state.detector else 0,
        "detection_count": state.detection_count,
        "device_coal_detections": state.device_coal_detections
    })

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 设备级实时检测"""
    def _detect_frame(frame, frame_id):
        return state.detector.detect_device(frame, frame_id)

    def _on_result(result):
        state.detection_count += 1
        if result.device_has_coal:
            state.device_coal_detections += 1
        state.last_result = result

    def _build_history(result, frame_id):
        return {
            "frame_id": frame_id,
            "timestamp": time.time(),
            "device_has_coal": result.device_has_coal,
            "coal_grids": result.coal_grids,
            "coal_percentage": result.coal_percentage,
            "alert_level": result.device_alert_level,
            "process_time": result.process_time_ms,
        }

    def _render_frame(frame, result):
        return state.detector.visualize_device(frame, result)

    def _build_response(result, image_base64):
        return {
            "image": image_base64,
            "result": result.to_dict(),
            "statistics": state.detector.get_device_statistics(),
            "detection_count": state.detection_count,
            "device_coal_detections": state.device_coal_detections,
            "device_coal_rate": (
                state.device_coal_detections / state.detection_count
                if state.detection_count > 0
                else 0.0
            ),
        }

    await run_websocket_stream(
        websocket,
        app_tag="[DeviceApp]",
        state=state,
        detect_frame=_detect_frame,
        on_result=_on_result,
        build_history_entry=_build_history,
        render_frame=_render_frame,
        build_response_data=_build_response,
        jpeg_quality=85,
    )

@app.get("/api/device/statistics")
async def get_device_statistics():
    """获取设备统计信息"""
    if not state.detector:
        return {"error": "设备检测器未初始化"}

    stats = state.detector.get_device_statistics()
    stats.update({
        "current_detection_count": state.detection_count,
        "current_device_coal_detections": state.device_coal_detections,
        "current_device_coal_rate": (state.device_coal_detections / state.detection_count
                                    if state.detection_count > 0 else 0.0),
        "last_result": state.last_result.to_dict() if state.last_result else None
    })

    return stats

@app.get("/api/device/history")
async def get_device_history():
    """获取设备检测历史"""
    return {
        "device_id": state.device_id,
        "total_records": len(state.detection_history),
        "history": state.detection_history[-50:]  # 返回最近50条
    }

@app.get("/api/device/status")
async def get_device_status():
    """获取设备状态"""
    return {
        "device_id": state.device_id,
        "is_running": state.is_running,
        "total_grids": len(state.detector.device_grids) if state.detector else 0,
        "camera_type": type(state.camera).__name__ if state.camera else "未知",
        "detector_type": "DeviceDetector" if state.detector else None,
        "last_alert_level": state.last_result.device_alert_level if state.last_result else "UNKNOWN"
    }

@app.post("/api/device/reset_stats")
async def reset_device_statistics():
    """重置设备统计数据"""
    try:
        state.reset_stream_counters()
        state.device_coal_detections = 0

        # 重置检测器内部统计
        if state.detector:
            state.detector.detection_count = 0
            state.detector.device_coal_detections = 0
            state.detector.avg_process_time = 0.0

        return {"success": True, "message": "统计数据已重置"}
    except Exception as e:
        logger.error(f"[DeviceApp] 重置统计失败: {e}")
        return {"error": f"重置失败: {e}"}

@app.get("/api/device/grid_details")
async def get_grid_details():
    """获取格栅详细状态"""
    if not state.last_result or not state.last_result.grid_details:
        return {"error": "无格栅详细数据"}

    grid_summary = {
        "total_grids": state.last_result.total_grids,
        "visible_grids": state.last_result.visible_grids,
        "coal_grids": state.last_result.coal_grids,
        "grid_states": []
    }

    # 汇总每个格栅的状态
    for i, grid in enumerate(state.last_result.grid_details):
        grid_state = {
            "grid_id": i,
            "x": grid.x,
            "y": grid.y,
            "w": grid.w,
            "h": grid.h,
            "is_visible": grid.is_visible,
            "has_coal": grid.has_coal,
            "visibility_score": grid.visibility_score,
            "coal_coverage": grid.coal_coverage
        }
        grid_summary["grid_states"].append(grid_state)

    return grid_summary
