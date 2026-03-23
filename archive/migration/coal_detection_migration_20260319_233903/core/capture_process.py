"""
翻车机积煤检测系统 V3.0 - 采集进程

核心职责：
1. 从相机持续采集图像
2. 写入共享内存缓冲区
3. 永不阻塞，永不等待检测进程
4. 性能监控和故障处理

设计原则：
- 采集永不停：无论检测进程状态如何，采集必须持续
- 最新优先：如果缓冲区忙碌，直接丢弃当前帧，继续采集下一帧
- 故障自愈：相机掉线时自动重连
- 性能优先：最小化采集延迟

工业铁律：
- 宁可丢帧，不可停采
- 宁可过载，不可卡死
"""

import time
import multiprocessing as mp
from typing import Optional
import signal
import traceback
from loguru import logger

from drivers.factory import create_camera
from .double_buffer import DoubleBuffer, connect_to_existing_buffer
from .frame_state import FrameState


class CaptureProcess:
    """
    图像采集进程

    独立进程，专门负责高频图像采集
    """

    def __init__(self, config, shared_state: FrameState, buffer_names: tuple):
        self.config = config
        self.state = shared_state
        self.buffer0_name, self.buffer1_name = buffer_names

        # 进程控制
        self.should_stop = mp.Event()
        self.is_running = mp.Event()
        self.process = None

        # 性能监控
        self.performance_stats = {
            "start_time": 0,
            "total_frames": 0,
            "dropped_frames": 0,
            "camera_errors": 0,
            "reconnect_count": 0,
            "avg_capture_time": 0,
            "max_capture_time": 0,
        }

        logger.info("[CaptureProcess] 采集进程初始化完成")

    def start(self):
        """启动采集进程"""
        if self.process and self.process.is_alive():
            logger.warning("[CaptureProcess] 进程已在运行")
            return

        logger.info("[CaptureProcess] 启动采集进程")
        self.should_stop.clear()
        self.performance_stats["start_time"] = time.time()

        # 创建进程
        self.process = mp.Process(
            target=self._capture_loop,
            name="CaptureProcess",
            daemon=True  # 主进程退出时自动结束
        )
        self.process.start()

        # 等待进程启动
        started = self.is_running.wait(timeout=10.0)
        if started:
            logger.info(f"[CaptureProcess] 进程启动成功 (PID: {self.process.pid})")
        else:
            logger.error("[CaptureProcess] 进程启动超时")

    def stop(self, timeout: float = 5.0):
        """停止采集进程"""
        if not self.process or not self.process.is_alive():
            logger.warning("[CaptureProcess] 进程未运行")
            return

        logger.info("[CaptureProcess] 停止采集进程")

        # 发送停止信号
        self.should_stop.set()

        # 等待进程结束
        self.process.join(timeout=timeout)

        if self.process.is_alive():
            logger.warning("[CaptureProcess] 进程未正常结束，强制终止")
            self.process.terminate()
            self.process.join(timeout=2.0)

            if self.process.is_alive():
                logger.error("[CaptureProcess] 强制终止失败，发送 KILL 信号")
                self.process.kill()

        logger.info("[CaptureProcess] 采集进程已停止")

    def _capture_loop(self):
        """采集主循环（在子进程中运行）"""
        try:
            # 设置进程名称和优先级
            mp.current_process().name = "CoalDetection-Capture"

            # 信号处理
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)

            logger.info(f"[CaptureProcess] 采集循环启动 (PID: {mp.current_process().pid})")

            # 连接共享内存
            double_buffer = connect_to_existing_buffer(
                self.buffer0_name, self.buffer1_name, self.config
            )

            # 创建相机
            camera = create_camera(self.config)

            # 性能监控
            self.performance_stats["start_time"] = time.time()
            total_capture_time = 0
            max_capture_time = 0

            # 标记进程已启动
            self.is_running.set()

            logger.info("[CaptureProcess] 开始图像采集循环")

            # ═══════════════════════════════════════════════════════════
            # 主采集循环
            # ═══════════════════════════════════════════════════════════
            while not self.should_stop.is_set():
                capture_time = 0.0
                write_time = 0.0
                buffer_idx = None
                write_finalized = False
                try:
                    # 获取写入缓冲区
                    buffer_idx, frame_id = self.state.begin_write()

                    # ═══════════════════════════════════════════════════════
                    # 采集图像（核心操作）
                    # ═══════════════════════════════════════════════════════
                    capture_start = time.time()

                    frame = camera.grab()

                    capture_time = time.time() - capture_start
                    total_capture_time += capture_time
                    max_capture_time = max(max_capture_time, capture_time)

                    # ═══════════════════════════════════════════════════════
                    # 写入共享内存（快速操作）
                    # ═══════════════════════════════════════════════════════
                    write_start = time.time()

                    success = double_buffer.copy_to_buffer(frame, buffer_idx)

                    write_time = time.time() - write_start

                    if success:
                        # 标记写入完成
                        self.state.end_write(buffer_idx)
                        write_finalized = True

                        self.performance_stats["total_frames"] += 1

                        # 性能监控（每100帧打印一次）
                        if self.performance_stats["total_frames"] % 100 == 0:
                            avg_capture = total_capture_time / self.performance_stats["total_frames"] * 1000
                            logger.debug(f"[CaptureProcess] Frame {frame_id}: "
                                       f"采集 {capture_time*1000:.1f}ms, "
                                       f"写入 {write_time*1000:.1f}ms, "
                                       f"平均采集 {avg_capture:.1f}ms")

                    else:
                        logger.error(f"[CaptureProcess] 写入共享内存失败 Frame {frame_id}")
                        self.performance_stats["dropped_frames"] += 1
                        self.state.abort_write(buffer_idx)
                        write_finalized = True

                except ConnectionError as e:
                    if buffer_idx is not None and not write_finalized:
                        self.state.abort_write(buffer_idx)
                        write_finalized = True

                    # 相机连接错误，尝试重连
                    logger.error(f"[CaptureProcess] 相机连接错误: {e}")
                    self.performance_stats["camera_errors"] += 1

                    if hasattr(camera, 'reconnect'):
                        logger.info("[CaptureProcess] 尝试重连相机...")
                        if camera.reconnect():
                            logger.info("[CaptureProcess] 相机重连成功")
                            self.performance_stats["reconnect_count"] += 1
                        else:
                            logger.error("[CaptureProcess] 相机重连失败，等待 1 秒后继续")
                            time.sleep(1.0)
                    else:
                        # 重新创建相机
                        logger.info("[CaptureProcess] 重新创建相机驱动...")
                        try:
                            camera = create_camera(self.config)
                            self.performance_stats["reconnect_count"] += 1
                        except Exception as camera_error:
                            logger.error(f"[CaptureProcess] 相机创建失败: {camera_error}")
                            time.sleep(1.0)
                    continue

                except Exception as e:
                    if buffer_idx is not None and not write_finalized:
                        self.state.abort_write(buffer_idx)
                        write_finalized = True

                    # 其他异常
                    logger.error(f"[CaptureProcess] 采集异常: {e}")
                    logger.error(traceback.format_exc())
                    self.performance_stats["camera_errors"] += 1

                    # 避免连续失败导致 CPU 100%
                    time.sleep(0.01)
                    continue

                # ═══════════════════════════════════════════════════════
                # 帧率控制（如果需要）
                # ═══════════════════════════════════════════════════════
                if hasattr(self.config, 'frame_interval'):
                    time.sleep(max(0, self.config.frame_interval - capture_time - write_time))

        except Exception as e:
            logger.error(f"[CaptureProcess] 采集循环异常: {e}")
            logger.error(traceback.format_exc())

        finally:
            # 清理资源
            try:
                if 'camera' in locals():
                    camera.release()

                if 'double_buffer' in locals():
                    double_buffer.close()

                # 清除运行状态
                self.is_running.clear()

                # 打印统计信息
                self._print_final_stats()

                logger.info("[CaptureProcess] 采集循环结束")

            except Exception as cleanup_error:
                logger.error(f"[CaptureProcess] 资源清理异常: {cleanup_error}")

    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"[CaptureProcess] 收到信号 {signum}，准备退出")
        self.should_stop.set()

    def _print_final_stats(self):
        """打印最终统计信息"""
        elapsed = time.time() - self.performance_stats["start_time"]
        total_frames = self.performance_stats["total_frames"]

        if elapsed > 0 and total_frames > 0:
            avg_fps = total_frames / elapsed
            drop_rate = (self.performance_stats["dropped_frames"] / total_frames) * 100

            logger.info("=" * 60)
            logger.info("[CaptureProcess] 采集统计:")
            logger.info(f"  运行时间: {elapsed:.1f}s")
            logger.info(f"  总帧数: {total_frames}")
            logger.info(f"  丢帧数: {self.performance_stats['dropped_frames']}")
            logger.info(f"  平均帧率: {avg_fps:.1f} FPS")
            logger.info(f"  丢帧率: {drop_rate:.2f}%")
            logger.info(f"  相机错误: {self.performance_stats['camera_errors']}")
            logger.info(f"  重连次数: {self.performance_stats['reconnect_count']}")
            logger.info("=" * 60)

    def get_stats(self) -> dict:
        """获取实时统计信息"""
        elapsed = time.time() - self.performance_stats.get("start_time", time.time())
        total_frames = self.state.total_captures.value

        stats = self.performance_stats.copy()
        stats.update({
            "total_frames": total_frames,
            "elapsed_time": elapsed,
            "current_fps": total_frames / max(elapsed, 0.001),
            "is_running": self.is_running.is_set(),
            "process_alive": self.process.is_alive() if self.process else False,
            "process_pid": self.process.pid if self.process else None,
        })

        return stats

    def is_healthy(self) -> bool:
        """检查采集进程健康状态"""
        if not self.process or not self.process.is_alive():
            return False

        if not self.is_running.is_set():
            return False

        # 检查是否有持续的采集
        stats = self.get_stats()
        if stats["elapsed_time"] > 5.0 and stats["current_fps"] < 0.1:
            logger.warning("[CaptureProcess] 采集帧率过低")
            return False

        return True

    def __del__(self):
        """析构函数"""
        try:
            self.stop()
        except Exception:
            return


