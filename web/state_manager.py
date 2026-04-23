"""
翻车机积煤检测系统 V3.0 - 中央状态管理器

管理多台翻车机 × 多个漏斗的运行时状态。

层次结构：
  StateManager
  ├── MachineState（翻车机，含 PLC）
  │   ├── FunnelState（漏斗，含 camera + detector）
  │   └── ...
  └── ...
"""

import asyncio
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, List

from loguru import logger

from config.config import Config
from config.devices_config import DevicesConfig, MachineConfig, FunnelConfig, build_funnel_config
from drivers.factory import create_camera, create_plc
from algo.device_detector import DeviceDetector
from web.common import StreamAppState, append_bounded
from core.capture_window import CaptureWindowController, CaptureWindowConfig
from web.archive_worker import ArchiveWorker
from web.archive_janitor import ArchiveJanitor


class FunnelState(StreamAppState):
    """
    单个漏斗的运行时状态

    继承 StreamAppState 以兼容 run_websocket_stream()。
    包含：camera, detector, config, is_running, detection_history 等。
    """

    def __init__(self, machine_id: str, funnel_id: str):
        super().__init__()
        self.machine_id = machine_id
        self.funnel_id = funnel_id
        self.last_result = None
        self.last_frame = None
        self._last_result_id: int = 0
        self.coal_detections: int = 0
        self.vision_enabled: bool = True
        self.capture_controller: Optional[CaptureWindowController] = None
        # 故障信息
        self.fault_info: Dict[str, Any] = {
            "camera": {"status": "unknown", "error": None, "since": None, "reconnect_attempts": 0},
            "detector": {"status": "unknown"},
        }
        self._reconnect_attempts: int = 0


@dataclass
class MachineState:
    """单台翻车机的运行时状态（PLC + N 个漏斗）"""
    machine_id: str
    machine_config: MachineConfig
    plc: Any = None
    funnels: Dict[str, FunnelState] = field(default_factory=dict)
    fault_info: Dict[str, Any] = field(default_factory=lambda: {
        "plc": {"status": "unknown", "error": None, "since": None},
    })

    @property
    def is_any_alarm(self) -> bool:
        return any(
            fs.last_result and getattr(fs.last_result, "device_has_coal", False)
            for fs in self.funnels.values()
        )

    @property
    def worst_alert_level(self) -> str:
        levels = ["NORMAL", "ATTENTION", "WARNING", "CRITICAL"]
        worst = 0
        for fs in self.funnels.values():
            if fs.last_result:
                lvl = getattr(fs.last_result, "device_alert_level", "NORMAL")
                if lvl in levels:
                    worst = max(worst, levels.index(lvl))
        return levels[worst]

    @property
    def plc_connected(self) -> bool:
        return hasattr(self.plc, "is_connected") and self.plc.is_connected


