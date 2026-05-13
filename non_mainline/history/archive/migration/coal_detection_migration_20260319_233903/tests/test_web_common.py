"""
web.common 公共模块测试
"""

import asyncio
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi import WebSocketDisconnect

from web.common import (
    StreamAppState,
    append_bounded,
    apply_mock_source_from_env,
    mount_static_and_templates,
    read_bool_env,
    run_websocket_stream,
)


class _FakeCamera:
    def __init__(self, frames=None, fail_first=False):
        self._frames = frames or [np.zeros((8, 8, 3), dtype=np.uint8)]
        self._idx = 0
        self._fail_first = fail_first
        self.released = False

    def grab(self):
        if self._fail_first:
            self._fail_first = False
            raise RuntimeError("simulated camera error")

        frame = self._frames[self._idx % len(self._frames)]
        self._idx += 1
        return frame

    def release(self):
        self.released = True


class _FakeWebSocket:
    def __init__(self):
        self.accepted = False
        self.sent = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        self.sent.append(data)


def test_append_bounded_keeps_latest():
    history = []
    for i in range(6):
        append_bounded(history, {"i": i}, max_items=3)

    assert len(history) == 3
    assert [x["i"] for x in history] == [3, 4, 5]


def test_stream_app_state_common_runtime_methods():
    state = StreamAppState()
    state.is_running = True
    state.detection_count = 10
    state.detection_history = [{"a": 1}, {"a": 2}]
    state.camera = _FakeCamera()

    state.stop_runtime(app_tag="[Test]")
    assert state.is_running is False
    assert state.camera.released is True

    state.reset_stream_counters()
    assert state.detection_count == 0
    assert state.detection_history == []


def test_apply_mock_source_from_env(monkeypatch):
    cfg = SimpleNamespace(MOCK_SOURCE_DIR="default_path")
    monkeypatch.setenv("MOCK_SOURCE_DIR", "tests/sample_only")

    apply_mock_source_from_env(cfg, app_tag="[Test]")
    assert cfg.MOCK_SOURCE_DIR == "tests/sample_only"


def test_read_bool_env(monkeypatch):
    monkeypatch.setenv("TEST_BOOL_ENV", "true")
    assert read_bool_env("TEST_BOOL_ENV", default=False) is True

    monkeypatch.setenv("TEST_BOOL_ENV", "0")
    assert read_bool_env("TEST_BOOL_ENV", default=True) is False

    monkeypatch.setenv("TEST_BOOL_ENV", "invalid")
    assert read_bool_env("TEST_BOOL_ENV", default=True) is True

    monkeypatch.delenv("TEST_BOOL_ENV", raising=False)
    assert read_bool_env("TEST_BOOL_ENV", default=False) is False


def test_mount_static_and_templates_create_dirs():
    app = FastAPI()
    static_dir = Path("tests/.tmp_static_assets")
    templates_dir = Path("tests/.tmp_templates_assets")

    if static_dir.exists():
        shutil.rmtree(static_dir)
    if templates_dir.exists():
        shutil.rmtree(templates_dir)

    try:
        templates = mount_static_and_templates(
            app,
            static_dir=str(static_dir),
            templates_dir=str(templates_dir),
            create_dirs=True,
        )

        assert static_dir.is_dir()
        assert templates_dir.is_dir()
        assert any(getattr(route, "path", None) == "/static" for route in app.routes)
        assert str(templates_dir) in templates.env.loader.searchpath
    finally:
        if static_dir.exists():
            shutil.rmtree(static_dir)
        if templates_dir.exists():
            shutil.rmtree(templates_dir)


