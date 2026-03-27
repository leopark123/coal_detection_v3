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

from dataclasses import dataclass, field
from typing import Dict, Optional, Any, List

from loguru import logger

from config.config import Config
from config.devices_config import DevicesConfig, MachineConfig, FunnelConfig, build_funnel_config
from drivers.factory import create_camera, create_plc
from algo.device_detector import DeviceDetector
from web.common import StreamAppState
from core.capture_window import CaptureWindowController, CaptureWindowConfig


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
        self.coal_detections: int = 0
        self.vision_enabled: bool = True  # 视觉采集启用状态
        self.capture_controller: Optional[CaptureWindowController] = None


@dataclass
class MachineState:
    """单台翻车机的运行时状态（PLC + N 个漏斗）"""
    machine_id: str
    machine_config: MachineConfig
    plc: Any = None
    funnels: Dict[str, FunnelState] = field(default_factory=dict)

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

    def initialize(self, devices_config: DevicesConfig, base_config: Config, yaml_path: str = None):
        """
        初始化所有翻车机和漏斗

        为每个漏斗创建独立的 camera 和 detector 实例。
        为每台翻车机创建独立的 PLC 连接。
        """
        self.devices_config = devices_config
        self.base_config = base_config
        self._yaml_path = yaml_path

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
            except Exception as e:
                logger.error(f"[StateManager] PLC {mc.plc_ip} 连接失败: {e}")

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
        for ms in self.machines.values():
            for fs in ms.funnels.values():
                fs.stop_runtime(app_tag=f"[{fs.machine_id}/{fs.funnel_id}]")
            if ms.plc and hasattr(ms.plc, "close"):
                try:
                    ms.plc.close()
                except Exception as e:
                    logger.error(f"[StateManager] PLC 关闭失败 ({ms.machine_id}): {e}")

        self.machines.clear()
        logger.info("[StateManager] 所有资源已释放")

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
        except Exception as e:
            logger.error(f"[StateManager] PLC {mc.plc_ip} 连接失败: {e}")

        # 漏斗
        for fc in mc.funnels:
            self._create_funnel(ms, mc, fc)

        self.machines[mc.id] = ms

        # 同步到配置并持久化
        self.devices_config.add_machine(mc)
        self._save_config()

        logger.info(f"[StateManager] 翻车机已添加: {mc.name} ({len(mc.funnels)} 个漏斗)")

    def remove_machine(self, machine_id: str):
        """运行时移除翻车机（停止所有漏斗，关闭 PLC）"""
        ms = self.machines.get(machine_id)
        if not ms:
            raise ValueError(f"翻车机 {machine_id} 不存在")

        # 停止所有漏斗
        for fs in ms.funnels.values():
            fs.stop_runtime(app_tag=f"[{fs.machine_id}/{fs.funnel_id}]")

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
        applied = {}
        for key, value in params.items():
            if key not in allowed:
                continue
            # 更新 base_config
            if hasattr(self.base_config, key):
                setattr(self.base_config, key, value)
            # 更新每个漏斗的 config
            for ms in self.machines.values():
                for fs in ms.funnels.values():
                    if fs.config and hasattr(fs.config, key):
                        setattr(fs.config, key, value)
            applied[key] = value

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

        # 通知 PLC
        if ms.plc and hasattr(ms.plc, "set_vision_enable"):
            ms.plc.set_vision_enable(enabled)
        elif ms.plc and hasattr(ms.plc, "write"):
            ms.plc.write("Vision_Enable", enabled)
            if not enabled:
                ms.plc.write("Vision_CanTip", True)
                ms.plc.write("Vision_FaultCode", 0)
                ms.plc.write("Vision_ResultValid", True)

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

    def _create_funnel(self, ms: MachineState, mc: MachineConfig, fc: FunnelConfig):
        """内部：创建单个漏斗的 camera + detector"""
        funnel_cfg = build_funnel_config(self.base_config, mc, fc)
        fs = FunnelState(machine_id=mc.id, funnel_id=fc.id)
        fs.config = funnel_cfg

        try:
            fs.camera = create_camera(funnel_cfg)
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
        fs.capture_controller = CaptureWindowController(cap_cfg, plc=ms.plc)

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

        fs.is_running = bool(fs.camera and fs.detector)
        if fs.is_running:
            fs.capture_controller.start()
        ms.funnels[fc.id] = fs

    def _save_config(self):
        """内部：将当前拓扑配置持久化到 devices.yaml"""
        if self._yaml_path:
            try:
                self.devices_config.to_yaml(self._yaml_path)
                logger.debug(f"[StateManager] 配置已保存: {self._yaml_path}")
            except Exception as e:
                logger.error(f"[StateManager] 配置保存失败: {e}")

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

    def get_overview_data(self) -> List[dict]:
        """总览页数据"""
        result = []
        for mid, ms in self.machines.items():
            mc = ms.machine_config
            vision_enabled = any(fs.vision_enabled for fs in ms.funnels.values()) if ms.funnels else True
            machine_data = {
                "id": mid,
                "name": mc.name,
                "plc_ip": mc.plc_ip,
                "plc_connected": ms.plc_connected,
                "alert_level": ms.worst_alert_level,
                "funnel_count": len(ms.funnels),
                "vision_enabled": vision_enabled,
                "funnels": [],
            }
            for fid, fs in ms.funnels.items():
                fc = next((f for f in mc.funnels if f.id == fid), None)
                cap_phase = "idle"
                cap_remaining = 0
                if fs.capture_controller:
                    fs.capture_controller.tick()
                    cap_phase = fs.capture_controller.phase.value
                    cap_remaining = round(fs.capture_controller.window_remaining, 1)
                funnel_data = {
                    "id": fid,
                    "name": fc.name if fc else fid,
                    "is_running": fs.is_running,
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
