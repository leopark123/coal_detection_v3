"""
翻车机积煤检测系统 V3.0 - 窗口采集控制器

采集模式：
  不是持续采集，而是按周期在固定时间窗口内采集。

时间轴：
  |--- 空闲期(不采集) ---|--- 采集窗口(连续采集+投票) ---|--- 空闲期 ---|
  |<-------- cycle_interval_s -------->|

参数（均可通过设置页实时调整）：
  - cycle_interval_s:  采集周期（秒），两次采集窗口的间隔
  - window_duration_s: 采集窗口时长（秒），窗口内连续采集
  - pre_delay_s:       窗口前延时（秒），翻车机回位后等待稳定
  - vote_threshold:    投票阈值，窗口内超过该比例的帧报警才输出报警

状态机：
  IDLE → (周期到) → DELAY → (延时结束) → CAPTURING → (窗口结束) → JUDGING → IDLE
"""

import time
import threading
from enum import Enum
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field
from loguru import logger


class CapturePhase(str, Enum):
    """采集阶段"""
    IDLE = "idle"           # 空闲，等待下一个周期
    DELAY = "delay"         # 延时等待（翻车机稳定）
    CAPTURING = "capturing" # 采集窗口内，正在采集
    JUDGING = "judging"     # 窗口结束，汇总判定中


@dataclass
class CaptureWindowConfig:
    """窗口采集配置"""
    cycle_interval_s: float = 30.0    # 采集周期（秒）
    window_duration_s: float = 3.0    # 采集窗口时长（秒）
    pre_delay_s: float = 2.0          # 窗口前延时（秒）
    vote_threshold: float = 0.6       # 投票阈值（0-1，超过该比例报警才输出报警）

    def validate(self):
        """校验参数合理性"""
        if self.cycle_interval_s < self.window_duration_s + self.pre_delay_s:
            raise ValueError("采集周期必须大于窗口时长+延时")
        if not 0 < self.vote_threshold <= 1:
            raise ValueError("投票阈值必须在 (0, 1] 之间")


@dataclass
class WindowResult:
    """单次采集窗口的汇总结果"""
    total_frames: int = 0             # 窗口内总帧数
    alarm_frames: int = 0             # 报警帧数
    alarm_ratio: float = 0.0          # 报警比例
    is_alarm: bool = False            # 最终是否报警
    confidence: str = "NORMAL"        # 置信度
    fault_code: int = 0               # 故障码
    coal_grids_avg: float = 0.0       # 平均积煤格栅数
    window_start: float = 0.0         # 窗口开始时间
    window_end: float = 0.0           # 窗口结束时间
    frame_results: List[Dict] = field(default_factory=list)  # 每帧结果


