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


def test_enqueue_archive_empty_frames_is_noop():
    """零帧路径（_finalize_window 的 total==0 分支和安全超时零帧分支）
    应调用 _enqueue_archive，但因为 frames 为空，worker.enqueue 不应被调用。
    这是 A3 契约：所有完成路径统一走 _enqueue_archive，零帧时内部 no-op。"""
    worker = MagicMock()
    cc = _make_controller(archive_worker=worker)
    result = WindowResult(is_alarm=False, fault_code=3, confidence="LOW")
    # 不应 raise
    cc._enqueue_archive([], result)
    worker.enqueue.assert_not_called()


def test_finalize_window_zero_frames_calls_enqueue_archive():
    """A3：_finalize_window 在 total==0 时也必须调用 _enqueue_archive（契约统一）"""
    worker = MagicMock()
    cc = _make_controller(archive_worker=worker)
    cc._phase = CapturePhase.CAPTURING
    # 不喂任何帧
    notified = []
    cc._notify_complete = lambda: notified.append(True)

    cc._finalize_window()

    # _enqueue_archive 被调用但 worker.enqueue 不调用（零帧 no-op）
    worker.enqueue.assert_not_called()
    # _notify_complete 仍被调用
    assert notified == [True]
    # last_window_result 有 fail-safe 结果
    assert cc.last_window_result is not None
    assert cc.last_window_result.fault_code == 3


# ═════════════════════════════════════════════════════════════════════
# 内存泄漏防护（V3.0.13 修复：_enqueue_archive 必须清空 frame_ref）
# ═════════════════════════════════════════════════════════════════════

def test_enqueue_archive_releases_frame_refs_on_success():
    """_enqueue_archive 成功后必须把所有 frame_ref 置 None，
    避免 last_window_result.frame_results 长期持有整窗 ~400MB 大图"""
    worker = MagicMock()
    cc = _make_controller(archive_worker=worker)
    frames = [
        {"has_coal": True, "fault_code": 0, "frame_ref": _frame(1), "timestamp": 1},
        {"has_coal": True, "fault_code": 0, "frame_ref": _frame(2), "timestamp": 2},
        {"has_coal": True, "fault_code": 0, "frame_ref": _frame(3), "timestamp": 3},
    ]
    result = WindowResult(is_alarm=True, fault_code=0)
    cc._enqueue_archive(frames, result)

    # worker 确实被调用
    worker.enqueue.assert_called_once()
    # 关键：所有 frame_ref 必须已清空
    for f in frames:
        assert f["frame_ref"] is None, f"frame_ref 未清理：{f}"


def test_enqueue_archive_releases_frame_refs_on_worker_exception():
    """worker.enqueue 抛异常时也必须清 frame_ref（否则异常路径泄漏）"""
    worker = MagicMock()
    worker.enqueue.side_effect = RuntimeError("fake")
    cc = _make_controller(archive_worker=worker)
    frames = [
        {"has_coal": True, "fault_code": 0, "frame_ref": _frame(1), "timestamp": 1},
    ]
    result = WindowResult(is_alarm=True, fault_code=0)
    # 不应 raise
    cc._enqueue_archive(frames, result)
    # frame_ref 仍被清理
    assert frames[0]["frame_ref"] is None


def test_enqueue_archive_releases_frame_refs_when_worker_none():
    """archive_worker=None 时也必须清 frame_ref（开发/禁用归档场景同样会持有）"""
    cc = _make_controller(archive_worker=None)
    frames = [
        {"has_coal": True, "fault_code": 0, "frame_ref": _frame(1), "timestamp": 1},
    ]
    result = WindowResult(is_alarm=True, fault_code=0)
    cc._enqueue_archive(frames, result)
    assert frames[0]["frame_ref"] is None


def test_enqueue_archive_releases_frame_refs_when_all_none():
    """全 frame_ref=None 的早退分支：本来就是 None，清理操作幂等不应 raise"""
    worker = MagicMock()
    cc = _make_controller(archive_worker=worker)
    frames = [
        {"has_coal": True, "fault_code": 0, "frame_ref": None, "timestamp": 1},
    ]
    result = WindowResult(is_alarm=True, fault_code=0)
    cc._enqueue_archive(frames, result)
    assert frames[0]["frame_ref"] is None
    worker.enqueue.assert_not_called()
