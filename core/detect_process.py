"""
翻车机积煤检测系统 V3.0 - 检测进程

核心职责：
1. 从共享内存读取图像
2. 执行积煤检测算法
3. 输出结果到 PLC
4. 跟不上就跳帧，确保检测最新帧

设计原则：
- 最新优先：总是处理最新的可用帧
- 自适应跳帧：处理能力不足时自动跳帧
- 结果及时：检测完成立即输出，不等待
- 故障恢复：检测异常时继续运行

工业铁律：
- 宁可跳帧，不可延迟
- 宁可低精度，不可卡死
- 宁可降级，不可停止
"""

import time
import multiprocessing as mp
from typing import Optional, Dict, Any
import signal
import traceback
from loguru import logger

from drivers.factory import create_plc
from algo.detector import CoalDetector
from .double_buffer import connect_to_existing_buffer
from .frame_state import FrameState


class DetectProcess:
    """
    积煤检测进程

    独立进程，专门负责图像分析和结果输出
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
            "total_detections": 0,
            "skipped_frames": 0,
            "detection_errors": 0,
            "plc_write_errors": 0,
            "avg_detection_time": 0,
            "max_detection_time": 0,
            "last_frame_id": -1,
        }

        # 结果缓存（用于多帧投票）
        self.result_history = []

        logger.info("[DetectProcess] 检测进程初始化完成")

    def start(self):
        """启动检测进程"""
        if self.process and self.process.is_alive():
            logger.warning("[DetectProcess] 进程已在运行")
            return

        logger.info("[DetectProcess] 启动检测进程")
        self.should_stop.clear()
        self.performance_stats["start_time"] = time.time()

        # 创建进程
        self.process = mp.Process(
            target=self._detect_loop,
            name="DetectProcess",
            daemon=True  # 主进程退出时自动结束
        )
        self.process.start()

        # 等待进程启动
        started = self.is_running.wait(timeout=10.0)
        if started:
            logger.info(f"[DetectProcess] 进程启动成功 (PID: {self.process.pid})")
        else:
            logger.error("[DetectProcess] 进程启动超时")

    def stop(self, timeout: float = 5.0):
        """停止检测进程"""
        if not self.process or not self.process.is_alive():
            logger.warning("[DetectProcess] 进程未运行")
            return

        logger.info("[DetectProcess] 停止检测进程")

        # 发送停止信号
        self.should_stop.set()

        # 等待进程结束
        self.process.join(timeout=timeout)

        if self.process.is_alive():
            logger.warning("[DetectProcess] 进程未正常结束，强制终止")
            self.process.terminate()
            self.process.join(timeout=2.0)

            if self.process.is_alive():
                logger.error("[DetectProcess] 强制终止失败，发送 KILL 信号")
                self.process.kill()

        logger.info("[DetectProcess] 检测进程已停止")

    def _detect_loop(self):
        """检测主循环（在子进程中运行）"""
        try:
            # 设置进程名称和优先级
            mp.current_process().name = "CoalDetection-Detect"

            # 信号处理
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)

            logger.info(f"[DetectProcess] 检测循环启动 (PID: {mp.current_process().pid})")

            # 连接共享内存
            double_buffer = connect_to_existing_buffer(
                self.buffer0_name, self.buffer1_name, self.config
            )

            # 创建检测器
            detector = CoalDetector(self.config)

            # 创建 PLC 通信
            plc = create_plc(self.config)

            # 性能监控
            self.performance_stats["start_time"] = time.time()
            total_detection_time = 0
            max_detection_time = 0
            last_processed_frame_id = -1

            # 标记进程已启动
            self.is_running.set()

            logger.info("[DetectProcess] 开始检测循环")

            # ═══════════════════════════════════════════════════════════
            # 主检测循环
            # ═══════════════════════════════════════════════════════════
            while not self.should_stop.is_set():
                frame_id = -1
                try:
                    # ═══════════════════════════════════════════════════════
                    # 获取最新帧
                    # ═══════════════════════════════════════════════════════
                    latest_frame_info = self.state.get_latest_frame()

                    if latest_frame_info is None:
                        # 没有新帧，等待一下
                        time.sleep(0.001)  # 1ms
                        continue

                    buffer_idx, frame_id, timestamp = latest_frame_info

                    # 检查是否为新帧
                    if frame_id <= last_processed_frame_id:
                        time.sleep(0.001)
                        continue

                    # 计算帧间隔（检查是否跳帧）
                    if last_processed_frame_id >= 0:
                        skipped_count = frame_id - last_processed_frame_id - 1
                        if skipped_count > 0:
                            self.performance_stats["skipped_frames"] += skipped_count
                            logger.debug(f"[DetectProcess] 跳过 {skipped_count} 帧")

                    last_processed_frame_id = frame_id
                    self.performance_stats["last_frame_id"] = frame_id

                    # ═══════════════════════════════════════════════════════
                    # 读取图像数据
                    # ═══════════════════════════════════════════════════════
                    frame = double_buffer.get_read_buffer(buffer_idx)

                    # 计算采集到检测的延迟
                    current_time = time.time()
                    capture_to_detect_latency = (current_time - timestamp) * 1000

                    # ═══════════════════════════════════════════════════════
                    # 执行检测算法（核心计算）
                    # ═══════════════════════════════════════════════════════
                    detect_start = time.time()

                    result = detector.detect(frame, frame_id)

                    detect_time = time.time() - detect_start
                    total_detection_time += detect_time
                    max_detection_time = max(max_detection_time, detect_time)

                    # ═══════════════════════════════════════════════════════
                    # 多帧投票决策
                    # ═══════════════════════════════════════════════════════
                    final_result = self._apply_voting(result)

                    # ═══════════════════════════════════════════════════════
                    # 输出结果到 PLC
                    # ═══════════════════════════════════════════════════════
                    self._send_result_to_plc(plc, final_result, frame_id)

                    # ═══════════════════════════════════════════════════════
                    # 更新统计信息
                    # ═══════════════════════════════════════════════════════
                    self.performance_stats["total_detections"] += 1

                    # 标记帧已处理
                    self.state.mark_frame_processed(buffer_idx, frame_id)

                    # 性能日志（每50帧打印一次）
                    if self.performance_stats["total_detections"] % 50 == 0:
                        avg_detect = total_detection_time / self.performance_stats["total_detections"] * 1000
                        logger.debug(f"[DetectProcess] Frame {frame_id}: "
                                   f"延迟 {capture_to_detect_latency:.1f}ms, "
                                   f"检测 {detect_time*1000:.1f}ms, "
                                   f"平均 {avg_detect:.1f}ms")

                        # 检查性能警告
                        if detect_time > 0.08:  # 80ms 阈值
                            logger.warning(f"[DetectProcess] 检测耗时过长: {detect_time*1000:.1f}ms")

                        if capture_to_detect_latency > 150:  # 150ms 阈值
                            logger.warning(f"[DetectProcess] 端到端延迟过高: {capture_to_detect_latency:.1f}ms")

                except Exception as e:
                    # 检测异常，但不停止进程
                    frame_label = frame_id if frame_id >= 0 else "unknown"
                    logger.error(f"[DetectProcess] 检测异常 Frame {frame_label}: {e}")
                    self.performance_stats["detection_errors"] += 1

                    # 发送故障信号
                    if 'plc' in locals():
                        try:
                            fault_frame_id = frame_id
                            if fault_frame_id < 0:
                                fault_frame_id = max(0, self.performance_stats.get("last_frame_id", 0))

                            fault_result = {
                                "coal_present": False,
                                "confidence": "ERROR",
                                "need_manual": True,
                                "fault_code": 3  # FAULT_QUALITY_FAIL
                            }
                            self._send_result_to_plc(plc, fault_result, fault_frame_id)
                        except Exception as plc_error:
                            logger.debug(f"[DetectProcess] 发送故障信号失败: {plc_error}")

                    # 避免连续错误导致 CPU 100%
                    time.sleep(0.01)

        except Exception as e:
            logger.error(f"[DetectProcess] 检测循环异常: {e}")
            logger.error(traceback.format_exc())

        finally:
            # 清理资源
            try:
                if 'plc' in locals():
                    plc.close()

                if 'double_buffer' in locals():
                    double_buffer.close()

                # 清除运行状态
                self.is_running.clear()

                # 打印统计信息
                self._print_final_stats()

                logger.info("[DetectProcess] 检测循环结束")

            except Exception as cleanup_error:
                logger.error(f"[DetectProcess] 资源清理异常: {cleanup_error}")

    def _apply_voting(self, current_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        应用多帧投票机制

        Args:
            current_result: 当前帧检测结果

        Returns:
            投票后的最终结果
        """
        # 添加到历史记录（转为 dict 保证一致性）
        if hasattr(current_result, "to_dict"):
            self.result_history.append(current_result.to_dict())
        elif isinstance(current_result, dict):
            self.result_history.append(current_result)
        else:
            from dataclasses import asdict
            self.result_history.append(asdict(current_result))

        # 保持窗口大小
        window_size = self.config.VOTE_WINDOW_SIZE
        if len(self.result_history) > window_size:
            self.result_history = self.result_history[-window_size:]

        # 如果历史记录不足，直接返回当前结果
        if len(self.result_history) < self.config.VOTE_THRESHOLD:
            return current_result

        # 统计投票（兼容 dict 和 DetectionResult dataclass）
        def _get(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        coal_votes = sum(1 for r in self.result_history if _get(r, "has_coal", False))
        total_votes = len(self.result_history)

        # 投票决策
        voted_coal_present = coal_votes >= self.config.VOTE_THRESHOLD

        # 生成最终结果（转为 dict 确保可序列化和可修改）
        if hasattr(current_result, "to_dict"):
            final_result = current_result.to_dict()
        elif isinstance(current_result, dict):
            final_result = current_result.copy()
        else:
            from dataclasses import asdict
            final_result = asdict(current_result)

        final_result["has_coal"] = voted_coal_present

        # 如果投票结果与当前检测不一致，降低置信度
        if voted_coal_present != _get(current_result, "has_coal", False):
            final_result["confidence"] = "LOW"
            final_result["need_manual_confirm"] = True

        return final_result

    def _send_result_to_plc(self, plc, result: Dict[str, Any], frame_id: int):
        """
        发送结果到 PLC

        Args:
            plc: PLC 通信对象
            result: 检测结果
            frame_id: 帧 ID
        """
        try:
            if hasattr(plc, 'send_detection_result'):
                # 使用 Allen Bradley PLC 的批量发送
                plc.send_detection_result(
                    coal_present=result.get("coal_present", False),
                    confidence=result.get("confidence", "UNKNOWN"),
                    need_manual=result.get("need_manual", True),
                    fault_code=result.get("fault_code", 0)
                )
            else:
                # 逐个写入点位
                plc.write("Detection.CoalPresent", result.get("coal_present", False))
                plc.write("Detection.Confidence", result.get("confidence", "UNKNOWN"))
                plc.write("Detection.NeedManualConfirm", result.get("need_manual", True))
                plc.write("Detection.FaultCode", result.get("fault_code", 0))

                # 更新心跳
                if hasattr(plc, 'update_heartbeat'):
                    plc.update_heartbeat()

        except Exception as e:
            logger.error(f"[DetectProcess] PLC 写入失败 Frame {frame_id}: {e}")
            self.performance_stats["plc_write_errors"] += 1

    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"[DetectProcess] 收到信号 {signum}，准备退出")
        self.should_stop.set()

    def _print_final_stats(self):
        """打印最终统计信息"""
        elapsed = time.time() - self.performance_stats["start_time"]
        total_detections = self.performance_stats["total_detections"]

        if elapsed > 0 and total_detections > 0:
            avg_detect_fps = total_detections / elapsed

            logger.info("=" * 60)
            logger.info("[DetectProcess] 检测统计:")
            logger.info(f"  运行时间: {elapsed:.1f}s")
            logger.info(f"  总检测数: {total_detections}")
            logger.info(f"  跳帧数: {self.performance_stats['skipped_frames']}")
            logger.info(f"  检测帧率: {avg_detect_fps:.1f} FPS")
            logger.info(f"  检测错误: {self.performance_stats['detection_errors']}")
            logger.info(f"  PLC 错误: {self.performance_stats['plc_write_errors']}")
            logger.info(f"  最大检测耗时: {self.performance_stats['max_detection_time']*1000:.1f}ms")
            logger.info("=" * 60)

    def get_stats(self) -> dict:
        """获取实时统计信息"""
        elapsed = time.time() - self.performance_stats.get("start_time", time.time())
        total_detections = self.state.total_detections.value

        stats = self.performance_stats.copy()
        stats.update({
            "total_detections": total_detections,
            "elapsed_time": elapsed,
            "current_detect_fps": total_detections / max(elapsed, 0.001),
            "is_running": self.is_running.is_set(),
            "process_alive": self.process.is_alive() if self.process else False,
            "process_pid": self.process.pid if self.process else None,
            "vote_history_length": len(self.result_history),
        })

        return stats

    def is_healthy(self) -> bool:
        """检查检测进程健康状态"""
        if not self.process or not self.process.is_alive():
            return False

        if not self.is_running.is_set():
            return False

        # 检查是否有持续的检测
        stats = self.get_stats()
        if stats["elapsed_time"] > 10.0 and stats["current_detect_fps"] < 0.1:
            logger.warning("[DetectProcess] 检测帧率过低")
            return False

        # 检查错误率
        if stats["total_detections"] > 100:
            error_rate = stats["detection_errors"] / stats["total_detections"]
            if error_rate > 0.1:  # 错误率超过 10%
                logger.warning(f"[DetectProcess] 检测错误率过高: {error_rate*100:.1f}%")
                return False

        return True

    def __del__(self):
        """析构函数"""
        try:
            self.stop()
        except Exception:
            return


