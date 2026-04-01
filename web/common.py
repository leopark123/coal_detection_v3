"""
Shared helpers for web applications.
"""

import asyncio
import base64
import os
import gc
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, MutableSequence

import cv2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger

# WebSocket 发送超时（秒）：客户端接收慢时丢弃帧而非堆积
_WS_SEND_TIMEOUT = 5.0
# 内存监控间隔（帧数）
_MEM_CHECK_INTERVAL = 500

# 独立线程池：camera.grab 和 detect_frame 各自独立，互不阻塞
_grab_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="grab")
_detect_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="detect")
# run_in_executor 超时（秒）：防止线程池被永久阻塞的任务耗尽
_EXECUTOR_TIMEOUT = 10.0


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
    cam_connected = camera and getattr(camera, "is_connected", False)
    if not (cam_connected and detector and config):
        reason = "相机未连接" if not cam_connected else "检测器/配置缺失"
        logger.warning(f"{app_tag} 推流条件不满足({reason})")
        try:
            await websocket.send_json({"error": reason, "retry_after": 60})
        except Exception:
            pass
        return

    loop = asyncio.get_event_loop()
    # 是否使用线程池（测试时可通过 state._use_sync = True 跳过）
    use_sync = getattr(state, "_use_sync", False)
    frame_id = 0
    try:
        while (
            state.is_running
            and getattr(state, "camera", None)
            and getattr(state, "detector", None)
            and getattr(state, "config", None)
        ):
            try:
                if use_sync:
                    frame = state.camera.grab()
                else:
                    # 独立 grab 线程池 + 超时保护
                    frame = await asyncio.wait_for(
                        loop.run_in_executor(_grab_executor, state.camera.grab),
                        timeout=_EXECUTOR_TIMEOUT,
                    )
            except asyncio.TimeoutError:
                logger.warning(f"{app_tag} 相机 grab 超时({_EXECUTOR_TIMEOUT}s)，跳过")
                await asyncio.sleep(1)
                continue
            except Exception as e:
                now = loop.time()
                last_err = getattr(state, '_last_grab_err_log', 0)
                if now - last_err > 30:
                    logger.error(f"{app_tag} 采集失败: {e}")
                    state._last_grab_err_log = now
                grab_fails = getattr(state, '_grab_fail_count', 0) + 1
                state._grab_fail_count = grab_fails
                if grab_fails >= 30:
                    logger.error(f"{app_tag} 相机连续{grab_fails}次采集失败，停止推流")
                    break
                await asyncio.sleep(3)
                continue
            state._grab_fail_count = 0

            try:
                if use_sync:
                    result = detect_frame(frame, frame_id)
                else:
                    # 独立 detect 线程池 + 超时保护
                    result = await asyncio.wait_for(
                        loop.run_in_executor(_detect_executor, detect_frame, frame, frame_id),
                        timeout=_EXECUTOR_TIMEOUT,
                    )
            except asyncio.TimeoutError:
                logger.warning(f"{app_tag} 检测超时({_EXECUTOR_TIMEOUT}s)，跳过帧 #{frame_id}")
                result = None
            on_result(result)

            if result is not None:
                # 正常检测帧（在采集窗口内）
                if build_history_entry is not None:
                    history_entry = build_history_entry(result, frame_id)
                    if history_entry is not None:
                        append_bounded(state.detection_history, history_entry, max_items=100)

                vis_frame = render_frame(frame, result)
                image_base64 = encode_frame_jpeg_base64(vis_frame, quality=jpeg_quality)
                try:
                    await asyncio.wait_for(
                        websocket.send_json(build_response_data(result, image_base64)),
                        timeout=_WS_SEND_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"{app_tag} WebSocket 发送超时，丢弃帧 #{frame_id}")
                frame_id += 1
            else:
                # 窗口外：低频推送原始画面（每2秒一帧，而非每帧都推）
                idle_counter = getattr(state, '_idle_frame_counter', 0) + 1
                state._idle_frame_counter = idle_counter
                idle_interval = max(1, int(2.0 / max(state.config.frame_interval, 0.05)))
                if idle_counter % idle_interval == 0:
                    image_base64 = encode_frame_jpeg_base64(frame, quality=40)
                    cap_status = {}
                    cc = getattr(state, 'capture_controller', None)
                    if cc:
                        cap_status = {
                            "capture_phase": cc.phase.value,
                            "capture_phase_display": cc.phase_display,
                            "window_remaining": round(cc.window_remaining, 1),
                        }
                    try:
                        await asyncio.wait_for(
                            websocket.send_json({
                                "image": image_base64,
                                "idle": True,
                                **cap_status,
                            }),
                            timeout=_WS_SEND_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"{app_tag} WebSocket idle 发送超时，跳过")

            await asyncio.sleep(state.config.frame_interval)

            # 定期内存检查（每 _MEM_CHECK_INTERVAL 帧）
            if frame_id > 0 and frame_id % _MEM_CHECK_INTERVAL == 0:
                gc.collect()
                try:
                    import psutil
                    proc = psutil.Process()
                    mem_mb = proc.memory_info().rss / 1024 / 1024
                    if mem_mb > 1024:
                        logger.warning(f"{app_tag} 内存偏高: {mem_mb:.0f}MB")
                    else:
                        logger.debug(f"{app_tag} 内存: {mem_mb:.0f}MB (帧#{frame_id})")
                except ImportError:
                    pass  # psutil 未安装，跳过

    except WebSocketDisconnect:
        logger.info(f"{app_tag} WebSocket客户端已断开")
    except Exception as e:
        logger.error(f"{app_tag} WebSocket错误: {e}")
