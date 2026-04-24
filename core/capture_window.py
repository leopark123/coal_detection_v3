"""
翻车机积煤检测系统 V3.0 - 窗口采集控制器（PLC 触发模式）

采集时序（由 PLC 控制触发）：
  1. 翻车机翻转 → 回到原位（PLC 检测 Tipper_InPosition）
  2. PLC 延时 N 秒（Capture_Delay_Timer，在 PLC 梯形图中配置）
  3. PLC 写 PLC_CaptureCmd = 1（开始采集指令）
  4. 服务器读到 Cmd=1 → 写 Vision_CaptureState=1 → 开始连续采集
  5. 采集 window_duration_s 秒 → 多帧投票判定
  6. 服务器写结果（Vision_CanTip 等）+ Vision_CaptureState=2（判定完成）
  7. PLC 读到 State=2 → 写 PLC_CaptureCmd=0 → 复位
  8. 服务器读到 Cmd=0 → 写 Vision_CaptureState=0 → 回到空闲

PLC 标签：
  - PLC_CaptureCmd:      DINT  PLC→服务器（0=空闲, 1=开始采集, 2=取消）
  - Vision_CaptureState:  DINT  服务器→PLC（0=空闲, 1=采集中, 2=判定完成）
"""

import time
import threading
from enum import Enum
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field
from loguru import logger


class CapturePhase(str, Enum):
    """采集阶段"""
    IDLE = "idle"           # 空闲，等待 PLC 指令
    CAPTURING = "capturing" # 采集窗口内，正在采集
    JUDGING = "judging"     # 窗口结束，汇总判定中
    COMPLETE = "complete"   # 判定完成，等待 PLC 复位


@dataclass
class CaptureWindowConfig:
    """
    窗口采集配置

    注意：采集起止时机完全由 PLC 控制（PLC_CaptureCmd），
    服务器不做时间截止。以下 window_duration_s 仅用于 UI 显示。
    max_capture_s 是安全上限，防止 PLC 故障导致永远采集。
    """
    window_duration_s: float = 3.0    # UI 显示用（实际由 PLC 控制）
    vote_threshold: float = 0.6       # 投票阈值（0-1，超过该比例报警才输出报警）
    poll_interval_s: float = 0.2      # 轮询 PLC 指令的间隔（秒）
    max_capture_s: float = 60.0       # 安全上限：超过此时间强制停止采集（防 PLC 故障）

    # 兼容旧配置字段（不再使用但保留避免报错）
    cycle_interval_s: float = 30.0
    pre_delay_s: float = 2.0


@dataclass
class WindowResult:
    """单次采集窗口的汇总结果"""
    total_frames: int = 0
    alarm_frames: int = 0
    alarm_ratio: float = 0.0
    is_alarm: bool = False
    confidence: str = "NORMAL"
    fault_code: int = 0
    coal_grids_avg: float = 0.0
    window_start: float = 0.0
    window_end: float = 0.0
    frame_results: List[Dict] = field(default_factory=list)