def test_detect_process():
    """测试检测进程"""
    from config.config import Config
    from .capture_process import CaptureProcess

    # 创建配置
    config = Config()
    config.DEV_MODE = True

    try:
        # 创建状态管理器
        state = FrameState(config)

        # 创建双缓冲区
        from .double_buffer import DoubleBuffer
        double_buffer = DoubleBuffer(config)
        buffer_names = (double_buffer.shm_buffer0.name, double_buffer.shm_buffer1.name)

        # 创建采集进程
        capture_proc = CaptureProcess(config, state, buffer_names)

        # 创建检测进程
        detect_proc = DetectProcess(config, state, buffer_names)

        # 启动进程
        capture_proc.start()
        time.sleep(1)  # 等待采集进程启动

        detect_proc.start()

        print("采集和检测进程已启动，运行 15 秒...")

        # 监控运行过程
        for i in range(15):
            time.sleep(1)

            # 获取统计信息
            capture_stats = capture_proc.get_stats()
            detect_stats = detect_proc.get_stats()
            perf_stats = state.get_performance_stats()

            print(f"[{i+1:2d}s] 采集: {capture_stats['current_fps']:.1f} FPS, "
                  f"检测: {detect_stats['current_detect_fps']:.1f} FPS, "
                  f"跳帧率: {perf_stats['skip_rate_percent']:.1f}%")

            # 健康检查
            if not capture_proc.is_healthy():
                print("⚠️ 采集进程异常")

            if not detect_proc.is_healthy():
                print("⚠️ 检测进程异常")

        print("测试完成")

    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 清理资源
        if 'capture_proc' in locals():
            capture_proc.stop()

        if 'detect_proc' in locals():
            detect_proc.stop()

        if 'double_buffer' in locals():
            double_buffer.close()


if __name__ == "__main__":
    test_detect_process()
