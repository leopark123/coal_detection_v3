"""
翻车机积煤检测系统 V3.0 - 主程序入口

使用方式：
    开发模式：python main.py --dev
    生产模式：python main.py --config config/config_prod.yaml
"""

import sys
import time
import argparse
from pathlib import Path
from typing import Optional

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger
from config.config import Config
from drivers.factory import create_camera, create_plc, create_image_saver
from algo.detector import CoalDetector, FrameVoter
from core.frame_state import FrameState
from core.double_buffer import DoubleBuffer
from core.capture_process import CaptureProcess
from core.detect_process import DetectProcess


def setup_logging(config: Config):
    """配置日志"""
    logger.remove()  # 移除默认处理器
    
    # 控制台输出
    logger.add(
        sys.stderr,
        level=config.LOG_LEVEL,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>"
    )
    
    # 文件输出
    logger.add(
        "logs/coal_detection_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # 每天轮转
        retention="30 days",
        level="DEBUG",
        encoding="utf-8"
    )


def run_detection_loop(config: Config):
    """
    运行检测主循环
    
    开发模式：单进程，便于调试
    """
    # 打印配置
    config.print_summary()
    
    # 创建组件
    logger.info("正在初始化组件...")
    camera = create_camera(config)
    plc = create_plc(config)
    image_saver = create_image_saver(config)
    detector = CoalDetector(config)
    voter = FrameVoter(config)
    
    logger.info("=" * 50)
    logger.info("  系统启动完成，开始检测...")
    logger.info("  按 Ctrl+C 停止")
    logger.info("=" * 50)
    
    frame_id = 0
    consecutive_errors = 0
    max_errors = 5
    
    try:
        while True:
            loop_start = time.perf_counter()
            
            # ═══════════════════════════════════════════════════════
            # 1. 采集图像
            # ═══════════════════════════════════════════════════════
            try:
                frame = camera.grab()
                consecutive_errors = 0  # 重置错误计数
            except ConnectionError as e:
                consecutive_errors += 1
                logger.error(f"相机采集失败 ({consecutive_errors}/{max_errors}): {e}")
                
                if consecutive_errors >= max_errors:
                    logger.critical("相机连续失败，尝试重连...")
                    if hasattr(camera, 'reconnect'):
                        camera.reconnect()
                    consecutive_errors = 0
                
                time.sleep(1)
                continue
            except Exception as e:
                logger.exception(f"采集异常: {e}")
                time.sleep(1)
                continue
            
            # ═══════════════════════════════════════════════════════
            # 2. 检测
            # ═══════════════════════════════════════════════════════
            result = detector.detect(frame, frame_id)
            
            # ═══════════════════════════════════════════════════════
            # 3. 多帧投票
            # ═══════════════════════════════════════════════════════
            voted_result = voter.vote(result)
            
            # ═══════════════════════════════════════════════════════
            # 4. 输出到 PLC（5 个标签，最小化通信）
            # ═══════════════════════════════════════════════════════
            coal_present = voted_result.has_coal or False
            need_manual = voted_result.need_manual_confirm
            confidence = voted_result.confidence

            # 故障码
            if not voted_result.quality_ok:
                fault_code = 3  # 画面质量问题
            elif need_manual:
                fault_code = 4  # 低置信度，需人工确认
            else:
                fault_code = 0

            # 一次性发送（含心跳）
            plc.send_detection_result(
                coal_present=coal_present,
                confidence=confidence,
                need_manual=need_manual,
                fault_code=fault_code
            )
            
            # ═══════════════════════════════════════════════════════
            # 5. 保存图像（报警或定时）
            # ═══════════════════════════════════════════════════════
            is_alarm = voted_result.has_coal is True
            if image_saver.should_save(frame_id, is_alarm):
                image_saver.save(
                    frame, frame_id, 
                    is_alarm=is_alarm,
                    result=voted_result.to_dict()
                )
            
            # ═══════════════════════════════════════════════════════
            # 6. 日志
            # ═══════════════════════════════════════════════════════
            loop_time = (time.perf_counter() - loop_start) * 1000
            
            # 结果图标
            if voted_result.has_coal is True:
                icon = "🚨"
            elif voted_result.has_coal is False:
                icon = "✅"
            else:
                icon = "❓"
            
            logger.info(
                f"{icon} 帧#{frame_id:05d} | "
                f"耗时:{loop_time:5.1f}ms | "
                f"格栅:{voted_result.grid_visible_ratio:.0%} | "
                f"覆盖:{voted_result.coal_coverage:.0%} | "
                f"{voted_result.confidence}"
            )
            
            frame_id += 1
            
            # ═══════════════════════════════════════════════════════
            # 7. 帧率控制
            # ═══════════════════════════════════════════════════════
            elapsed = time.perf_counter() - loop_start
            sleep_time = config.frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    except KeyboardInterrupt:
        logger.info("\n收到停止信号，正在退出...")
    
    finally:
        # 清理资源
        camera.release()
        plc.close()
        
        # 打印统计
        stats = image_saver.get_stats()
        logger.info("=" * 50)
        logger.info(f"  共处理 {frame_id} 帧")
        logger.info(f"  保存图像 {stats['total_saved']} 张（报警 {stats['alarm_saved']} 张）")
        logger.info("=" * 50)


