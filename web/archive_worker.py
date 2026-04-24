"""
异步归档 Worker

职责：
1. 接收来自 CaptureWindowController 的代表帧
2. 后台线程异步写入磁盘（不阻塞检测 / PLC 响应）
3. 队列满时执行背压策略：报警帧优先保留
4. 提供监控统计（队列深度、落盘耗时、失败计数等）

线程模型：
- 单独 daemon 线程消费队列
- 主路径调用 enqueue() 非阻塞
- stop() 时给队列内残余项一次落盘机会
"""

from __future__ import annotations

import os
import queue
import shutil
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np
from loguru import logger


class ArchiveWorker:
    """异步归档工作线程"""

    # 背压策略阈值
    DROP_NON_ALARM_ON_FULL = True

    def __init__(self, config):
        """
        Args:
            config: Config 对象，需要字段：
                - IMAGE_SAVE_DIR: 归档目录
                - archive_queue_max: 队列上限
                - archive_save_normal: 是否保存正常窗口
                - archive_jpeg_quality: JPEG 质量（1-100）
        """
        self.config = config
        self.save_dir = Path(getattr(config, "IMAGE_SAVE_DIR", "logs/images"))
        self.queue_max = int(getattr(config, "archive_queue_max", 200))
        self.save_normal = bool(getattr(config, "archive_save_normal", True))
        self.jpeg_quality = int(getattr(config, "archive_jpeg_quality", 85))

        self._queue: "queue.Queue[dict]" = queue.Queue(maxsize=self.queue_max)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._startup_ok = False  # 目录预检是否通过

        # 监控统计
        self._lock = threading.Lock()
        self.total_saved = 0
        self.alarm_saved = 0
        self.normal_saved = 0
        self.fault_saved = 0
        self.dropped_non_alarm = 0
        self.dropped_full = 0
        self.dropped_alarm = 0
        self.io_errors = 0
        self.last_save_ms: float = 0.0
        self._recent_save_ms: deque = deque(maxlen=100)

    def start(self) -> bool:
        """
        启动后台线程。

        启动时对 save_dir 做可写性预检，失败则返回 False 并禁用归档。
        """
        if self._thread is not None and self._thread.is_alive():
            return self._startup_ok

        # 预检：目录可创建 + 可写
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            probe = self.save_dir / ".archive_probe"
            probe.write_bytes(b"ok")
            probe.unlink()
            self._startup_ok = True
            logger.info(
                f"[ArchiveWorker] 启动成功: dir={self.save_dir.resolve()}, "
                f"queue_max={self.queue_max}, jpeg_q={self.jpeg_quality}, "
                f"save_normal={self.save_normal}"
            )
        except Exception as e:
            self._startup_ok = False
            logger.error(
                f"[ArchiveWorker] 目录预检失败，归档已禁用: {self.save_dir} - {e}"
            )
            return False

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="ArchiveWorker",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self, timeout: float = 5.0):
        """停止（给队列清空机会）"""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.info(
            f"[ArchiveWorker] 已停止: total_saved={self.total_saved}, "
            f"io_errors={self.io_errors}, dropped={self.dropped_full + self.dropped_non_alarm}"
        )

    def enqueue(self, frame: np.ndarray, is_alarm: bool, metadata: Dict[str, Any]):
        """
        入队（非阻塞）。

        背压策略：
        - 队列满 + 报警帧：尝试丢弃最旧的非报警帧腾位
        - 队列满 + 非报警帧：直接丢弃，计数 dropped_non_alarm++

        Args:
            frame: 原始 BGR 帧（将被 copy 避免外部修改）
            is_alarm: 是否为报警窗口
            metadata: 归档元数据（funnel_tag/window_end/alarm_ratio 等）
        """
        if not self._startup_ok:
            return

        # 非报警且配置禁用普通窗口保存
        if not is_alarm and not self.save_normal:
            return

        if frame is None:
            return

        try:
            item = {
                "frame": frame.copy(),
                "is_alarm": bool(is_alarm),
                "metadata": dict(metadata),
                "enqueue_time": time.time(),
            }
        except Exception as e:
            logger.error(f"[ArchiveWorker] 复制帧失败: {e}")
            return

        try:
            self._queue.put_nowait(item)
            return
        except queue.Full:
            pass

        # 队列满的处理
        if is_alarm and self.DROP_NON_ALARM_ON_FULL:
            if self._make_room_for_alarm():
                try:
                    self._queue.put_nowait(item)
                    return
                except queue.Full:
                    pass
            with self._lock:
                self.dropped_alarm += 1
                self.dropped_full += 1
            logger.warning("[ArchiveWorker] 队列满，丢失报警帧")
        else:
            with self._lock:
                self.dropped_non_alarm += 1
                self.dropped_full += 1

    def _make_room_for_alarm(self) -> bool:
        """从队列中移除第一个非报警项，腾出位置"""
        try:
            items = []
            while True:
                try:
                    items.append(self._queue.get_nowait())
                except queue.Empty:
                    break

            removed = False
            for it in items:
                if not removed and not it["is_alarm"]:
                    removed = True
                    with self._lock:
                        self.dropped_non_alarm += 1
                    continue
                try:
                    self._queue.put_nowait(it)
                except queue.Full:
                    break
            return removed
        except Exception as e:
            logger.error(f"[ArchiveWorker] 腾位异常: {e}")
            return False

    def _run_loop(self):
        """消费循环"""
        logger.debug("[ArchiveWorker] 消费线程启动")
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            self._save_one(item)

        # 停止时清空队列
        drained = 0
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            self._save_one(item)
            drained += 1
        if drained:
            logger.info(f"[ArchiveWorker] 停止时排空 {drained} 张")

    def _save_one(self, item: Dict[str, Any]):
        """写盘一条项（异常隔离）"""
        try:
            t0 = time.perf_counter()
            frame = item["frame"]
            metadata = item["metadata"]
            is_alarm = item["is_alarm"]
            fault_code = int(metadata.get("fault_code", 0) or 0)

            # 文件名：{prefix}_{funnel_tag}_{yyyymmdd_HHMMSS}.jpg
            if is_alarm:
                prefix = "ALARM"
            elif fault_code != 0:
                prefix = "FAULT"
            else:
                prefix = "NORMAL"

            funnel_tag = str(metadata.get("funnel_tag", "unknown"))
            window_end = float(metadata.get("window_end") or time.time())
            ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(window_end))
            filename = f"{prefix}_{funnel_tag}_{ts}.jpg"
            filepath = self.save_dir / filename

            # 标注
            annotated = self._annotate(frame, metadata, is_alarm, prefix)

            ok = cv2.imwrite(
                str(filepath),
                annotated,
                [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
            )
            if not ok:
                raise IOError(f"cv2.imwrite 返回 False: {filepath}")

            elapsed_ms = (time.perf_counter() - t0) * 1000
            with self._lock:
                self.total_saved += 1
                if is_alarm:
                    self.alarm_saved += 1
                elif fault_code != 0:
                    self.fault_saved += 1
                else:
                    self.normal_saved += 1
                self.last_save_ms = elapsed_ms
                self._recent_save_ms.append(elapsed_ms)
        except Exception as e:
            with self._lock:
                self.io_errors += 1
            logger.error(f"[ArchiveWorker] 写盘失败: {e}")

    def _annotate(
        self,
        frame: np.ndarray,
        metadata: Dict[str, Any],
        is_alarm: bool,
        prefix: str,
    ) -> np.ndarray:
        """在图像上标注元数据（右上角半透明信息框）"""
        try:
            img = frame.copy()
            if img.ndim == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

            lines = [
                f"{prefix} | {metadata.get('funnel_tag', '?')}",
                f"Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(metadata.get('window_end', time.time())))}",
                f"Conf: {metadata.get('confidence', '?')}  Fault: {metadata.get('fault_code', 0)}",
                f"AlarmRatio: {float(metadata.get('alarm_ratio', 0) or 0):.0%}  "
                f"Grids: {float(metadata.get('coal_grids_avg', 0) or 0):.1f}",
                f"Reason: {metadata.get('reason', '?')}",
            ]

            overlay = img.copy()
            h, w = img.shape[:2]
            box_w = 480
            box_h = 130
            x0 = max(10, w - box_w - 10)
            y0 = 10
            cv2.rectangle(overlay, (x0, y0), (x0 + box_w, y0 + box_h), (0, 0, 0), -1)
            img = cv2.addWeighted(overlay, 0.55, img, 0.45, 0)

            color = (0, 0, 255) if is_alarm else (200, 200, 200)
            for i, text in enumerate(lines):
                cv2.putText(
                    img, text,
                    (x0 + 10, y0 + 22 + i * 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
                )
            return img
        except Exception:
            # 标注失败不应阻塞落盘：返回原图
            return frame

    def get_stats(self) -> Dict[str, Any]:
        """获取归档统计（线程安全快照）"""
        with self._lock:
            recent = list(self._recent_save_ms)
            last_ms = self.last_save_ms
            snap = {
                "total_saved": self.total_saved,
                "alarm_saved": self.alarm_saved,
                "normal_saved": self.normal_saved,
                "fault_saved": self.fault_saved,
                "dropped_full": self.dropped_full,
                "dropped_non_alarm": self.dropped_non_alarm,
                "dropped_alarm": self.dropped_alarm,
                "io_errors": self.io_errors,
            }

        # p50 / p95
        p50 = p95 = 0.0
        if recent:
            sorted_ms = sorted(recent)
            p50 = sorted_ms[len(sorted_ms) // 2]
            p95 = sorted_ms[int(len(sorted_ms) * 0.95)] if len(sorted_ms) >= 20 else sorted_ms[-1]

        # 磁盘使用率
        try:
            total, used, free = shutil.disk_usage(str(self.save_dir.resolve().anchor or self.save_dir.resolve()))
            disk_total_gb = total / (1024 ** 3)
            disk_used_gb = used / (1024 ** 3)
            disk_free_gb = free / (1024 ** 3)
            disk_usage_pct = round((used / total) * 100, 2) if total else 0.0
        except Exception:
            disk_total_gb = disk_used_gb = disk_free_gb = 0.0
            disk_usage_pct = 0.0

        snap.update({
            "queue_depth": self._queue.qsize(),
            "queue_max": self.queue_max,
            "last_save_ms": round(last_ms, 2),
            "p50_save_ms": round(p50, 2),
            "p95_save_ms": round(p95, 2),
            "save_dir": str(self.save_dir.resolve()),
            "disk_total_gb": round(disk_total_gb, 1),
            "disk_used_gb": round(disk_used_gb, 1),
            "disk_free_gb": round(disk_free_gb, 1),
            "disk_usage_pct": disk_usage_pct,
            "startup_ok": self._startup_ok,
            "save_normal": self.save_normal,
            "jpeg_quality": self.jpeg_quality,
        })
        return snap
