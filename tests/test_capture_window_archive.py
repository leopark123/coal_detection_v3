"""
CaptureWindowController 归档相关改造测试

覆盖：
1. feed_result 向后兼容（旧签名 frame=None）
2. 选帧策略：报警窗口 → 第一个 has_coal
3. 选帧策略：正常窗口 → 中间帧
4. 选帧策略：故障窗口 → 第一个故障
5. archive_worker=None 时不出错
6. 所有帧无 frame_ref 时跳过归档
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from core.capture_window import (
    CaptureWindowController,
    CaptureWindowConfig,
    CapturePhase,
    WindowResult,
)


def _make_controller(archive_worker=None, funnel_tag="m1_f1"):
    cfg = CaptureWindowConfig(
        window_duration_s=1.0,
        vote_threshold=0.6,
        poll_interval_s=0.05,
    )
    cc = CaptureWindowController(
        cfg,
        plc=None,
        archive_worker=archive_worker,
        funnel_tag=funnel_tag,
    )
    return cc


def _frame(tag=0):
    # 用 tag 让每张帧内容可辨（左上角像素）
    img = np.zeros((60, 80, 3), dtype=np.uint8)
    img[0, 0] = (tag, tag, tag)
    return img


def test_feed_result_backward_compatible():
    """旧签名（无 frame）应仍工作"""
    cc = _make_controller()
    cc._phase = CapturePhase.CAPTURING
    cc.feed_result({"has_coal": True, "coal_grids": 5, "fault_code": 0})
    assert len(cc._frame_results) == 1
    assert cc._frame_results[0]["frame_ref"] is None


def test_feed_result_with_frame():
    cc = _make_controller()
    cc._phase = CapturePhase.CAPTURING
    img = _frame(7)
    cc.feed_result({"has_coal": True, "fault_code": 0}, frame=img)
    assert cc._frame_results[0]["frame_ref"] is img


def test_select_representative_alarm_first_has_coal():
    cc = _make_controller()
    frames = [
        {"has_coal": False, "fault_code": 0, "frame_ref": _frame(1), "timestamp": 1},
        {"has_coal": False, "fault_code": 0, "frame_ref": _frame(2), "timestamp": 2},
        {"has_coal": True,  "fault_code": 0, "frame_ref": _frame(3), "timestamp": 3},
        {"has_coal": True,  "fault_code": 0, "frame_ref": _frame(4), "timestamp": 4},
    ]
    result = WindowResult(is_alarm=True, fault_code=0)
    frame, meta = cc._select_representative_frame(frames, result)
    # 第一个有煤帧是 tag=3
    assert frame[0, 0, 0] == 3
    assert meta["reason"] == "first_alarm"


def test_select_representative_normal_middle():
    cc = _make_controller()
    frames = [
        {"has_coal": False, "fault_code": 0, "frame_ref": _frame(i), "timestamp": i}
        for i in range(5)
    ]
    result = WindowResult(is_alarm=False, fault_code=0)
    frame, meta = cc._select_representative_frame(frames, result)
    # 5 帧中间 = index 2 = tag 2
    assert frame[0, 0, 0] == 2
    assert meta["reason"] == "middle"


def test_select_representative_fault_first():
    cc = _make_controller()
    frames = [
        {"has_coal": False, "fault_code": 0, "frame_ref": _frame(1), "timestamp": 1},
        {"has_coal": False, "fault_code": 3, "frame_ref": _frame(2), "timestamp": 2},
        {"has_coal": False, "fault_code": 3, "frame_ref": _frame(3), "timestamp": 3},
    ]
    result = WindowResult(is_alarm=False, fault_code=3)
    frame, meta = cc._select_representative_frame(frames, result)
    assert frame[0, 0, 0] == 2
    assert meta["reason"] == "first_fault"


def test_select_representative_no_frame_ref():
    cc = _make_controller()
    frames = [
        {"has_coal": True, "fault_code": 0, "frame_ref": None, "timestamp": 1},
    ]
    result = WindowResult(is_alarm=True, fault_code=0)
    frame, meta = cc._select_representative_frame(frames, result)
    assert frame is None
    assert meta == {}


def test_select_representative_alarm_but_no_has_coal_fallback():
    """is_alarm=True 但所有帧 has_coal=False（理论上不该发生），fallback 取第一张"""
    cc = _make_controller()
    frames = [
        {"has_coal": False, "fault_code": 0, "frame_ref": _frame(10), "timestamp": 1},
        {"has_coal": False, "fault_code": 0, "frame_ref": _frame(11), "timestamp": 2},
    ]
    result = WindowResult(is_alarm=True, fault_code=0)
    frame, meta = cc._select_representative_frame(frames, result)
    assert frame[0, 0, 0] == 10
    assert meta["reason"] == "fallback_first"


def test_enqueue_archive_calls_worker():
    worker = MagicMock()
    cc = _make_controller(archive_worker=worker, funnel_tag="machine-1_funnel-1")
    frames = [
        {"has_coal": True, "fault_code": 0, "frame_ref": _frame(5),
         "timestamp": time.time(), "coal_grids": 3},
    ]
    result = WindowResult(
        is_alarm=True,
        fault_code=0,
        confidence="HIGH",
        total_frames=1,
        alarm_frames=1,
        alarm_ratio=1.0,
        coal_grids_avg=3,
        window_end=time.time(),
    )
    cc._enqueue_archive(frames, result)
    worker.enqueue.assert_called_once()
    args, kwargs = worker.enqueue.call_args
    assert kwargs["is_alarm"] is True
    md = kwargs["metadata"]
    assert md["funnel_tag"] == "machine-1_funnel-1"
    assert md["confidence"] == "HIGH"
    assert md["reason"] == "first_alarm"


def test_enqueue_archive_no_worker_noop():
    """archive_worker=None 时不应抛异常"""
    cc = _make_controller(archive_worker=None)
    frames = [
        {"has_coal": True, "fault_code": 0, "frame_ref": _frame(0), "timestamp": 1},
    ]
    result = WindowResult(is_alarm=True, fault_code=0)
    # 不应 raise
    cc._enqueue_archive(frames, result)


def test_enqueue_archive_worker_exception_isolated():
    """worker.enqueue 抛异常不应传播到主路径"""
    worker = MagicMock()
    worker.enqueue.side_effect = RuntimeError("fake")
    cc = _make_controller(archive_worker=worker)
    frames = [
        {"has_coal": True, "fault_code": 0, "frame_ref": _frame(0), "timestamp": 1},
    ]
    result = WindowResult(is_alarm=True, fault_code=0)
    # 不应 raise
    cc._enqueue_archive(frames, result)


def test_enqueue_archive_skipped_when_no_ref():
    """所有帧无 frame_ref 时，不调用 worker.enqueue"""
    worker = MagicMock()
    cc = _make_controller(archive_worker=worker)
    frames = [
        {"has_coal": True, "fault_code": 0, "frame_ref": None, "timestamp": 1},
    ]
    result = WindowResult(is_alarm=True, fault_code=0)
    cc._enqueue_archive(frames, result)
    worker.enqueue.assert_not_called()
