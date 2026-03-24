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

    def initialize(self, devices_config: DevicesConfig, base_config: Config):
        """
        初始化所有翻车机和漏斗

        为每个漏斗创建独立的 camera 和 detector 实例。
        为每台翻车机创建独立的 PLC 连接。
        """
        self.devices_config = devices_config
        self.base_config = base_config

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

            # 创建每个漏斗的 camera + detector
            for fc in mc.funnels:
                funnel_cfg = build_funnel_config(base_config, mc, fc)
                fs = FunnelState(machine_id=mc.id, funnel_id=fc.id)
                fs.config = funnel_cfg

                try:
                    fs.camera = create_camera(funnel_cfg)
                    logger.info(f"[StateManager] 相机 {fc.camera_ip} 已连接 ({mc.name}/{fc.name})")
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

                fs.is_running = bool(fs.camera and fs.detector)
                ms.funnels[fc.id] = fs

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
            machine_data = {
                "id": mid,
                "name": mc.name,
                "plc_ip": mc.plc_ip,
                "plc_connected": ms.plc_connected,
                "alert_level": ms.worst_alert_level,
                "funnel_count": len(ms.funnels),
                "funnels": [],
            }
            for fid, fs in ms.funnels.items():
                fc = next((f for f in mc.funnels if f.id == fid), None)
                funnel_data = {
                    "id": fid,
                    "name": fc.name if fc else fid,
                    "is_running": fs.is_running,
                    "detection_count": fs.detection_count,
                    "coal_detections": fs.coal_detections,
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