class CoalDetectionSystem:
    """多进程系统封装（兼容集成测试入口）"""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self._frame_state: Optional[FrameState] = None
        self._double_buffer: Optional[DoubleBuffer] = None
        self._capture_process: Optional[CaptureProcess] = None
        self._detect_process: Optional[DetectProcess] = None
        self._running = False

    def start(self) -> bool:
        """启动系统"""
        if self._running:
            return True

        try:
            self._frame_state = FrameState(self.config)
            self._double_buffer = DoubleBuffer(self.config)
            buffer_names = (
                self._double_buffer.shm_buffer0.name,
                self._double_buffer.shm_buffer1.name,
            )

            self._capture_process = CaptureProcess(self.config, self._frame_state, buffer_names)
            self._detect_process = DetectProcess(self.config, self._frame_state, buffer_names)

            self._capture_process.start()
            time.sleep(0.5)
            self._detect_process.start()

            self._running = True
            return True

        except Exception as e:
            logger.error(f"系统启动失败: {e}")
            self.stop()
            return False

    def stop(self):
        """停止系统"""
        if self._detect_process:
            self._detect_process.stop()
        if self._capture_process:
            self._capture_process.stop()
        if self._double_buffer:
            self._double_buffer.close()

        self._running = False

    def is_running(self) -> bool:
        """系统是否运行中"""
        if not self._running:
            return False

        capture_alive = (
            self._capture_process is not None
            and self._capture_process.process is not None
            and self._capture_process.process.is_alive()
        )
        detect_alive = (
            self._detect_process is not None
            and self._detect_process.process is not None
            and self._detect_process.process.is_alive()
        )
        return capture_alive and detect_alive

    def get_status(self) -> dict:
        """获取系统状态快照"""
        capture_stats = self._capture_process.get_stats() if self._capture_process else {}
        detect_stats = self._detect_process.get_stats() if self._detect_process else {}
        frame_stats = self._frame_state.get_performance_stats() if self._frame_state else {}

        return {
            "running": self.is_running(),
            "capture_fps": capture_stats.get("current_fps", 0.0),
            "detect_fps": detect_stats.get("current_detect_fps", 0.0),
            "capture_frames": capture_stats.get("total_frames", 0),
            "detect_frames": detect_stats.get("total_detections", 0),
            "skip_rate_percent": frame_stats.get("skip_rate_percent", 0.0),
            "capture_process_alive": capture_stats.get("process_alive", False),
            "detect_process_alive": detect_stats.get("process_alive", False),
        }


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="翻车机积煤检测系统 V3.0"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="配置文件路径（YAML）"
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="开发模式（自动启用 DEV_MODE）"
    )
    parser.add_argument(
        "--fault-injection",
        action="store_true",
        help="启用故障注入（测试异常处理）"
    )
    
    args = parser.parse_args()
    
    # 加载配置
    if args.config:
        config = Config.from_yaml(args.config)
    else:
        config = Config()
    
    # 命令行覆盖
    if args.dev:
        config.DEV_MODE = True
    
    if args.fault_injection:
        config.MOCK_ENABLE_FAULT_INJECTION = True
    
    # 设置日志
    setup_logging(config)
    
    # 运行主循环
    run_detection_loop(config)


if __name__ == "__main__":
    main()