class StateManager:
    """
    中央状态管理器

    管理所有翻车机和漏斗的生命周期。
    由 unified_app.py 的 lifespan 调用 initialize() / shutdown()。
    """

    def __init__(self):
        self.machines: Dict[str, MachineState] = {}
        self.devices_config: Optional[DevicesConfig] = None
        self.base_config: Optional[Config] = None
        self._yaml_path: Optional[str] = None
        self._bg_workers: Dict[str, threading.Thread] = {}
        self._bg_stop_event = threading.Event()
        self._start_time: float = time.time()
        # 故障事件日志（最近 50 条）
        self._fault_events: List[Dict] = []
        self._fault_events_max = 50
        # 归档（所有漏斗共享一个 worker + janitor）
        self.archive_worker: Optional[ArchiveWorker] = None
        self.archive_janitor: Optional[ArchiveJanitor] = None

    def add_fault_event(self, device: str, event_type: str, message: str):
        """记录一条故障事件"""
        entry = {
            "timestamp": time.time(),
            "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
            "device": device,
            "type": event_type,
            "message": message,
        }
        self._fault_events.append(entry)
        if len(self._fault_events) > self._fault_events_max:
            self._fault_events = self._fault_events[-self._fault_events_max:]

    def initialize(self, devices_config: DevicesConfig, base_config: Config, yaml_path: str = None):
        """
        初始化所有翻车机和漏斗

        为每个漏斗创建独立的 camera 和 detector 实例。
        为每台翻车机创建独立的 PLC 连接。
        为整个系统创建一个归档 worker（所有漏斗共享）+ 一个清理 janitor。
        """
        self.devices_config = devices_config
        self.base_config = base_config
        self._yaml_path = yaml_path

        # 启动归档 worker（共享给所有漏斗的 capture_controller）
        # 启动失败时 worker 标记禁用，不影响主检测
        if bool(getattr(base_config, "archive_enable", True)):
            try:
                self.archive_worker = ArchiveWorker(base_config)
                if not self.archive_worker.start():
                    logger.warning("[StateManager] 归档 worker 启动失败，归档禁用")
                    self.archive_worker = None
                else:
                    # Janitor 依赖 worker 已启动（共用 save_dir 预检结果）
                    self.archive_janitor = ArchiveJanitor(base_config)
                    self.archive_janitor.start()
            except Exception as e:
                logger.error(f"[StateManager] 归档初始化异常，归档禁用: {e}")
                self.archive_worker = None
                self.archive_janitor = None
        else:
            logger.info("[StateManager] 归档已通过配置禁用 (archive_enable=False)")

        for mc in devices_config.machines:
            ms = MachineState(machine_id=mc.id, machine_config=mc)

            # 创建 PLC（每台翻车机一个）
            plc_cfg = Config()
            plc_cfg.DEV_MODE = base_config.DEV_MODE
            plc_cfg.PLC_IP = mc.plc_ip
            plc_cfg.PLC_TIMEOUT_MS = mc.plc_timeout_ms
            plc_cfg.PLC_HEARTBEAT_INTERVAL_MS = mc.plc_heartbeat_interval_ms
            try:
                ms.plc = create_plc(plc_cfg)
                logger.info(f"[StateManager] PLC {mc.plc_ip} 已连接 ({mc.name})")
                self.add_fault_event(mc.name, "plc_ok", f"PLC 连接成功 ({mc.plc_ip})")
                self._register_plc_callback(ms, mc)
            except ImportError:
                raise
            except Exception as e:
                logger.error(f"[StateManager] PLC {mc.plc_ip} 连接失败: {e}")
                self.add_fault_event(mc.name, "plc", f"PLC 连接失败: {e}")
                ms.fault_info["plc"] = {"status": "offline", "error": str(e), "since": time.time()}

            # 创建每个漏斗的 camera + detector + capture_controller
            for fc in mc.funnels:
                self._create_funnel(ms, mc, fc)

            self.machines[mc.id] = ms

        total_funnels = sum(len(ms.funnels) for ms in self.machines.values())
        logger.info(
            f"[StateManager] 初始化完成: {len(self.machines)} 台翻车机, "
            f"{total_funnels} 个漏斗"
        )

    def shutdown(self):
        """释放所有资源"""
        self.stop_background_workers()
        for ms in self.machines.values():
            for fs in ms.funnels.values():
                fs.stop_runtime(app_tag=f"[{fs.machine_id}/{fs.funnel_id}]")
            if ms.plc and hasattr(ms.plc, "close"):
                try:
                    ms.plc.close()
                except Exception as e:
                    logger.error(f"[StateManager] PLC 关闭失败 ({ms.machine_id}): {e}")

        # 停止归档 janitor 再停 worker（janitor 可能正在读磁盘）
        if self.archive_janitor is not None:
            try:
                self.archive_janitor.stop()
            except Exception as e:
                logger.error(f"[StateManager] 归档 janitor 关闭失败: {e}")
            self.archive_janitor = None

        if self.archive_worker is not None:
            try:
                self.archive_worker.stop(timeout=5.0)
            except Exception as e:
                logger.error(f"[StateManager] 归档 worker 关闭失败: {e}")
            self.archive_worker = None

        self.machines.clear()
        logger.info("[StateManager] 所有资源已释放")

    # ═══════════════════════════════════════════════════════════════
    # 后台检测 worker（独立于 WebSocket，确保无人看页面时也能检测）
    # ═══════════════════════════════════════════════════════════════

    def start_background_workers(self):
        """
        为每个已就绪的漏斗启动后台检测线程。

        后台 worker 持续驱动：tick() → grab → detect → feed_result → PLC 写入
        即使没有浏览器连接也能响应 PLC 采集指令。
        """
        self._bg_stop_event.clear()
        for mid, ms in self.machines.items():
            for fid, fs in ms.funnels.items():
                if not fs.is_running:
                    continue
                key = f"{mid}/{fid}"
                t = threading.Thread(
                    target=self._bg_detection_loop,
                    args=(ms, fs, key),
                    daemon=True,
                    name=f"bg-detect-{key}",
                )
                t.start()
                self._bg_workers[key] = t
                logger.info(f"[StateManager] 后台检测 worker 已启动: {key}")

    def stop_background_workers(self):
        """停止所有后台检测 worker"""
        self._bg_stop_event.set()
        for key, t in self._bg_workers.items():
            t.join(timeout=5.0)
            if t.is_alive():
                logger.warning(f"[StateManager] 后台 worker {key} 未能及时退出")
        self._bg_workers.clear()
        logger.info("[StateManager] 所有后台 worker 已停止")

    def _bg_detection_loop(self, ms: "MachineState", fs: "FunnelState", tag: str):
        """
        单个漏斗的后台检测循环。

        职责：
        1. 驱动 CaptureWindowController 状态机 (tick)
        2. 在采集窗口内抓帧、检测、喂结果
        3. 窗口结束后由 on_window_complete 回调写 PLC

        与 WebSocket 流的关系：
        - 后台 worker 负责检测逻辑和 PLC 写入（核心功能）
        - WebSocket 流负责视频推送和 UI 展示（展示功能）
        - 两者共享 fs.last_result，WebSocket 流读取后台产生的结果
        """
        logger.info(f"[BgWorker:{tag}] 启动")
        interval = getattr(fs.config, 'frame_interval', 0.1)

        while not self._bg_stop_event.is_set() and fs.is_running:
            try:
                # 视觉停用时休眠
                if not fs.vision_enabled:
                    self._bg_stop_event.wait(1.0)
                    continue

                cc = fs.capture_controller
                if not cc:
                    self._bg_stop_event.wait(1.0)
                    continue

                # 无相机或断连时自动重连
                # 策略：
                #   从未连接过(_ever_connected=False) → 不重连（IP不存在，避免pypylon枚举冲突）
                #   曾连接过(_ever_connected=True)   → 快速5次(10秒) → 慢速(60秒)永不放弃
                if not fs.camera or not getattr(fs.camera, 'is_connected', False):
                    FAST_MAX = 5
                    FAST_INTERVAL = 10.0
                    SLOW_INTERVAL = 60.0

                    # 从未连接成功过的相机不重连（IP 不存在的漏斗）
                    ever_connected = getattr(fs, '_ever_connected', False)
                    if not ever_connected:
                        if fs.fault_info["camera"]["status"] != "not_available":
                            fs.fault_info["camera"] = {
                                "status": "not_available",
                                "error": getattr(fs.camera, 'last_error', '相机未初始化') if fs.camera else "相机未初始化",
                                "since": time.time(),
                                "reconnect_attempts": 0,
                            }
                            logger.info(f"[BgWorker:{tag}] 相机从未连接成功，不重连")
                            self.add_fault_event(tag, "camera", "相机从未连接成功(IP不存在)，不重连")
                        self._bg_stop_event.wait(SLOW_INTERVAL)
                        continue

                    # 曾连接过 → 断电/更换后自动重连，永不放弃
                    if fs.fault_info["camera"]["status"] != "disconnected":
                        cam_err = getattr(fs.camera, 'last_error', None) if fs.camera else "连接断开"
                        fs.fault_info["camera"] = {
                            "status": "disconnected",
                            "error": cam_err,
                            "since": time.time(),
                            "reconnect_attempts": 0,
                        }
                        self.add_fault_event(tag, "camera", f"相机断开: {cam_err or '连接断开'}")

                    if not fs.camera or not hasattr(fs.camera, 'reconnect'):
                        self._bg_stop_event.wait(SLOW_INTERVAL)
                        continue

                    fs._reconnect_attempts += 1
                    fs.fault_info["camera"]["reconnect_attempts"] = fs._reconnect_attempts
                    is_fast = fs._reconnect_attempts <= FAST_MAX
                    wait_time = FAST_INTERVAL if is_fast else SLOW_INTERVAL
                    phase = f"{fs._reconnect_attempts}/{FAST_MAX}" if is_fast else "慢速"

                    # 慢速阶段降低日志频率（每10次打一次）
                    if is_fast or fs._reconnect_attempts % 10 == 0:
                        logger.info(f"[BgWorker:{tag}] 相机重连 ({phase}, 第{fs._reconnect_attempts}次)")
                    try:
                        success = fs.camera.reconnect()
                        if success:
                            fs._reconnect_attempts = 0
                            fs._ever_connected = True
                            fs.fault_info["camera"] = {"status": "connected", "error": None, "since": None, "reconnect_attempts": 0}
                            logger.info(f"[BgWorker:{tag}] 相机重连成功")
                            self.add_fault_event(tag, "camera_ok", f"相机重连成功(第{fs._reconnect_attempts+1}次尝试后)")
                        else:
                            fs.fault_info["camera"]["error"] = getattr(fs.camera, 'last_error', '重连失败')
                            self._bg_stop_event.wait(wait_time)
                            continue
                    except Exception as e:
                        fs.fault_info["camera"]["error"] = str(e)
                        self._bg_stop_event.wait(wait_time)
                        continue
                else:
                    # 相机正常，更新状态
                    if fs.fault_info["camera"]["status"] != "connected":
                        fs.fault_info["camera"] = {"status": "connected", "error": None, "since": None, "reconnect_attempts": 0}

                # 驱动状态机
                cc.tick()

                if cc.should_capture():
                    # 在采集窗口内：抓帧 → 检测 → 喂结果
                    if not fs.camera or not getattr(fs.camera, 'is_connected', False):
                        self._bg_stop_event.wait(0.5)
                        continue

                    try:
                        frame = fs.camera.grab()
                    except Exception:
                        self._bg_stop_event.wait(0.5)
                        continue

                    try:
                        result = fs.detector.detect_device(frame, fs.detection_count)
                    except Exception as e:
                        logger.error(f"[BgWorker:{tag}] 检测异常: {e}")
                        self._bg_stop_event.wait(0.5)
                        continue

                    # 更新状态
                    fs.detection_count += 1
                    if getattr(result, "device_has_coal", False):
                        fs.coal_detections += 1
                    fs.last_result = result
                    fs.last_frame = frame
                    fs._last_result_id += 1

                    # 写入历史记录
                    history_entry = {
                        "frame_id": fs.detection_count,
                        "timestamp": time.time(),
                        "device_has_coal": getattr(result, "device_has_coal", False),
                        "coal_grids": getattr(result, "coal_grids", 0),
                        "alert_level": getattr(result, "device_alert_level", "UNKNOWN"),
                        "process_time": getattr(result, "process_time_ms", 0.0),
                    }
                    append_bounded(fs.detection_history, history_entry, max_items=100)

                    # 喂入窗口控制器（frame 用于窗口结束时选代表帧归档）
                    cc.feed_result(
                        {
                            "has_coal": getattr(result, "device_has_coal", False),
                            "coal_grids": getattr(result, "coal_grids", 0),
                            "alert_level": getattr(result, "device_alert_level", "UNKNOWN"),
                            "fault_code": getattr(result, "fault_code", 0),
                        },
                        frame=frame,
                    )

                    # 控制帧率
                    self._bg_stop_event.wait(interval)
                else:
                    # 窗口外：低频抓一帧供预览（不做检测）
                    if fs.camera and getattr(fs.camera, 'is_connected', False):
                        try:
                            fs.last_frame = fs.camera.grab()
                        except Exception:
                            pass
                    self._bg_stop_event.wait(0.5)

            except Exception as e:
                logger.error(f"[BgWorker:{tag}] 循环异常: {e}")
                self._bg_stop_event.wait(2.0)

        logger.info(f"[BgWorker:{tag}] 已退出")

    def _start_funnel_worker(self, ms: "MachineState", fs: "FunnelState"):
        """为单个漏斗启动后台 worker（如果条件满足）"""
        if not fs.is_running:
            return
        key = f"{ms.machine_id}/{fs.funnel_id}"
        if key in self._bg_workers and self._bg_workers[key].is_alive():
            return  # 已在运行
        t = threading.Thread(
            target=self._bg_detection_loop,
            args=(ms, fs, key),
            daemon=True,
            name=f"bg-detect-{key}",
        )
        t.start()
        self._bg_workers[key] = t
        logger.info(f"[StateManager] 后台 worker 已启动: {key}")

    def _stop_funnel_worker(self, machine_id: str, funnel_id: str):
        """停止单个漏斗的后台 worker"""
        key = f"{machine_id}/{funnel_id}"
        t = self._bg_workers.pop(key, None)
        if t and t.is_alive():
            t.join(timeout=3.0)
            if t.is_alive():
                logger.warning(f"[StateManager] 后台 worker {key} 未能及时退出")
            else:
                logger.info(f"[StateManager] 后台 worker 已停止: {key}")

    # ═══════════════════════════════════════════════════════════════
    # 动态增删（管理员 API 调用）
    # ═══════════════════════════════════════════════════════════════

    def add_machine(self, mc: MachineConfig):
        """运行时添加翻车机（创建 PLC + 所有漏斗）"""
        if mc.id in self.machines:
            raise ValueError(f"翻车机 {mc.id} 已存在")

        ms = MachineState(machine_id=mc.id, machine_config=mc)

        # PLC
        plc_cfg = Config()
        plc_cfg.DEV_MODE = self.base_config.DEV_MODE
        plc_cfg.PLC_IP = mc.plc_ip
        plc_cfg.PLC_TIMEOUT_MS = mc.plc_timeout_ms
        plc_cfg.PLC_HEARTBEAT_INTERVAL_MS = mc.plc_heartbeat_interval_ms
        try:
            ms.plc = create_plc(plc_cfg)
            logger.info(f"[StateManager] PLC {mc.plc_ip} 已连接 ({mc.name})")
            self.add_fault_event(mc.name, "plc_ok", f"PLC 连接成功 ({mc.plc_ip})")
            self._register_plc_callback(ms, mc)
        except Exception as e:
            logger.error(f"[StateManager] PLC {mc.plc_ip} 连接失败: {e}")
            self.add_fault_event(mc.name, "plc", f"PLC 连接失败: {e}")
            ms.fault_info["plc"] = {"status": "offline", "error": str(e), "since": time.time()}

        # 漏斗
        for fc in mc.funnels:
            self._create_funnel(ms, mc, fc)

        self.machines[mc.id] = ms

        # 启动后台 worker
        for fid, fs in ms.funnels.items():
            self._start_funnel_worker(ms, fs)

        # 同步到配置并持久化
        self.devices_config.add_machine(mc)
        self._save_config()

        logger.info(f"[StateManager] 翻车机已添加: {mc.name} ({len(mc.funnels)} 个漏斗)")

    def remove_machine(self, machine_id: str):
        """运行时移除翻车机（停止所有漏斗，关闭 PLC）"""
        ms = self.machines.get(machine_id)
        if not ms:
            raise ValueError(f"翻车机 {machine_id} 不存在")

        # 停止后台 worker + 漏斗
        for fid, fs in ms.funnels.items():
            fs.is_running = False  # 让 worker 退出循环
            self._stop_funnel_worker(machine_id, fid)
            fs.stop_runtime(app_tag=f"[{machine_id}/{fid}]")

        # 关闭 PLC
        if ms.plc and hasattr(ms.plc, "close"):
            try:
                ms.plc.close()
            except Exception as e:
                logger.error(f"[StateManager] PLC 关闭失败: {e}")

        del self.machines[machine_id]

        # 同步到配置并持久化
        self.devices_config.remove_machine(machine_id)
        self._save_config()

        logger.info(f"[StateManager] 翻车机已移除: {machine_id}")

    def add_funnel(self, machine_id: str, fc: FunnelConfig):
        """运行时给翻车机添加漏斗"""
        ms = self.machines.get(machine_id)
        if not ms:
            raise ValueError(f"翻车机 {machine_id} 不存在")
        if fc.id in ms.funnels:
            raise ValueError(f"漏斗 {fc.id} 已存在于 {machine_id}")

        self._create_funnel(ms, ms.machine_config, fc)

        # 启动后台 worker
        fs = ms.funnels.get(fc.id)
        if fs:
            self._start_funnel_worker(ms, fs)

        # 同步到配置并持久化
        self.devices_config.add_funnel(machine_id, fc)
        self._save_config()

        logger.info(f"[StateManager] 漏斗已添加: {machine_id}/{fc.name}")

    def remove_funnel(self, machine_id: str, funnel_id: str):
        """运行时从翻车机移除漏斗"""
        ms = self.machines.get(machine_id)
        if not ms:
            raise ValueError(f"翻车机 {machine_id} 不存在")
        fs = ms.funnels.get(funnel_id)
        if not fs:
            raise ValueError(f"漏斗 {funnel_id} 不存在于 {machine_id}")

        fs.is_running = False  # 让 worker 退出
        self._stop_funnel_worker(machine_id, funnel_id)
        fs.stop_runtime(app_tag=f"[{machine_id}/{funnel_id}]")
        del ms.funnels[funnel_id]

        # 同步到配置并持久化
        self.devices_config.remove_funnel(machine_id, funnel_id)
        self._save_config()

        logger.info(f"[StateManager] 漏斗已移除: {machine_id}/{funnel_id}")

    def update_thresholds(self, params: dict):
        """
        更新检测阈值（立即生效，应用到所有漏斗的检测器）

        支持的参数：
        - GRID_VISIBLE_THRESHOLD, COAL_COVERAGE_THRESHOLD
        - VOTE_WINDOW_SIZE, VOTE_THRESHOLD
        """
        allowed = {
            "GRID_VISIBLE_THRESHOLD", "COAL_COVERAGE_THRESHOLD",
            "VOTE_WINDOW_SIZE", "VOTE_THRESHOLD",
        }
        # 边界校验
        validators = {
            "GRID_VISIBLE_THRESHOLD": lambda v: 0.0 < v <= 1.0,
            "COAL_COVERAGE_THRESHOLD": lambda v: 0.0 < v <= 1.0,
            "VOTE_WINDOW_SIZE": lambda v: isinstance(v, (int, float)) and 1 <= v <= 20,
            "VOTE_THRESHOLD": lambda v: isinstance(v, (int, float)) and 1 <= v <= 20,
        }
        applied = {}
        for key, value in params.items():
            if key not in allowed:
                continue
            validator = validators.get(key)
            if validator and not validator(value):
                raise ValueError(f"参数 {key}={value} 超出有效范围")
            # 更新 base_config
            if hasattr(self.base_config, key):
                setattr(self.base_config, key, value)
            # 更新每个漏斗的 config
            for ms in self.machines.values():
                for fs in ms.funnels.values():
                    if fs.config and hasattr(fs.config, key):
                        setattr(fs.config, key, value)
            applied[key] = value

        # 组合约束校验：VOTE_THRESHOLD 不能大于 VOTE_WINDOW_SIZE
        cfg = self.base_config or Config()
        vt = applied.get("VOTE_THRESHOLD", getattr(cfg, "VOTE_THRESHOLD", 3))
        vw = applied.get("VOTE_WINDOW_SIZE", getattr(cfg, "VOTE_WINDOW_SIZE", 5))
        if vt > vw:
            raise ValueError(f"VOTE_THRESHOLD({vt}) 不能大于 VOTE_WINDOW_SIZE({vw})")

        logger.info(f"[StateManager] 阈值已更新: {applied}")
        return applied

    def get_thresholds(self) -> dict:
        """获取当前检测阈值"""
        cfg = self.base_config or Config()
        return {
            "GRID_VISIBLE_THRESHOLD": cfg.GRID_VISIBLE_THRESHOLD,
            "COAL_COVERAGE_THRESHOLD": cfg.COAL_COVERAGE_THRESHOLD,
            "VOTE_WINDOW_SIZE": cfg.VOTE_WINDOW_SIZE,
            "VOTE_THRESHOLD": cfg.VOTE_THRESHOLD,
        }

    # ═══════════════════════════════════════════════════════════════
    # 视觉采集启停控制
    # ═══════════════════════════════════════════════════════════════

    def set_vision_enabled(self, machine_id: str, enabled: bool) -> dict:
        """
        启用或停用某台翻车机的视觉采集

        停用时：
        - 所有漏斗停止采集
        - PLC 写入 Vision_Enable=False，梯形图中 Allow_Tip 强制=1
        - 心跳继续运行（保持视觉系统在线状态）

        启用时：
        - 所有漏斗恢复采集
        - PLC 写入 Vision_Enable=True，恢复正常检测逻辑
        """
        ms = self.machines.get(machine_id)
        if not ms:
            raise ValueError(f"翻车机 {machine_id} 不存在")

        # 更新每个漏斗的采集状态（不改 is_running，WebSocket 保持连接）
        for fs in ms.funnels.values():
            fs.vision_enabled = enabled
            if not enabled and fs.capture_controller:
                fs.capture_controller.stop()
            elif enabled and fs.capture_controller:
                fs.capture_controller.start()

        # 通知 PLC（检查写入结果，失败则回滚）
        if not ms.plc:
            # PLC 不存在，回滚并报错
            for fs in ms.funnels.values():
                fs.vision_enabled = not enabled
                if fs.capture_controller:
                    if not enabled:
                        fs.capture_controller.start()
                    else:
                        fs.capture_controller.stop()
            logger.error(f"[StateManager] PLC 不存在，无法切换 Vision_Enable")
            return {
                "machine_id": machine_id,
                "vision_enabled": not enabled,
                "error": "PLC 未连接，操作失败",
            }

        plc_ok = False
        if hasattr(ms.plc, "set_vision_enable"):
            plc_ok = ms.plc.set_vision_enable(enabled)
        elif hasattr(ms.plc, "write"):
            plc_ok = ms.plc.write("Vision_Enable", enabled)
            if plc_ok and not enabled:
                ms.plc.write("Vision_CanTip", True)
                ms.plc.write("Vision_FaultCode", 0)
                ms.plc.write("Vision_ResultValid", True)

        if not plc_ok:
            # PLC 写入失败，回滚内存状态
            for fs in ms.funnels.values():
                fs.vision_enabled = not enabled
                if fs.capture_controller:
                    if not enabled:
                        fs.capture_controller.start()
                    else:
                        fs.capture_controller.stop()
            logger.error(f"[StateManager] PLC 写入 Vision_Enable={enabled} 失败，已回滚")
            return {
                "machine_id": machine_id,
                "vision_enabled": not enabled,
                "error": "PLC 写入失败，操作已回滚",
            }

        status = "启用" if enabled else "停用"
        logger.info(f"[StateManager] 视觉采集已{status}: {ms.machine_config.name}")

        return {
            "machine_id": machine_id,
            "vision_enabled": enabled,
            "message": f"视觉采集已{status}",
        }

    def get_vision_enabled(self, machine_id: str) -> bool:
        """获取某台翻车机的视觉采集状态"""
        ms = self.machines.get(machine_id)
        if not ms:
            return False
        # 只要有一个漏斗启用就算启用
        return any(fs.vision_enabled for fs in ms.funnels.values())

    # ═══════════════════════════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════════════════════════

    def _register_plc_callback(self, ms: MachineState, mc: MachineConfig):
        """注册 PLC 运行时状态变化回调"""
        if not ms.plc or not hasattr(ms.plc, 'on_status_change'):
            return

        def _cb(status, msg, _name=mc.name, _ms=ms):
            if status == "disconnected":
                self.add_fault_event(_name, "plc", msg)
                _ms.fault_info["plc"] = {"status": "offline", "error": msg, "since": time.time()}
            elif status == "connected":
                self.add_fault_event(_name, "plc_ok", msg)
                _ms.fault_info["plc"] = {"status": "online", "error": None, "since": None}
                # PLC 重连后重置所有漏斗的采集状态
                # 防止 CaptureState 残留（断连时写 State 失败→PLC 不发下次 Cmd→采集停滞）
                # 重置所有漏斗的采集状态（不 sleep，不阻塞心跳线程）
                # 先尝试一次写入，失败则设标志由 tick() 异步重试
                from core.capture_window import CapturePhase
                for _fs in _ms.funnels.values():
                    cc = _fs.capture_controller
                    if cc:
                        cc._phase = CapturePhase.IDLE
                        ok = cc._write_plc_state(0)
                        if ok:
                            cc._needs_state_reset = False
                            logger.info(f"[StateManager] PLC重连后重置 {_fs.funnel_id} CaptureState=0")
                        else:
                            cc._needs_state_reset = True
                            logger.warning(f"[StateManager] {_fs.funnel_id} State=0 首次写入失败，由 tick() 重试")

        ms.plc.on_status_change = _cb

    def _create_funnel(self, ms: MachineState, mc: MachineConfig, fc: FunnelConfig):
        """内部：创建单个漏斗的 camera + detector"""
        funnel_cfg = build_funnel_config(self.base_config, mc, fc)
        fs = FunnelState(machine_id=mc.id, funnel_id=fc.id)
        fs.config = funnel_cfg

        try:
            fs.camera = create_camera(funnel_cfg)
        except ImportError:
            raise  # 生产环境依赖缺失，必须终止启动
        except Exception as e:
            logger.error(f"[StateManager] 相机 {fc.camera_ip} 连接失败: {e}")

        try:
            fs.detector = DeviceDetector(
                funnel_cfg,
                device_id=f"{mc.id}/{fc.id}",
                grid_count=fc.grid_count,
            )
        except Exception as e:
            logger.error(f"[StateManager] 检测器创建失败 ({mc.name}/{fc.name}): {e}")

        # 窗口采集控制器（PLC 触发模式）
        cap_cfg = CaptureWindowConfig(
            window_duration_s=getattr(fc, 'capture_window_s', 3.0),
            vote_threshold=getattr(fc, 'capture_vote_threshold', 0.6),
        )
        fs.capture_controller = CaptureWindowController(
            cap_cfg,
            plc=ms.plc,
            archive_worker=self.archive_worker,
            funnel_tag=f"{mc.id}_{fc.id}",
        )

        # 设置窗口完成回调：写检测结果到 PLC
        def _on_window_complete(result, _ms=ms, _fs=fs):
            if _ms.plc and hasattr(_ms.plc, 'send_detection_result'):
                _ms.plc.send_detection_result(
                    coal_present=result.is_alarm,
                    confidence=result.confidence,
                    need_manual=(result.confidence == "LOW"),
                    fault_code=result.fault_code,
                )
        fs.capture_controller.on_window_complete = _on_window_complete

        cam_ok = fs.camera and getattr(fs.camera, 'is_connected', False)
        fs._ever_connected = cam_ok  # 标记初始化时是否成功连过
        fs.is_running = bool(fs.camera and fs.detector)
        if fs.is_running:
            fs.capture_controller.start()
        if not cam_ok and fs.camera:
            fs.fault_info["camera"] = {
                "status": "not_available",
                "error": getattr(fs.camera, 'last_error', '初始化连接失败'),
                "since": time.time(),
                "reconnect_attempts": 0,
            }
        ms.funnels[fc.id] = fs

    def _save_config(self):
        """
        内部：将当前拓扑配置持久化到 devices.yaml

        Raises:
            RuntimeError: 保存失败时抛出，调用方需处理
        """
        if self._yaml_path:
            try:
                self.devices_config.to_yaml(self._yaml_path)
                logger.debug(f"[StateManager] 配置已保存: {self._yaml_path}")
            except Exception as e:
                logger.error(f"[StateManager] 配置保存失败: {e}")
                raise RuntimeError(
                    f"配置保存失败（内存已生效但未持久化，重启后丢失）: {e}"
                ) from e

    # ═══════════════════════════════════════════════════════════════
    # 查询方法
    # ═══════════════════════════════════════════════════════════════

    def get_machine_state(self, machine_id: str) -> Optional[MachineState]:
        return self.machines.get(machine_id)

    def get_funnel_state(self, machine_id: str, funnel_id: str) -> Optional[FunnelState]:
        ms = self.machines.get(machine_id)
        if ms:
            return ms.funnels.get(funnel_id)
        return None

    def get_all_faults(self) -> dict:
        """获取全部故障详情 + 系统状态 + 故障事件日志"""
        import gc
        faults = []
        for mid, ms in self.machines.items():
            mc = ms.machine_config
            # PLC
            if not ms.plc_connected:
                plc_info = ms.fault_info.get("plc", {})
                faults.append({
                    "device": mc.name, "type": "plc",
                    "machine_id": mid,
                    "status": "offline",
                    "status_display": "离线",
                    "ip": mc.plc_ip,
                    "error": plc_info.get("error", "连接断开"),
                    "since": plc_info.get("since"),
                    "duration_min": int((time.time() - plc_info["since"]) / 60) if plc_info.get("since") else 0,
                    "reconnect_attempts": 0,
                    "detail": f"心跳: 停止, 写入失败: {getattr(ms.plc, 'write_count', 0) if ms.plc else 0}次",
                })
            # 漏斗相机
            for fid, fs in ms.funnels.items():
                fc = next((f for f in mc.funnels if f.id == fid), None)
                fname = fc.name if fc else fid
                cam = fs.fault_info.get("camera", {})
                if cam.get("status") in ("disconnected", "not_available", "stopped"):
                    since = cam.get("since")
                    dur_min = int((time.time() - since) / 60) if since else 0
                    status_map = {
                        "disconnected": f"重连中 (第{cam.get('reconnect_attempts',0)}次)",
                        "not_available": "未连接(IP不存在)",
                        "stopped": "已停止重连",
                    }
                    faults.append({
                        "device": f"{mc.name}/{fname}", "type": "camera",
                        "machine_id": mid,
                        "funnel_id": fid,
                        "status": cam["status"],
                        "status_display": status_map.get(cam["status"], cam["status"]),
                        "ip": fc.camera_ip if fc else "?",
                        "error": cam.get("error", "未知"),
                        "since": since,
                        "duration_min": dur_min,
                        "reconnect_attempts": cam.get("reconnect_attempts", 0),
                    })
        # 系统状态
        uptime = time.time() - self._start_time
        system = {
            "uptime_s": round(uptime),
            "uptime_h": round(uptime / 3600, 1),
            "machines": len(self.machines),
            "gc_collections": sum(s.get('collections', 0) for s in gc.get_stats()),
        }
        try:
            import psutil
            proc = psutil.Process()
            system["rss_mb"] = round(proc.memory_info().rss / 1024 / 1024, 1)
            system["threads"] = proc.num_threads()
        except ImportError:
            pass

        # 采集统计
        total_captures = 0
        for ms in self.machines.values():
            for fs in ms.funnels.values():
                total_captures += fs.detection_count
        system["total_captures"] = total_captures

        return {
            "faults": faults,
            "fault_count": len(faults),
            "system": system,
            "events": self._fault_events[-20:],  # 最近 20 条事件
        }

    def get_overview_data(self) -> List[dict]:
        """总览页数据"""
        result = []
        for mid, ms in self.machines.items():
            mc = ms.machine_config
            vision_enabled = any(fs.vision_enabled for fs in ms.funnels.values()) if ms.funnels else True
            # 收集故障信息
            faults = []
            if not ms.plc_connected:
                faults.append(f"PLC 离线")
            for fid_chk, fs_chk in ms.funnels.items():
                cam = fs_chk.fault_info.get("camera", {})
                cam_status = cam.get("status", "unknown")
                if cam_status in ("disconnected", "not_available", "stopped"):
                    fc_chk = next((f for f in mc.funnels if f.id == fid_chk), None)
                    fname = fc_chk.name if fc_chk else fid_chk
                    if cam_status == "not_available":
                        faults.append(f"{fname} 相机未连接(IP不存在)")
                    elif cam_status == "stopped":
                        faults.append(f"{fname} 相机已停止重连")
                    else:
                        attempts = cam.get("reconnect_attempts", 0)
                        since = cam.get("since")
                        dur = ""
                        if since:
                            mins = int((time.time() - since) / 60)
                            dur = f" ({mins}分钟)" if mins > 0 else " (<1分钟)"
                        phase = f"重连{attempts}/5" if attempts <= 5 else "慢速重连"
                        faults.append(f"{fname} 相机断开{dur} [{phase}]")

            machine_data = {
                "id": mid,
                "name": mc.name,
                "plc_ip": mc.plc_ip,
                "plc_connected": ms.plc_connected,
                "alert_level": ms.worst_alert_level,
                "funnel_count": len(ms.funnels),
                "vision_enabled": vision_enabled,
                "faults": faults,
                "funnels": [],
            }
            for fid, fs in ms.funnels.items():
                fc = next((f for f in mc.funnels if f.id == fid), None)
                cap_phase = "idle"
                cap_remaining = 0
                if fs.capture_controller:
                    # tick() 只由后台 worker 驱动，这里只读取状态
                    cap_phase = fs.capture_controller.phase.value
                    cap_remaining = round(fs.capture_controller.window_remaining, 1)
                cam_status = fs.fault_info.get("camera", {}).get("status", "unknown")
                funnel_data = {
                    "id": fid,
                    "name": fc.name if fc else fid,
                    "is_running": fs.is_running,
                    "camera_status": cam_status,
                    "camera_error": fs.fault_info.get("camera", {}).get("error"),
                    "camera_since": fs.fault_info.get("camera", {}).get("since"),
                    "camera_reconnects": fs.fault_info.get("camera", {}).get("reconnect_attempts", 0),
                    "detection_count": fs.detection_count,
                    "coal_detections": fs.coal_detections,
                    "capture_phase": cap_phase,
                    "capture_remaining": cap_remaining,
                }
                if fs.last_result:
                    funnel_data.update({
                        "alert_level": getattr(fs.last_result, "device_alert_level", "UNKNOWN"),
                        "coal_grids": getattr(fs.last_result, "coal_grids", 0),
                        "total_grids": getattr(fs.last_result, "total_grids", 0),
                        "visible_grids": getattr(fs.last_result, "visible_grids", 0),
                    })
                else:
                    funnel_data.update({
                        "alert_level": "UNKNOWN",
                        "coal_grids": 0,
                        "total_grids": fc.grid_count if fc else 0,
                        "visible_grids": 0,
                    })
                machine_data["funnels"].append(funnel_data)
            result.append(machine_data)
        return result
