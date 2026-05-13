"""
Shared helpers for web applications.
"""

import asyncio
import base64
import os
from pathlib import Path
from typing import Any, Callable, MutableSequence

import cv2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger


def mount_static_and_templates(
    app: FastAPI,
    static_dir: str = "web/static",
    templates_dir: str = "web/templates",
    create_dirs: bool = True,
) -> Jinja2Templates:
    """Mount static resources and return Jinja templates."""
    mount_static(app, static_dir=static_dir, create_dirs=create_dirs)
    if create_dirs:
        Path(templates_dir).mkdir(parents=True, exist_ok=True)
    return Jinja2Templates(directory=templates_dir)


def mount_static(
    app: FastAPI,
    static_dir: str = "web/static",
    create_dirs: bool = True,
) -> None:
    """Mount static resources."""
    if create_dirs:
        Path(static_dir).mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


def apply_mock_source_from_env(
    config,
    *,
    app_tag: str,
    env_key: str = "MOCK_SOURCE_DIR",
    log_when_missing: bool = False,
) -> None:
    """Apply mock source directory from environment."""
    mock_source = os.getenv(env_key)
    if mock_source:
        config.MOCK_SOURCE_DIR = mock_source
        logger.info(f"{app_tag} 使用指定图片目录: {mock_source}")
    elif log_when_missing:
        logger.warning(f"{app_tag} 未找到{env_key}环境变量，使用默认: {config.MOCK_SOURCE_DIR}")


def read_bool_env(env_key: str, default: bool = False) -> bool:
    """Read boolean-like environment variable with a safe fallback."""
    raw_value = os.getenv(env_key)
    if raw_value is None:
        return default

    value = raw_value.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def apply_sample_resolution(config, width: int = 462, height: int = 603) -> None:
    """Apply sample image resolution used in dev validation."""
    config.DEV_FRAME_WIDTH = width
    config.DEV_FRAME_HEIGHT = height


def encode_frame_jpeg_base64(frame, quality: int = 85) -> str:
    """Encode frame to base64 JPEG string."""
    ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return base64.b64encode(buffer).decode("utf-8")


def append_bounded(history: MutableSequence[Any], item: Any, max_items: int = 100) -> None:
    """Append item and keep only latest max_items records."""
    history.append(item)
    if len(history) > max_items:
        del history[:-max_items]


def release_camera_safely(camera, *, app_tag: str) -> None:
    """Release camera resource without raising."""
    if not camera:
        return
    try:
        camera.release()
    except Exception as e:
        logger.warning(f"{app_tag} 相机释放失败: {e}")


class StreamAppState:
    """Base state for realtime stream apps."""

    def __init__(self):
        self.config = None
        self.camera = None
        self.is_running = False
        self.detection_count = 0
        self.detection_history = []

    def stop_runtime(self, *, app_tag: str) -> None:
        """Stop runtime and release camera safely."""
        self.is_running = False
        release_camera_safely(self.camera, app_tag=app_tag)

    def reset_stream_counters(self) -> None:
        """Reset common stream counters."""
        self.detection_count = 0
        self.detection_history.clear()


async def run_websocket_stream(
    websocket: WebSocket,
    *,
    app_tag: str,
    state: Any,
    detect_frame: Callable[[Any, int], Any],
    on_result: Callable[[Any], None],
    build_history_entry: Callable[[Any, int], Any] | None,
    render_frame: Callable[[Any, Any], Any],
    build_response_data: Callable[[Any, str], dict],
    jpeg_quality: int = 85,
) -> None:
    """Run shared realtime websocket loop for stream apps."""
    await websocket.accept()
    logger.info(f"{app_tag} WebSocket客户端已连接")

    camera = getattr(state, "camera", None)
    detector = getattr(state, "detector", None)
    config = getattr(state, "config", None)
    if not (state.is_running and camera and detector and config):
        logger.warning(f"{app_tag} WebSocket启动条件不满足，已跳过推流")
        return

    frame_id = 0
    try:
        while (
            state.is_running
            and getattr(state, "camera", None)
            and getattr(state, "detector", None)
            and getattr(state, "config", None)
        ):
            try:
                frame = state.camera.grab()
            except Exception as e:
                logger.error(f"{app_tag} 采集失败: {e}")
                await asyncio.sleep(1)
                continue

            result = detect_frame(frame, frame_id)
            on_result(result)

            if build_history_entry is not None:
                history_entry = build_history_entry(result, frame_id)
                if history_entry is not None:
                    append_bounded(state.detection_history, history_entry, max_items=100)

            vis_frame = render_frame(frame, result)
            image_base64 = encode_frame_jpeg_base64(vis_frame, quality=jpeg_quality)

            await websocket.send_json(build_response_data(result, image_base64))

            frame_id += 1
            await asyncio.sleep(state.config.frame_interval)

    except WebSocketDisconnect:
        logger.info(f"{app_tag} WebSocket客户端已断开")
    except Exception as e:
        logger.error(f"{app_tag} WebSocket错误: {e}")