def test_run_websocket_stream_single_cycle():
    ws = _FakeWebSocket()
    state = SimpleNamespace(
        is_running=True,
        detector=object(),
        camera=_FakeCamera(),
        detection_history=[],
        config=SimpleNamespace(frame_interval=0.0),
        detection_count=0,
    )

    def detect_frame(frame, frame_id):
        assert frame.shape == (8, 8, 3)
        return {"frame_id": frame_id, "has_coal": False}

    def on_result(result):
        state.detection_count += 1
        # 单次循环后停止，避免测试长时间运行
        state.is_running = False

    def build_history(result, frame_id):
        return {"fid": frame_id}

    def render_frame(frame, result):
        return frame

    def build_response(result, image_base64):
        return {"image": image_base64, "result": result}

    asyncio.run(
        run_websocket_stream(
            ws,
            app_tag="[Test]",
            state=state,
            detect_frame=detect_frame,
            on_result=on_result,
            build_history_entry=build_history,
            render_frame=render_frame,
            build_response_data=build_response,
            jpeg_quality=80,
        )
    )

    assert ws.accepted is True
    assert state.detection_count == 1
    assert len(state.detection_history) == 1
    assert len(ws.sent) == 1
    assert "image" in ws.sent[0]
    assert "result" in ws.sent[0]


def test_run_websocket_stream_retry_on_capture_error(monkeypatch):
    ws = _FakeWebSocket()
    state = SimpleNamespace(
        is_running=True,
        detector=object(),
        camera=_FakeCamera(fail_first=True),
        detection_history=[],
        config=SimpleNamespace(frame_interval=0.0),
        detection_count=0,
    )

    async def _no_sleep(_):
        return None

    monkeypatch.setattr("web.common.asyncio.sleep", _no_sleep)

    def detect_frame(frame, frame_id):
        return {"frame_id": frame_id}

    def on_result(result):
        state.detection_count += 1
        state.is_running = False

    def render_frame(frame, result):
        return frame

    def build_response(result, image_base64):
        return {"image": image_base64, "result": result}

    asyncio.run(
        run_websocket_stream(
            ws,
            app_tag="[Test]",
            state=state,
            detect_frame=detect_frame,
            on_result=on_result,
            build_history_entry=None,
            render_frame=render_frame,
            build_response_data=build_response,
        )
    )

    assert ws.accepted is True
    assert state.detection_count == 1
    assert len(ws.sent) == 1


def test_run_websocket_stream_handles_disconnect():
    class _DisconnectWebSocket(_FakeWebSocket):
        async def send_json(self, data):
            raise WebSocketDisconnect()

    ws = _DisconnectWebSocket()
    state = SimpleNamespace(
        is_running=True,
        detector=object(),
        camera=_FakeCamera(),
        detection_history=[],
        config=SimpleNamespace(frame_interval=0.0),
        detection_count=0,
    )

    def detect_frame(frame, frame_id):
        return {"frame_id": frame_id}

    def on_result(result):
        state.detection_count += 1

    def render_frame(frame, result):
        return frame

    def build_response(result, image_base64):
        return {"image": image_base64, "result": result}

    # 不应抛异常，断开连接被内部捕获
    asyncio.run(
        run_websocket_stream(
            ws,
            app_tag="[Test]",
            state=state,
            detect_frame=detect_frame,
            on_result=on_result,
            build_history_entry=None,
            render_frame=render_frame,
            build_response_data=build_response,
        )
    )

    assert ws.accepted is True


def test_run_websocket_stream_skips_when_not_ready():
    ws = _FakeWebSocket()
    state = SimpleNamespace(
        is_running=True,
        detector=None,
        camera=None,
        detection_history=[],
        config=SimpleNamespace(frame_interval=0.0),
        detection_count=0,
    )

    def detect_frame(frame, frame_id):
        return {"frame_id": frame_id}

    def on_result(result):
        state.detection_count += 1

    def render_frame(frame, result):
        return frame

    def build_response(result, image_base64):
        return {"image": image_base64, "result": result}

    asyncio.run(
        run_websocket_stream(
            ws,
            app_tag="[Test]",
            state=state,
            detect_frame=detect_frame,
            on_result=on_result,
            build_history_entry=None,
            render_frame=render_frame,
            build_response_data=build_response,
        )
    )

    assert ws.accepted is True
    assert state.detection_count == 0
    assert len(ws.sent) == 0
