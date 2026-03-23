#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
单格栅检测Web应用

阶段1专用：单格栅检测验证和参数调优
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
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config
from drivers.factory import create_camera
from algo.single_grid_detector import SingleGridDetector, SingleGridResult
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
    title="单格栅检测系统",
    description="阶段1: 单格栅检测验证",
    lifespan=lifespan
)

# 静态文件和模板
templates = mount_static_and_templates(app)

class SingleGridAppState(StreamAppState):
    """单格栅应用状态"""
    def __init__(self):
        super().__init__()
        self.detector: Optional[SingleGridDetector] = None
        self.target_grid_id: int = 0

        # 检测统计
        self.coal_detections: int = 0
        self.last_result: Optional[SingleGridResult] = None

state = SingleGridAppState()

async def startup():
    """应用启动"""
    logger.info("[SingleGridApp] 启动单格栅检测应用")

    state.config = Config()
    state.config.USE_REAL_GRID_IN_DEV = read_bool_env("USE_REAL_GRID_IN_DEV", default=True)

    apply_mock_source_from_env(state.config, app_tag="[SingleGridApp]")

    # 获取目标格栅ID
    try:
        state.target_grid_id = int(os.getenv('TARGET_GRID_ID', '0'))
    except ValueError:
        state.target_grid_id = 0

    apply_sample_resolution(state.config, width=462, height=603)

    # 初始化相机和检测器
    try:
        state.camera = create_camera(state.config)
        state.detector = SingleGridDetector(state.config, state.target_grid_id)
        state.is_running = True

        logger.info(f"[SingleGridApp] 初始化完成")
        logger.info(f"[SingleGridApp] 目标格栅ID: {state.target_grid_id}")
        logger.info(f"[SingleGridApp] 总格栅数量: {state.detector.original_grid_count}")

    except Exception as e:
        logger.error(f"[SingleGridApp] 初始化失败: {e}")
        state.is_running = False

async def shutdown():
    """应用关闭"""
    state.stop_runtime(app_tag="[SingleGridApp]")
    logger.info("[SingleGridApp] 服务已关闭")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """单格栅检测主页"""
    return templates.TemplateResponse("single_grid.html", {
        "request": request,
        "grid_id": state.target_grid_id,
        "total_grids": state.detector.original_grid_count if state.detector else 0,
        "detection_count": state.detection_count,
        "coal_detections": state.coal_detections
    })

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 实时检测"""
    def _detect_frame(frame, frame_id):
        return state.detector.detect_single_grid(frame, frame_id)

    def _on_result(result):
        state.detection_count += 1
        if result.has_coal:
            state.coal_detections += 1
        state.last_result = result

    def _build_history(result, frame_id):
        return {
            "frame_id": frame_id,
            "timestamp": time.time(),
            "has_coal": result.has_coal,
            "confidence": result.confidence,
            "process_time": result.process_time_ms,
        }

    def _render_frame(frame, result):
        return state.detector.visualize_single_grid(frame, result)

    def _build_response(result, image_base64):
        return {
            "image": image_base64,
            "result": result.to_dict(),
            "statistics": state.detector.get_statistics(),
            "detection_count": state.detection_count,
            "coal_detections": state.coal_detections,
            "coal_rate": (
                state.coal_detections / state.detection_count
                if state.detection_count > 0
                else 0.0
            ),
        }

    await run_websocket_stream(
        websocket,
        app_tag="[SingleGridApp]",
        state=state,
        detect_frame=_detect_frame,
        on_result=_on_result,
        build_history_entry=_build_history,
        render_frame=_render_frame,
        build_response_data=_build_response,
        jpeg_quality=85,
    )

@app.get("/api/statistics")
async def get_statistics():
    """获取检测统计信息"""
    if not state.detector:
        return {"error": "检测器未初始化"}

    stats = state.detector.get_statistics()
    stats.update({
        "current_detection_count": state.detection_count,
        "current_coal_detections": state.coal_detections,
        "current_coal_rate": (state.coal_detections / state.detection_count
                             if state.detection_count > 0 else 0.0),
        "last_result": state.last_result.to_dict() if state.last_result else None
    })

    return stats

@app.get("/api/history")
async def get_detection_history():
    """获取检测历史"""
    return {
        "total_records": len(state.detection_history),
        "history": state.detection_history[-50:]  # 返回最近50条
    }

@app.get("/api/grid/switch/{grid_id}")
async def switch_grid(grid_id: int):
    """切换目标格栅"""
    if not state.detector:
        return {"error": "检测器未初始化"}

    try:
        # 创建新的检测器
        new_detector = SingleGridDetector(state.config, grid_id)

        # 更新状态
        state.detector = new_detector
        state.target_grid_id = grid_id

        # 重置统计
        state.reset_stream_counters()
        state.coal_detections = 0

        logger.info(f"[SingleGridApp] 已切换到格栅ID: {grid_id}")

        return {
            "success": True,
            "grid_id": grid_id,
            "message": f"已切换到格栅 {grid_id}"
        }

    except Exception as e:
        logger.error(f"[SingleGridApp] 切换格栅失败: {e}")
        return {"error": f"切换失败: {e}"}

@app.post("/api/save_logs")
async def save_detection_logs():
    """保存检测日志"""
    if not state.detector or not state.last_result:
        return {"error": "无数据可保存"}

    try:
        state.detector.save_detection_log(state.last_result)
        return {"success": True, "message": "日志已保存"}
    except Exception as e:
        logger.error(f"[SingleGridApp] 保存日志失败: {e}")
        return {"error": f"保存失败: {e}"}

@app.get("/api/status")
async def get_status():
    """获取系统状态"""
    return {
        "is_running": state.is_running,
        "target_grid_id": state.target_grid_id,
        "total_grids": state.detector.original_grid_count if state.detector else 0,
        "camera_type": type(state.camera).__name__ if state.camera else "未知",
        "detector_type": "SingleGridDetector" if state.detector else None
    }
