"""
翻车机积煤检测系统 V3.0 - 跨进程帧状态管理

功能：
1. 管理双缓冲区状态
2. 原子性的缓冲区切换
3. 帧 ID 和时间戳管理
4. 性能统计

核心原理：
- 使用共享内存存储状态
- 原子操作确保线程安全
- 采集进程写，检测进程读
- 无锁设计，避免阻塞
"""

import time
import multiprocessing as mp
from typing import Tuple, Optional
from dataclasses import dataclass
from loguru import logger


@dataclass
class FrameInfo:
    """帧信息"""
    frame_id: int = 0
    timestamp: float = 0.0
    buffer_index: int = 0
    width: int = 0
    height: int = 0
    channels: int = 0


class FrameState:
    """
    跨进程帧状态管理器

    使用共享变量管理双缓冲区状态，确保采集和检测进程的同步
    """

    def __init__(self, config):
        self.config = config

        # ═══════════════════════════════════════════════════════════════
        # 共享状态变量（原子操作）
        # ═══════════════════════════════════════════════════════════════
        self.current_write_buffer = mp.Value('i', 0)    # 当前写入缓冲区索引 (0 或 1)
        self.frame_id_counter = mp.Value('i', 0)        # 帧 ID 计数器
        self.last_complete_frame_id = mp.Value('i', -1) # 最后完成的帧 ID

        # Buffer 0 状态
        self.buf0_frame_id = mp.Value('i', -1)          # Buffer 0 的帧 ID
        self.buf0_timestamp = mp.Value('d', 0.0)        # Buffer 0 的时间戳
        self.buf0_writing = mp.Value('i', 0)            # Buffer 0 是否在写入中
        self.buf0_ready = mp.Value('i', 0)              # Buffer 0 是否就绪

        # Buffer 1 状态
        self.buf1_frame_id = mp.Value('i', -1)          # Buffer 1 的帧 ID
        self.buf1_timestamp = mp.Value('d', 0.0)        # Buffer 1 的时间戳
        self.buf1_writing = mp.Value('i', 0)            # Buffer 1 是否在写入中
        self.buf1_ready = mp.Value('i', 0)              # Buffer 1 是否就绪

        # 性能统计（共享）
        self.total_captures = mp.Value('i', 0)          # 总采集帧数
        self.total_detections = mp.Value('i', 0)        # 总检测帧数
        self.dropped_frames = mp.Value('i', 0)          # 丢帧数

        # 进程间通信锁（仅用于统计，不阻塞主流程）
        self.stats_lock = mp.Lock()

        logger.info("[FrameState] 状态管理器初始化完成")

    def begin_write(self) -> Tuple[int, int]:
        """
        开始写入新帧（采集进程调用）

        Returns:
            (buffer_index, frame_id) 要写入的缓冲区索引和帧 ID
        """
        # 获取新的帧 ID
        with self.frame_id_counter.get_lock():
            frame_id = self.frame_id_counter.value
            self.frame_id_counter.value += 1

        # 选择写入缓冲区（轮替）
        buffer_idx = frame_id % 2

        # 更新缓冲区状态
        timestamp = time.time()

        if buffer_idx == 0:
            with self.buf0_frame_id.get_lock():
                self.buf0_frame_id.value = frame_id
                self.buf0_timestamp.value = timestamp
                self.buf0_writing.value = 1
                self.buf0_ready.value = 0
        else:
            with self.buf1_frame_id.get_lock():
                self.buf1_frame_id.value = frame_id
                self.buf1_timestamp.value = timestamp
                self.buf1_writing.value = 1
                self.buf1_ready.value = 0

        # 更新当前写入缓冲区
        with self.current_write_buffer.get_lock():
            self.current_write_buffer.value = buffer_idx

        return buffer_idx, frame_id

    def end_write(self, buffer_idx: int):
        """
        完成写入（采集进程调用）

        Args:
            buffer_idx: 完成写入的缓冲区索引
        """
        if buffer_idx == 0:
            with self.buf0_writing.get_lock():
                self.buf0_writing.value = 0
                self.buf0_ready.value = 1
                # 更新最后完成帧 ID
                with self.last_complete_frame_id.get_lock():
                    self.last_complete_frame_id.value = self.buf0_frame_id.value
        else:
            with self.buf1_writing.get_lock():
                self.buf1_writing.value = 0
                self.buf1_ready.value = 1
                # 更新最后完成帧 ID
                with self.last_complete_frame_id.get_lock():
                    self.last_complete_frame_id.value = self.buf1_frame_id.value

        # 统计采集帧数
        with self.total_captures.get_lock():
            self.total_captures.value += 1

    def abort_write(self, buffer_idx: int):
        """
        中止写入（采集失败时调用）

        Args:
            buffer_idx: 被中止的缓冲区索引
        """
        if buffer_idx == 0:
            with self.buf0_writing.get_lock():
                self.buf0_writing.value = 0
                self.buf0_ready.value = 0
        else:
            with self.buf1_writing.get_lock():
                self.buf1_writing.value = 0
                self.buf1_ready.value = 0

        with self.dropped_frames.get_lock():
            self.dropped_frames.value += 1

    def get_latest_frame(self) -> Optional[Tuple[int, int, float]]:
        """
        获取最新可读帧信息（检测进程调用）

        Returns:
            (buffer_index, frame_id, timestamp) 或 None（无新帧）
        """
        # 检查两个缓冲区，找到最新的就绪帧
        buf0_frame_id = self.buf0_frame_id.value
        buf0_ready = self.buf0_ready.value
        buf0_timestamp = self.buf0_timestamp.value

        buf1_frame_id = self.buf1_frame_id.value
        buf1_ready = self.buf1_ready.value
        buf1_timestamp = self.buf1_timestamp.value

        # 如果两个缓冲区都就绪，选择帧 ID 更大的
        if buf0_ready and buf1_ready:
            if buf0_frame_id > buf1_frame_id:
                return 0, buf0_frame_id, buf0_timestamp
            else:
                return 1, buf1_frame_id, buf1_timestamp

        # 只有一个缓冲区就绪
        elif buf0_ready:
            return 0, buf0_frame_id, buf0_timestamp
        elif buf1_ready:
            return 1, buf1_frame_id, buf1_timestamp

        # 都没有就绪
        return None

    def mark_frame_processed(self, buffer_idx: int, frame_id: int):
        """
        标记帧已处理（检测进程调用）

        Args:
            buffer_idx: 处理的缓冲区索引
            frame_id: 处理的帧 ID
        """
        # 清除就绪状态（允许覆盖）
        if buffer_idx == 0:
            with self.buf0_ready.get_lock():
                self.buf0_ready.value = 0
        else:
            with self.buf1_ready.get_lock():
                self.buf1_ready.value = 0

        # 统计检测帧数
        with self.total_detections.get_lock():
            self.total_detections.value += 1

    def calculate_dropped_frames(self) -> int:
        """
        计算丢帧数

        Returns:
            丢帧数量
        """
        with self.total_captures.get_lock():
            captures = self.total_captures.value

        with self.total_detections.get_lock():
            detections = self.total_detections.value

        soft_dropped = max(0, captures - detections)
        recorded_dropped = self.dropped_frames.value
        dropped = max(soft_dropped, recorded_dropped)

        # 更新丢帧统计
        with self.dropped_frames.get_lock():
            self.dropped_frames.value = dropped

        return dropped

    def get_performance_stats(self) -> dict:
        """
        获取性能统计

        Returns:
            性能统计字典
        """
        # 原子读取所有统计数据
        captures = self.total_captures.value
        detections = self.total_detections.value
        dropped = self.calculate_dropped_frames()

        # 计算跳帧率
        skip_rate = (dropped / max(1, captures)) * 100

        # 获取最新帧信息
        latest_info = self.get_latest_frame()

        return {
            "total_captures": captures,
            "total_detections": detections,
            "dropped_frames": dropped,
            "skip_rate_percent": skip_rate,
            "current_write_buffer": self.current_write_buffer.value,
            "last_complete_frame_id": self.last_complete_frame_id.value,
            "latest_frame_info": latest_info,
            "buf0_state": {
                "frame_id": self.buf0_frame_id.value,
                "timestamp": self.buf0_timestamp.value,
                "writing": bool(self.buf0_writing.value),
                "ready": bool(self.buf0_ready.value),
            },
            "buf1_state": {
                "frame_id": self.buf1_frame_id.value,
                "timestamp": self.buf1_timestamp.value,
                "writing": bool(self.buf1_writing.value),
                "ready": bool(self.buf1_ready.value),
            }
        }

    def reset_stats(self):
        """重置性能统计"""
        with self.stats_lock:
            with self.total_captures.get_lock():
                self.total_captures.value = 0
            with self.total_detections.get_lock():
                self.total_detections.value = 0
            with self.dropped_frames.get_lock():
                self.dropped_frames.value = 0

        logger.info("[FrameState] 性能统计已重置")

    def check_health(self) -> dict:
        """
        健康检查

        Returns:
            健康状态字典
        """
        stats = self.get_performance_stats()

        # 健康判断
        is_healthy = True
        warnings = []

        # 检查跳帧率
        if stats["skip_rate_percent"] > 10:
            is_healthy = False
            warnings.append(f"跳帧率过高: {stats['skip_rate_percent']:.1f}%")

        # 检查是否有新帧产生
        if stats["total_captures"] == 0:
            is_healthy = False
            warnings.append("未检测到采集帧")

        # 检查缓冲区状态
        buf0_stuck = stats["buf0_state"]["writing"] and time.time() - stats["buf0_state"]["timestamp"] > 5.0
        buf1_stuck = stats["buf1_state"]["writing"] and time.time() - stats["buf1_state"]["timestamp"] > 5.0

        if buf0_stuck or buf1_stuck:
            is_healthy = False
            warnings.append("缓冲区写入超时")

        return {
            "is_healthy": is_healthy,
            "warnings": warnings,
            "stats": stats
        }


def test_frame_state():
    """测试帧状态管理器"""
    from config.config import Config

    config = Config()
    state = FrameState(config)

    # 模拟采集进程
    print("=== 模拟采集进程 ===")
    for i in range(5):
        buffer_idx, frame_id = state.begin_write()
        print(f"开始写入 Buffer {buffer_idx}, Frame {frame_id}")

        # 模拟写入耗时
        time.sleep(0.05)

        state.end_write(buffer_idx)
        print(f"完成写入 Buffer {buffer_idx}")

        time.sleep(0.02)

    print("\n=== 模拟检测进程 ===")
    for i in range(3):
        latest = state.get_latest_frame()
        if latest:
            buffer_idx, frame_id, timestamp = latest
            print(f"检测 Buffer {buffer_idx}, Frame {frame_id}")
            state.mark_frame_processed(buffer_idx, frame_id)
        else:
            print("无新帧")

        time.sleep(0.1)

    print("\n=== 性能统计 ===")
    stats = state.get_performance_stats()
    for key, value in stats.items():
        print(f"{key}: {value}")

    print("\n=== 健康检查 ===")
    health = state.check_health()
    print(f"健康状态: {health}")


if __name__ == "__main__":
    test_frame_state()
