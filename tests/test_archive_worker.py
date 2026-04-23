"""
ArchiveWorker 单元测试

覆盖：
1. 启动 + 基本落盘
2. 队列满丢弃非报警
3. 队列满时报警帧挤掉非报警
4. 写盘失败隔离（io_errors++）
5. save_normal=False 时不保存非报警
6. 目录不可写时 start() 返回 False
7. get_stats 字段完整
"""

from __future__ import annotations

import time
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from web.archive_worker import ArchiveWorker


def _cfg(tmp_path: Path, **overrides):
    base = dict(
        IMAGE_SAVE_DIR=str(tmp_path),
        archive_queue_max=5,
        archive_save_normal=True,
        archive_jpeg_quality=80,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _fake_frame():
    return np.zeros((120, 160, 3), dtype=np.uint8)


def _wait_queue_drain(worker: ArchiveWorker, timeout: float = 2.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if worker._queue.qsize() == 0:
            # 给 worker 循环一点时间完成最后一个写入
            time.sleep(0.1)
            return
        time.sleep(0.05)


def test_start_and_save_one_alarm(tmp_path):
    cfg = _cfg(tmp_path)
    w = ArchiveWorker(cfg)
    assert w.start() is True
    try:
        w.enqueue(
            _fake_frame(),
            is_alarm=True,
            metadata={"funnel_tag": "m1_f1", "window_end": time.time(), "fault_code": 0},
        )
        _wait_queue_drain(w)
        stats = w.get_stats()
        assert stats["total_saved"] == 1
        assert stats["alarm_saved"] == 1
        assert stats["io_errors"] == 0
        files = list(tmp_path.glob("ALARM_*.jpg"))
        assert len(files) == 1
    finally:
        w.stop(timeout=3.0)


def test_save_normal_false_skips_normal(tmp_path):
    cfg = _cfg(tmp_path, archive_save_normal=False)
    w = ArchiveWorker(cfg)
    assert w.start() is True
    try:
        w.enqueue(_fake_frame(), is_alarm=False,
                  metadata={"funnel_tag": "x", "window_end": time.time()})
        _wait_queue_drain(w)
        assert w.get_stats()["total_saved"] == 0
        # 非报警被过滤不计入 dropped
        assert w.get_stats()["dropped_non_alarm"] == 0
        assert w.get_stats()["dropped_full"] == 0
    finally:
        w.stop()


def test_queue_full_drops_non_alarm(tmp_path):
    """入队上限 5；塞入 10 张非报警帧；部分被丢弃。

    不要求恰好 5 条：worker 线程可能正在并发消费，
    实际入队/丢弃总数加起来等于 10。"""
    cfg = _cfg(tmp_path, archive_queue_max=5)
    w = ArchiveWorker(cfg)
    assert w.start() is True
    try:
        for _ in range(10):
            w.enqueue(_fake_frame(), is_alarm=False,
                      metadata={"funnel_tag": "t", "window_end": time.time()})
        _wait_queue_drain(w, timeout=5.0)
        stats = w.get_stats()
        # 至少有 1 条被 dropped_full（因为 worker 消费 + 队列容量 5 < 10）
        # 总吞吐 = saved + dropped_full
        assert stats["total_saved"] + stats["dropped_full"] == 10
    finally:
        w.stop()


def test_alarm_evicts_non_alarm_when_full(tmp_path):
    """停掉消费（用不可写目录），让队列满；报警帧应能挤掉非报警"""
    cfg = _cfg(tmp_path, archive_queue_max=3)
    w = ArchiveWorker(cfg)
    assert w.start() is True
    try:
        # 阻断消费线程：把 _queue.get 改成 wait
        # 简单办法：直接操控 stop_event 暂停 loop
        # 这里换一个方式：把 stop_event 设置 + 不 join，让 loop 退出
        # 然后手动调 enqueue 并检查队列中内容
        w._stop_event.set()
        w._thread.join(timeout=2.0)
        # 现在 worker 不再消费
        assert not w._thread.is_alive()

        # 入 3 张非报警填满
        for _ in range(3):
            w.enqueue(_fake_frame(), is_alarm=False,
                      metadata={"funnel_tag": "n", "window_end": time.time()})

        # 再入 1 张报警 —— 应该挤掉 1 张非报警
        w.enqueue(_fake_frame(), is_alarm=True,
                  metadata={"funnel_tag": "a", "window_end": time.time()})

        stats = w.get_stats()
        # 队列深度仍 ≤ 3
        assert stats["queue_depth"] <= 3
        # 至少挤掉了 1 张非报警
        assert stats["dropped_non_alarm"] >= 1
    finally:
        # 不要 stop() 因为 _thread 已退出，直接 pass
        pass


def test_imwrite_failure_increments_io_errors(tmp_path, monkeypatch):
    """模拟 cv2.imwrite 返回 False -> 计 io_errors"""
    import web.archive_worker as aw

    def fake_imwrite(*args, **kwargs):
        return False

    cfg = _cfg(tmp_path)
    w = ArchiveWorker(cfg)
    assert w.start() is True
    try:
        monkeypatch.setattr(aw.cv2, "imwrite", fake_imwrite)
        w.enqueue(_fake_frame(), is_alarm=True,
                  metadata={"funnel_tag": "x", "window_end": time.time()})
        _wait_queue_drain(w)
        stats = w.get_stats()
        assert stats["total_saved"] == 0
        assert stats["io_errors"] >= 1
    finally:
        w.stop()


def test_start_fails_on_unwritable_dir(tmp_path, monkeypatch):
    """目录预检失败 -> start() False, _startup_ok False"""
    cfg = _cfg(tmp_path / "sub")

    def fake_mkdir(self, *a, **kw):
        raise PermissionError("mock permission denied")

    monkeypatch.setattr(Path, "mkdir", fake_mkdir)
    w = ArchiveWorker(cfg)
    assert w.start() is False
    assert w._startup_ok is False
    # enqueue 应被静默忽略，不 raise
    w.enqueue(_fake_frame(), is_alarm=True, metadata={"funnel_tag": "x"})


def test_stats_fields(tmp_path):
    cfg = _cfg(tmp_path)
    w = ArchiveWorker(cfg)
    assert w.start() is True
    try:
        stats = w.get_stats()
        # 必须有这些字段
        required = [
            "queue_depth", "queue_max",
            "total_saved", "alarm_saved", "normal_saved", "fault_saved",
            "dropped_full", "dropped_non_alarm", "dropped_alarm", "io_errors",
            "last_save_ms", "p50_save_ms", "p95_save_ms",
            "save_dir", "disk_total_gb", "disk_used_gb", "disk_free_gb",
            "disk_usage_pct", "startup_ok", "save_normal", "jpeg_quality",
        ]
        for k in required:
            assert k in stats, f"stats 缺字段: {k}"
    finally:
        w.stop()


def test_frame_copy_isolation(tmp_path):
    """enqueue 应当 copy frame，使后续修改不影响已入队内容"""
    cfg = _cfg(tmp_path)
    w = ArchiveWorker(cfg)
    assert w.start() is True
    try:
        frame = np.ones((120, 160, 3), dtype=np.uint8) * 100
        w.enqueue(frame, is_alarm=True,
                  metadata={"funnel_tag": "x", "window_end": time.time()})
        # 修改原 frame
        frame[:] = 0
        _wait_queue_drain(w)
        assert w.get_stats()["total_saved"] == 1
        # 如果 copy 成功，磁盘上的图像不是全黑
        import cv2
        files = list(tmp_path.glob("ALARM_*.jpg"))
        assert len(files) == 1
        img = cv2.imread(str(files[0]))
        # 图像平均像素值明显大于 0（不是全黑）—— 标注 overlay 可能变暗，但主体仍 > 10
        assert img.mean() > 10
    finally:
        w.stop()


def test_fault_prefix(tmp_path):
    """fault_code!=0 的非报警窗口应生成 FAULT_ 前缀文件名"""
    cfg = _cfg(tmp_path)
    w = ArchiveWorker(cfg)
    assert w.start() is True
    try:
        w.enqueue(
            _fake_frame(),
            is_alarm=False,
            metadata={"funnel_tag": "x", "window_end": time.time(), "fault_code": 3},
        )
        _wait_queue_drain(w)
        files = list(tmp_path.glob("FAULT_*.jpg"))
        assert len(files) == 1
        stats = w.get_stats()
        assert stats["fault_saved"] == 1
    finally:
        w.stop()