class CaptureWindowController:
    """
    窗口采集控制器

    管理单个漏斗的采集节奏：周期性地打开采集窗口，
    窗口内连续采集并投票，窗口结束后输出汇总结果。

    使用方式：
        controller = CaptureWindowController(config)
        controller.start()

        # 在采集循环中检查：
        if controller.should_capture():
            result = detect(frame)
            controller.feed_result(result)

        # 获取最新窗口结果：
        window_result = controller.last_window_result
    """

    def __init__(self, config: Optional[CaptureWindowConfig] = None):
        self.config = config or CaptureWindowConfig()
        self._phase = CapturePhase.IDLE
        self._cycle_start_time: float = 0.0
        self._window_start_time: float = 0.0
        self._frame_results: List[Dict] = []
        self._lock = threading.Lock()

        # 最近一次窗口的汇总结果
        self.last_window_result: Optional[WindowResult] = None

        # 回调：窗口判定完成后通知外部（如写 PLC）
        self.on_window_complete: Optional[Callable[[WindowResult], None]] = None

        self._running = False
        self._started_time: float = 0.0

    @property
    def phase(self) -> CapturePhase:
        return self._phase

    @property
    def phase_display(self) -> str:
        """中文状态显示"""
        return {
            CapturePhase.IDLE: "空闲",
            CapturePhase.DELAY: "延时等待",
            CapturePhase.CAPTURING: "采集中",
            CapturePhase.JUDGING: "判定中",
        }.get(self._phase, "未知")

    @property
    def time_to_next_window(self) -> float:
        """距离下一个采集窗口的秒数"""
        if not self._running:
            return -1
        if self._phase == CapturePhase.CAPTURING:
            return 0
        elapsed = time.time() - self._cycle_start_time
        remaining = self.config.cycle_interval_s - elapsed
        return max(0, remaining)

    @property
    def window_remaining(self) -> float:
        """当前窗口剩余秒数（仅 CAPTURING 阶段有意义）"""
        if self._phase != CapturePhase.CAPTURING:
            return 0
        elapsed = time.time() - self._window_start_time
        return max(0, self.config.window_duration_s - elapsed)

    def start(self):
        """启动窗口采集控制"""
        self._running = True
        self._started_time = time.time()
        self._cycle_start_time = time.time()
        self._phase = CapturePhase.IDLE
        logger.info(
            f"[CaptureWindow] 启动: 周期={self.config.cycle_interval_s}s, "
            f"窗口={self.config.window_duration_s}s, "
            f"延时={self.config.pre_delay_s}s, "
            f"投票阈值={self.config.vote_threshold}"
        )

    def stop(self):
        """停止窗口采集"""
        self._running = False
        self._phase = CapturePhase.IDLE
        logger.info("[CaptureWindow] 已停止")

    def update_config(self, **kwargs):
        """运行时更新配置参数"""
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self.config, k):
                    setattr(self.config, k, v)
            try:
                self.config.validate()
            except ValueError as e:
                logger.warning(f"[CaptureWindow] 配置校验失败: {e}")

    def tick(self):
        """
        每帧调用一次，驱动状态机转换。

        Returns:
            当前阶段
        """
        if not self._running:
            return self._phase

        now = time.time()
        elapsed_in_cycle = now - self._cycle_start_time

        if self._phase == CapturePhase.IDLE:
            # 周期到了，进入延时阶段
            if elapsed_in_cycle >= self.config.cycle_interval_s:
                self._phase = CapturePhase.DELAY
                self._cycle_start_time = now
                logger.debug("[CaptureWindow] → DELAY")

        elif self._phase == CapturePhase.DELAY:
            # 延时结束，进入采集阶段
            if elapsed_in_cycle >= self.config.pre_delay_s:
                self._phase = CapturePhase.CAPTURING
                self._window_start_time = now
                self._frame_results.clear()
                logger.info("[CaptureWindow] → CAPTURING")

        elif self._phase == CapturePhase.CAPTURING:
            # 窗口时间到，进入判定阶段
            window_elapsed = now - self._window_start_time
            if window_elapsed >= self.config.window_duration_s:
                self._phase = CapturePhase.JUDGING
                logger.debug(
                    f"[CaptureWindow] → JUDGING ({len(self._frame_results)} frames)"
                )
                self._finalize_window()
                self._phase = CapturePhase.IDLE

        return self._phase

    def should_capture(self) -> bool:
        """当前是否应该采集帧"""
        return self._running and self._phase == CapturePhase.CAPTURING

    def feed_result(self, result: Dict):
        """
        喂入一帧的检测结果（仅在 CAPTURING 阶段有效）

        Args:
            result: 单帧检测结果字典，需包含：
                - has_coal (bool): 是否检测到积煤
                - coal_grids (int): 积煤格栅数
                - alert_level (str): 报警等级
                - fault_code (int): 故障码
        """
        if self._phase != CapturePhase.CAPTURING:
            return

        with self._lock:
            self._frame_results.append({
                "timestamp": time.time(),
                "has_coal": result.get("has_coal", False),
                "coal_grids": result.get("coal_grids", 0),
                "alert_level": result.get("alert_level", "UNKNOWN"),
                "fault_code": result.get("fault_code", 0),
            })

    def _finalize_window(self):
        """窗口结束，汇总投票"""
        with self._lock:
            frames = self._frame_results.copy()

        total = len(frames)
        if total == 0:
            self.last_window_result = WindowResult(
                fault_code=3,  # 画质问题（无帧）
                confidence="LOW",
            )
            logger.warning("[CaptureWindow] 窗口内无有效帧")
            self._notify_complete()
            return

        alarm_count = sum(1 for f in frames if f["has_coal"])
        alarm_ratio = alarm_count / total
        coal_grids_sum = sum(f["coal_grids"] for f in frames)
        fault_codes = [f["fault_code"] for f in frames if f["fault_code"] != 0]

        # 投票判定
        is_alarm = alarm_ratio >= self.config.vote_threshold

        # 置信度
        if alarm_ratio >= 0.8 or alarm_ratio <= 0.2:
            confidence = "HIGH"
        elif alarm_ratio >= 0.6 or alarm_ratio <= 0.4:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        # 故障码：取窗口内出现最多的非零故障码
        fault_code = 0
        if fault_codes:
            from collections import Counter
            fault_code = Counter(fault_codes).most_common(1)[0][0]

        result = WindowResult(
            total_frames=total,
            alarm_frames=alarm_count,
            alarm_ratio=alarm_ratio,
            is_alarm=is_alarm,
            confidence=confidence,
            fault_code=fault_code,
            coal_grids_avg=coal_grids_sum / total if total > 0 else 0,
            window_start=frames[0]["timestamp"] if frames else 0,
            window_end=frames[-1]["timestamp"] if frames else 0,
            frame_results=frames,
        )

        self.last_window_result = result

        logger.info(
            f"[CaptureWindow] 窗口判定: {total}帧, "
            f"报警{alarm_count}帧({alarm_ratio:.0%}), "
            f"{'→ 报警' if is_alarm else '→ 正常'}, "
            f"置信度={confidence}"
        )

        self._notify_complete()

    def _notify_complete(self):
        """通知回调"""
        if self.on_window_complete and self.last_window_result:
            try:
                self.on_window_complete(self.last_window_result)
            except Exception as e:
                logger.error(f"[CaptureWindow] 回调异常: {e}")

    def get_status(self) -> Dict[str, Any]:
        """获取当前状态（用于 API/UI）"""
        return {
            "phase": self._phase.value,
            "phase_display": self.phase_display,
            "running": self._running,
            "time_to_next": round(self.time_to_next_window, 1),
            "window_remaining": round(self.window_remaining, 1),
            "config": {
                "cycle_interval_s": self.config.cycle_interval_s,
                "window_duration_s": self.config.window_duration_s,
                "pre_delay_s": self.config.pre_delay_s,
                "vote_threshold": self.config.vote_threshold,
            },
            "last_result": {
                "total_frames": self.last_window_result.total_frames,
                "alarm_frames": self.last_window_result.alarm_frames,
                "alarm_ratio": round(self.last_window_result.alarm_ratio, 2),
                "is_alarm": self.last_window_result.is_alarm,
                "confidence": self.last_window_result.confidence,
            } if self.last_window_result else None,
        }