class CaptureWindowController:
    """
    窗口采集控制器（PLC 触发模式）

    PLC 发出 PLC_CaptureCmd=1 时开始采集，
    采集 window_duration_s 秒后投票判定，
    将结果写回 PLC，等待 PLC 复位。

    使用方式：
        controller = CaptureWindowController(config, plc=plc)
        controller.start()

        # 在采集循环中：
        controller.tick()
        if controller.should_capture():
            result = detect(frame)
            controller.feed_result(result)
    """

    # PLC 标签名
    TAG_CAPTURE_CMD = "PLC_CaptureCmd"
    TAG_CAPTURE_STATE = "Vision_CaptureState"
    TAG_TIPPER_IN_POSITION = "Tipper_InPosition"

    # PLC_CaptureCmd 值
    CMD_IDLE = 0
    CMD_START = 1
    CMD_CANCEL = 2

    # Vision_CaptureState 值
    STATE_IDLE = 0
    STATE_CAPTURING = 1
    STATE_COMPLETE = 2

    def __init__(self, config: Optional[CaptureWindowConfig] = None, plc=None):
        self.config = config or CaptureWindowConfig()
        self.plc = plc  # PLC 驱动实例（需有 read/write 方法）
        self._phase = CapturePhase.IDLE
        self._window_start_time: float = 0.0
        self._frame_results: List[Dict] = []
        self._lock = threading.Lock()
        self._last_poll_time: float = 0.0

        # 最近一次窗口的汇总结果
        self.last_window_result: Optional[WindowResult] = None

        # 回调：窗口判定完成后通知外部
        self.on_window_complete: Optional[Callable[[WindowResult], None]] = None

        # PLC 重连后 State 重置标志（由 state_manager 设置，tick() 重试）
        self._needs_state_reset: bool = False

        self._running = False
        self._capture_count = 0  # 总采集窗口计数

    @property
    def phase(self) -> CapturePhase:
        return self._phase

    @property
    def phase_display(self) -> str:
        """中文状态显示"""
        return {
            CapturePhase.IDLE: "等待指令",
            CapturePhase.CAPTURING: "采集中",
            CapturePhase.JUDGING: "判定中",
            CapturePhase.COMPLETE: "等待复位",
        }.get(self._phase, "未知")

    @property
    def window_remaining(self) -> float:
        """当前窗口剩余秒数"""
        if self._phase != CapturePhase.CAPTURING:
            return 0
        elapsed = time.time() - self._window_start_time
        return max(0, self.config.window_duration_s - elapsed)

    def start(self):
        """启动窗口采集控制"""
        self._running = True
        self._phase = CapturePhase.IDLE
        # 初始化 PLC 状态
        self._write_plc_state(self.STATE_IDLE)
        logger.info(
            f"[CaptureWindow] 启动(PLC触发模式): "
            f"窗口={self.config.window_duration_s}s, "
            f"投票阈值={self.config.vote_threshold}"
        )

    def stop(self):
        """停止窗口采集"""
        self._running = False
        self._phase = CapturePhase.IDLE
        self._write_plc_state(self.STATE_IDLE)
        logger.info("[CaptureWindow] 已停止")

    def update_config(self, **kwargs):
        """运行时更新配置参数"""
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self.config, k):
                    setattr(self.config, k, v)

    def tick(self):
        """
        每帧调用一次，驱动状态机。

        IDLE: 轮询 PLC_CaptureCmd，读到 1 → CAPTURING
        CAPTURING: 采集窗口倒计时，到时间 → JUDGING → COMPLETE
        COMPLETE: 等待 PLC 复位 Cmd=0 → IDLE
        """
        if not self._running:
            return self._phase

        now = time.time()

        if self._phase == CapturePhase.IDLE:
            # 按间隔轮询 PLC 指令（节流）
            if now - self._last_poll_time >= self.config.poll_interval_s:
                self._last_poll_time = now

                # PLC 重连后 State 重置重试（受 poll_interval 节流）
                if self._needs_state_reset:
                    if self._write_plc_state(self.STATE_IDLE):
                        self._needs_state_reset = False
                        logger.info("[CaptureWindow] State=0 重试写入成功")

                cmd = self._read_plc_cmd()
                if cmd == self.CMD_START:
                    # PLC 发出采集指令
                    self._phase = CapturePhase.CAPTURING
                    self._window_start_time = now
                    self._frame_results.clear()
                    self._write_plc_state(self.STATE_CAPTURING)
                    self._capture_count += 1
                    logger.info(
                        f"[CaptureWindow] PLC 触发采集 #{self._capture_count}"
                    )

        elif self._phase == CapturePhase.CAPTURING:
            # 安全上限：防止 PLC 故障导致永远采集
            capture_elapsed = now - self._window_start_time
            if capture_elapsed >= self.config.max_capture_s:
                logger.error(
                    f"[CaptureWindow] 采集超过安全上限 {self.config.max_capture_s}s，强制停止！"
                )
                if self._frame_results:
                    self._finalize_window()
                    self._write_plc_state(self.STATE_COMPLETE)
                    self._phase = CapturePhase.COMPLETE
                else:
                    # 零帧超时：必须 fail-safe，写故障结果到 PLC
                    self.last_window_result = WindowResult(
                        fault_code=3,
                        confidence="LOW",
                        is_alarm=False,
                    )
                    logger.error("[CaptureWindow] 安全上限超时且零帧，写 fail-safe 结果")
                    self._notify_complete()  # 触发回调写 PLC（fault_code=3 → can_tip=False）
                    self._write_plc_state(self.STATE_COMPLETE)
                    self._phase = CapturePhase.COMPLETE
                return self._phase

            # 轮询 PLC：只看 PLC 指令决定是否停止
            if now - self._last_poll_time >= self.config.poll_interval_s:
                self._last_poll_time = now
                cmd = self._read_plc_cmd()

                if cmd == self.CMD_IDLE:
                    # PLC 把 CaptureCmd 置 0（回位信号消失触发 Rung 9）→ 停止采集
                    logger.info(
                        f"[CaptureWindow] PLC 停止采集 "
                        f"({len(self._frame_results)} frames)"
                    )
                    if self._frame_results:
                        self._finalize_window()
                        self._write_plc_state(self.STATE_COMPLETE)
                        self._phase = CapturePhase.COMPLETE
                        logger.info("[CaptureWindow] → COMPLETE, 等待 PLC 复位")
                    else:
                        self._phase = CapturePhase.IDLE
                        self._write_plc_state(self.STATE_IDLE)

                elif cmd == self.CMD_CANCEL:
                    logger.warning("[CaptureWindow] PLC 取消采集")
                    self._frame_results.clear()
                    self._phase = CapturePhase.IDLE
                    self._write_plc_state(self.STATE_IDLE)

        elif self._phase == CapturePhase.COMPLETE:
            # 等待 PLC 复位 CaptureCmd=0
            if now - self._last_poll_time >= self.config.poll_interval_s:
                self._last_poll_time = now
                cmd = self._read_plc_cmd()
                if cmd == self.CMD_IDLE:
                    self._phase = CapturePhase.IDLE
                    self._write_plc_state(self.STATE_IDLE)
                    logger.info("[CaptureWindow] PLC 已复位, → IDLE")

        return self._phase

    def should_capture(self) -> bool:
        """当前是否应该采集帧"""
        return self._running and self._phase == CapturePhase.CAPTURING

    def feed_result(self, result: Dict):
        """喂入一帧的检测结果（仅 CAPTURING 阶段有效）"""
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

    def _read_plc_cmd(self) -> int:
        """读取 PLC 采集指令"""
        if not self.plc:
            return self.CMD_IDLE
        try:
            val = self.plc.read(self.TAG_CAPTURE_CMD)
            if val is not None:
                return int(val)
        except Exception as e:
            logger.debug(f"[CaptureWindow] 读取 PLC_CaptureCmd 失败: {e}")
        return self.CMD_IDLE

    def _read_tipper_in_position(self) -> bool:
        """读取翻车机回位信号"""
        if not self.plc:
            return True  # 无 PLC 时默认回位
        try:
            val = self.plc.read(self.TAG_TIPPER_IN_POSITION)
            if val is not None:
                return bool(val)
        except Exception as e:
            logger.debug(f"[CaptureWindow] 读取 Tipper_InPosition 失败: {e}")
        return True  # 读取失败时不中断采集

    def _write_plc_state(self, state: int) -> bool:
        """写入采集状态到 PLC，返回是否成功"""
        if not self.plc:
            return False
        try:
            ok = self.plc.write(self.TAG_CAPTURE_STATE, state)
            return bool(ok)
        except Exception as e:
            logger.error(f"[CaptureWindow] 写入 Vision_CaptureState={state} 失败: {e}")
            return False

    def _finalize_window(self):
        """窗口结束，汇总投票"""
        with self._lock:
            frames = self._frame_results.copy()

        total = len(frames)
        if total == 0:
            self.last_window_result = WindowResult(
                fault_code=3,
                confidence="LOW",
            )
            logger.warning("[CaptureWindow] 窗口内无有效帧")
            self._notify_complete()
            return

        # 分离有效帧和故障帧
        valid_frames = [f for f in frames if f["fault_code"] == 0]
        fault_frames = [f for f in frames if f["fault_code"] != 0]
        valid_count = len(valid_frames)

        # 如果有效帧不足一半，整个窗口不可信
        if valid_count < total * 0.5:
            from collections import Counter
            fault_codes = [f["fault_code"] for f in fault_frames]
            most_common_fault = Counter(fault_codes).most_common(1)[0][0] if fault_codes else 3

            self.last_window_result = WindowResult(
                total_frames=total,
                alarm_frames=0,
                alarm_ratio=0.0,
                is_alarm=False,
                confidence="LOW",
                fault_code=most_common_fault,
                coal_grids_avg=0,
                window_start=frames[0]["timestamp"],
                window_end=frames[-1]["timestamp"],
                frame_results=frames,
            )
            logger.warning(
                f"[CaptureWindow] 窗口内有效帧不足: {valid_count}/{total}, "
                f"故障帧{len(fault_frames)}, 故障码={most_common_fault}, 置信度=LOW"
            )
            self._notify_complete()
            return

        # 只用有效帧投票
        alarm_count = sum(1 for f in valid_frames if f["has_coal"])
        alarm_ratio = alarm_count / valid_count
        coal_grids_sum = sum(f["coal_grids"] for f in valid_frames)

        # 投票判定
        is_alarm = alarm_ratio >= self.config.vote_threshold

        # 置信度（基于报警一致性）
        consistency = abs(alarm_ratio - 0.5) * 2  # 0.0~1.0
        if consistency >= 0.6:       # 报警率 <=20% 或 >=80%
            confidence = "HIGH"
        elif consistency >= 0.2:     # 报警率 <=40% 或 >=60%
            confidence = "MEDIUM"
        else:                        # 报警率 40%~60%
            confidence = "LOW"

        # 如果有故障帧但不占多数，降一级置信度
        if fault_frames and confidence == "HIGH":
            confidence = "MEDIUM"

        # 故障码：有效帧为主时故障码=0
        fault_code = 0

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
            f"[CaptureWindow] 窗口判定: {total}帧(有效{valid_count},故障{len(fault_frames)}), "
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
            "window_remaining": round(self.window_remaining, 1),
            "capture_count": self._capture_count,
            "config": {
                "window_duration_s": self.config.window_duration_s,
                "vote_threshold": self.config.vote_threshold,
            },
            "last_result": {
                "total_frames": self.last_window_result.total_frames,
                "alarm_frames": self.last_window_result.alarm_frames,
                "alarm_ratio": round(self.last_window_result.alarm_ratio, 2),
                "is_alarm": self.last_window_result.is_alarm,
                "confidence": self.last_window_result.confidence,
                "window_end": self.last_window_result.window_end,
            } if self.last_window_result else None,
        }
