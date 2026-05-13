"""
翻车机积煤检测系统 V3.0 - 双缓冲共享内存

功能：
1. 跨进程共享内存管理
2. 双缓冲区切换机制
3. 高性能图像数据传输
4. 内存安全和错误处理

核心原理：
- 使用 multiprocessing.shared_memory
- 两个独立的图像缓冲区
- 采集进程写入，检测进程读取
- 无需拷贝，直接共享内存访问

安全机制：
- 边界检查
- 内存对齐
- 异常处理
- 资源清理
"""

import numpy as np
import multiprocessing as mp
from multiprocessing import shared_memory
from typing import Tuple, Optional
import time
from loguru import logger


class DoubleBuffer:
    """
    双缓冲共享内存管理器

    管理两个图像缓冲区，实现高性能的跨进程图像传输
    """

    def __init__(self, config):
        self.config = config
        self.width = config.frame_width
        self.height = config.frame_height
        self.channels = config.CHANNELS
        self.frame_size = self.width * self.height * self.channels
        self._owns_shared_memory = True
        self._closed = False

        # 计算内存对齐后的缓冲区大小
        # 确保按 64 字节边界对齐，优化缓存性能
        alignment = 64
        self.buffer_size = ((self.frame_size + alignment - 1) // alignment) * alignment

        logger.info(f"[DoubleBuffer] 初始化双缓冲区: "
                  f"{self.width}×{self.height}×{self.channels}, "
                  f"帧大小: {self.frame_size / 1024 / 1024:.1f} MB, "
                  f"缓冲区大小: {self.buffer_size / 1024 / 1024:.1f} MB")

        # 创建共享内存
        self._create_shared_buffers()

        # 创建 numpy 视图
        self._create_numpy_views()

        logger.info("[DoubleBuffer] 双缓冲区初始化完成")

    def _create_shared_buffers(self):
        """创建共享内存缓冲区"""
        try:
            # 创建两个共享内存块
            self.shm_buffer0 = shared_memory.SharedMemory(
                create=True,
                size=self.buffer_size,
                name=f"coal_detection_buf0_{int(time.time())}"
            )

            self.shm_buffer1 = shared_memory.SharedMemory(
                create=True,
                size=self.buffer_size,
                name=f"coal_detection_buf1_{int(time.time())}"
            )

            logger.info(f"[DoubleBuffer] 共享内存创建成功:")
            logger.info(f"  Buffer 0: {self.shm_buffer0.name}")
            logger.info(f"  Buffer 1: {self.shm_buffer1.name}")

        except Exception as e:
            logger.error(f"[DoubleBuffer] 共享内存创建失败: {e}")
            raise

    def _create_numpy_views(self):
        """创建 numpy 数组视图"""
        try:
            # 创建指向共享内存的 numpy 数组
            # 注意：这些数组直接映射到共享内存，修改数组就是修改共享内存
            self.buffer0 = np.ndarray(
                (self.height, self.width, self.channels),
                dtype=np.uint8,
                buffer=self.shm_buffer0.buf
            )

            self.buffer1 = np.ndarray(
                (self.height, self.width, self.channels),
                dtype=np.uint8,
                buffer=self.shm_buffer1.buf
            )

            # 初始化为黑色
            self.buffer0.fill(0)
            self.buffer1.fill(0)

            logger.info("[DoubleBuffer] numpy 视图创建成功")

        except Exception as e:
            logger.error(f"[DoubleBuffer] numpy 视图创建失败: {e}")
            raise

    def get_write_buffer(self, buffer_idx: int) -> np.ndarray:
        """
        获取写入缓冲区（采集进程使用）

        Args:
            buffer_idx: 缓冲区索引 (0 或 1)

        Returns:
            numpy 数组视图，直接写入即可
        """
        if buffer_idx == 0:
            return self.buffer0
        elif buffer_idx == 1:
            return self.buffer1
        else:
            raise ValueError(f"无效的缓冲区索引: {buffer_idx}")

    def get_read_buffer(self, buffer_idx: int) -> np.ndarray:
        """
        获取读取缓冲区（检测进程使用）

        Args:
            buffer_idx: 缓冲区索引 (0 或 1)

        Returns:
            numpy 数组视图的拷贝，避免读取过程中被覆盖
        """
        if buffer_idx == 0:
            # 返回拷贝，确保检测过程中不被修改
            return self.buffer0.copy()
        elif buffer_idx == 1:
            return self.buffer1.copy()
        else:
            raise ValueError(f"无效的缓冲区索引: {buffer_idx}")

    def copy_to_buffer(self, frame: np.ndarray, buffer_idx: int) -> bool:
        """
        拷贝图像到指定缓冲区

        Args:
            frame: 源图像
            buffer_idx: 目标缓冲区索引

        Returns:
            是否拷贝成功
        """
        try:
            # 参数检查
            if frame is None:
                logger.error("[DoubleBuffer] 源图像为空")
                return False

            if frame.shape != (self.height, self.width, self.channels):
                logger.error(f"[DoubleBuffer] 图像尺寸不匹配: "
                          f"期望 {(self.height, self.width, self.channels)}, "
                          f"实际 {frame.shape}")
                return False

            if frame.dtype != np.uint8:
                logger.warning(f"[DoubleBuffer] 数据类型不匹配: {frame.dtype} -> uint8")
                frame = frame.astype(np.uint8)

            # 直接拷贝到共享内存
            target_buffer = self.get_write_buffer(buffer_idx)
            np.copyto(target_buffer, frame)

            return True

        except Exception as e:
            logger.error(f"[DoubleBuffer] 拷贝失败: {e}")
            return False

    def get_buffer_info(self) -> dict:
        """
        获取缓冲区信息

        Returns:
            缓冲区状态信息
        """
        return {
            "width": self.width,
            "height": self.height,
            "channels": self.channels,
            "frame_size_mb": self.frame_size / 1024 / 1024,
            "buffer_size_mb": self.buffer_size / 1024 / 1024,
            "total_memory_mb": (self.buffer_size * 2) / 1024 / 1024,
            "buffer0_name": self.shm_buffer0.name,
            "buffer1_name": self.shm_buffer1.name,
            "numpy_shapes": {
                "buffer0": self.buffer0.shape,
                "buffer1": self.buffer1.shape,
            }
        }

    def test_performance(self, iterations: int = 100) -> dict:
        """
        性能测试

        Args:
            iterations: 测试迭代次数

        Returns:
            性能测试结果
        """
        logger.info(f"[DoubleBuffer] 开始性能测试 ({iterations} 次迭代)")

        # 创建测试图像
        test_frame = np.random.randint(
            0, 255, (self.height, self.width, self.channels), dtype=np.uint8
        )

        # 测试写入性能
        start_time = time.time()
        for i in range(iterations):
            buffer_idx = i % 2
            self.copy_to_buffer(test_frame, buffer_idx)

        write_time = time.time() - start_time
        write_fps = iterations / write_time

        # 测试读取性能
        start_time = time.time()
        for i in range(iterations):
            buffer_idx = i % 2
            _ = self.get_read_buffer(buffer_idx)

        read_time = time.time() - start_time
        read_fps = iterations / read_time

        # 计算带宽
        bytes_per_frame = self.frame_size
        write_bandwidth_mbps = (bytes_per_frame * write_fps) / (1024 * 1024)
        read_bandwidth_mbps = (bytes_per_frame * read_fps) / (1024 * 1024)

        results = {
            "iterations": iterations,
            "frame_size_mb": bytes_per_frame / (1024 * 1024),
            "write_time_s": write_time,
            "read_time_s": read_time,
            "write_fps": write_fps,
            "read_fps": read_fps,
            "write_bandwidth_mbps": write_bandwidth_mbps,
            "read_bandwidth_mbps": read_bandwidth_mbps,
            "avg_write_latency_ms": (write_time / iterations) * 1000,
            "avg_read_latency_ms": (read_time / iterations) * 1000,
        }

        logger.info(f"[DoubleBuffer] 性能测试完成:")
        logger.info(f"  写入: {write_fps:.1f} FPS, {write_bandwidth_mbps:.1f} MB/s")
        logger.info(f"  读取: {read_fps:.1f} FPS, {read_bandwidth_mbps:.1f} MB/s")
        logger.info(f"  延迟: 写入 {results['avg_write_latency_ms']:.1f}ms, "
                  f"读取 {results['avg_read_latency_ms']:.1f}ms")

        return results

    def close(self):
        """释放共享内存资源"""
        if getattr(self, "_closed", False):
            return

        try:
            if hasattr(self, 'shm_buffer0'):
                self.shm_buffer0.close()
                if self._owns_shared_memory:
                    try:
                        self.shm_buffer0.unlink()  # 仅创建者删除共享内存
                    except FileNotFoundError:
                        pass
                logger.info(f"[DoubleBuffer] 已关闭 {self.shm_buffer0.name}")

            if hasattr(self, 'shm_buffer1'):
                self.shm_buffer1.close()
                if self._owns_shared_memory:
                    try:
                        self.shm_buffer1.unlink()
                    except FileNotFoundError:
                        pass
                logger.info(f"[DoubleBuffer] 已关闭 {self.shm_buffer1.name}")

            logger.info("[DoubleBuffer] 资源清理完成")
            self._closed = True

        except Exception as e:
            logger.error(f"[DoubleBuffer] 资源清理失败: {e}")

    def __del__(self):
        """析构函数"""
        self.close()


def connect_to_existing_buffer(buffer0_name: str, buffer1_name: str, config) -> DoubleBuffer:
    """
    连接到已存在的共享内存缓冲区（用于子进程）

    Args:
        buffer0_name: 缓冲区0的名称
        buffer1_name: 缓冲区1的名称
        config: 配置对象

    Returns:
        DoubleBuffer 实例
    """
    try:
        # 创建一个特殊的 DoubleBuffer 实例
        db = object.__new__(DoubleBuffer)  # 跳过 __init__
        db.config = config
        db.width = config.frame_width
        db.height = config.frame_height
        db.channels = config.CHANNELS
        db.frame_size = db.width * db.height * db.channels
        db._owns_shared_memory = False
        db._closed = False

        # 连接到现有共享内存
        db.shm_buffer0 = shared_memory.SharedMemory(name=buffer0_name)
        db.shm_buffer1 = shared_memory.SharedMemory(name=buffer1_name)

        # 创建 numpy 视图
        db.buffer0 = np.ndarray(
            (db.height, db.width, db.channels),
            dtype=np.uint8,
            buffer=db.shm_buffer0.buf
        )

        db.buffer1 = np.ndarray(
            (db.height, db.width, db.channels),
            dtype=np.uint8,
            buffer=db.shm_buffer1.buf
        )

        logger.info(f"[DoubleBuffer] 已连接到现有缓冲区: {buffer0_name}, {buffer1_name}")
        return db

    except Exception as e:
        logger.error(f"[DoubleBuffer] 连接现有缓冲区失败: {e}")
        raise


def test_double_buffer():
    """测试双缓冲共享内存"""
    from config.config import Config

    # 创建配置
    config = Config()
    config.DEV_MODE = True  # 使用较小分辨率测试

    try:
        # 创建双缓冲区
        db = DoubleBuffer(config)

        # 打印信息
        info = db.get_buffer_info()
        print("缓冲区信息:")
        for key, value in info.items():
            print(f"  {key}: {value}")

        # 性能测试
        perf = db.test_performance(iterations=50)
        print("\n性能测试:")
        for key, value in perf.items():
            print(f"  {key}: {value}")

        # 测试读写操作
        print("\n功能测试:")

        # 创建测试图像
        test_frame = np.random.randint(
            0, 255, (config.frame_height, config.frame_width, 3), dtype=np.uint8
        )

        # 写入测试
        success = db.copy_to_buffer(test_frame, 0)
        print(f"写入缓冲区0: {'成功' if success else '失败'}")

        # 读取测试
        read_frame = db.get_read_buffer(0)
        print(f"读取缓冲区0: {read_frame.shape}, dtype={read_frame.dtype}")

        # 验证数据一致性
        is_equal = np.array_equal(test_frame, read_frame)
        print(f"数据一致性: {'通过' if is_equal else '失败'}")

    except Exception as e:
        print(f"测试失败: {e}")

    finally:
        if 'db' in locals():
            db.close()


if __name__ == "__main__":
    test_double_buffer()