def test_capture_process():
    """测试采集进程"""
    from config.config import Config
    import cv2

    # 创建配置
    config = Config()
    config.DEV_MODE = True  # 开发模式

    try:
        # 创建状态管理器
        state = FrameState(config)

        # 创建双缓冲区
        double_buffer = DoubleBuffer(config)
        buffer_names = (double_buffer.shm_buffer0.name, double_buffer.shm_buffer1.name)

        # 创建采集进程
        capture_proc = CaptureProcess(config, state, buffer_names)

        # 启动采集
        capture_proc.start()

        print("采集进程已启动，按 'q' 退出...")

        # 监控采集过程
        start_time = time.time()
        while time.time() - start_time < 10:  # 运行 10 秒
            # 获取最新帧
            latest = state.get_latest_frame()
            if latest:
                buffer_idx, frame_id, timestamp = latest

                # 读取图像
                frame = double_buffer.get_read_buffer(buffer_idx)

                # 显示图像
                cv2.imshow("Capture Test", frame)

                # 标记已处理
                state.mark_frame_processed(buffer_idx, frame_id)

                print(f"处理 Frame {frame_id}, Buffer {buffer_idx}")

            # 检查按键
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            time.sleep(0.1)

        # 打印统计
        stats = capture_proc.get_stats()
        print("采集统计:", stats)

        perf_stats = state.get_performance_stats()
        print("性能统计:", perf_stats)

    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 清理资源
        if 'capture_proc' in locals():
            capture_proc.stop()

        if 'double_buffer' in locals():
            double_buffer.close()

        cv2.destroyAllWindows()


if __name__ == "__main__":
    test_capture_process()
