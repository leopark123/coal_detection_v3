"""
翻车机积煤检测系统 V3.0 - 多机拓扑配置加载器

三级数据模型：
- DevicesConfig（服务器级）
  - MachineConfig（翻车机级，含 PLC 信息）
    - FunnelConfig（漏斗级，含相机信息）
"""

from dataclasses import dataclass, field
from typing import List
from pathlib import Path

import yaml

from config.config import Config


@dataclass
class FunnelConfig:
    """漏斗配置（一个漏斗 = 一台相机 + 一组格栅）"""
    id: str
    name: str
    camera_ip: str
    pixel_format: str = "mono"
    camera_timeout_ms: int = 5000
    grid_count: int = 125
    grid_config_path: str = "config/grid_manual.yaml"


@dataclass
class MachineConfig:
    """翻车机配置（一台翻车机 = 一台 PLC + N 个漏斗）"""
    id: str
    name: str
    plc_ip: str
    plc_timeout_ms: int = 3000
    plc_heartbeat_interval_ms: int = 500
    funnels: List[FunnelConfig] = field(default_factory=list)


@dataclass
class DevicesConfig:
    """顶层配置（一台服务器管理的所有翻车机）"""
    machines: List[MachineConfig] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str) -> "DevicesConfig":
        """从 YAML 文件加载多机拓扑配置"""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        machines = []
        for m in data.get("machines", []):
            funnels = []
            for fn in m.get("funnels", []):
                funnels.append(FunnelConfig(
                    id=fn["id"],
                    name=fn.get("name", fn["id"]),
                    camera_ip=fn["camera_ip"],
                    pixel_format=fn.get("pixel_format", "mono"),
                    camera_timeout_ms=fn.get("camera_timeout_ms", 5000),
                    grid_count=fn.get("grid_count", 125),
                    grid_config_path=fn.get("grid_config_path", "config/grid_manual.yaml"),
                ))
            machines.append(MachineConfig(
                id=m["id"],
                name=m.get("name", m["id"]),
                plc_ip=m["plc_ip"],
                plc_timeout_ms=m.get("plc_timeout_ms", 3000),
                plc_heartbeat_interval_ms=m.get("plc_heartbeat_interval_ms", 500),
                funnels=funnels,
            ))

        return cls(machines=machines)

    def get_machine(self, machine_id: str):
        """按 ID 查找翻车机配置"""
        for m in self.machines:
            if m.id == machine_id:
                return m
        return None

    def get_funnel(self, machine_id: str, funnel_id: str):
        """按 ID 查找漏斗配置"""
        m = self.get_machine(machine_id)
        if m:
            for f in m.funnels:
                if f.id == funnel_id:
                    return f
        return None


def build_funnel_config(
    base_config: Config,
    machine: MachineConfig,
    funnel: FunnelConfig,
) -> Config:
    """
    为指定漏斗构建 Config 对象

    基于 base_config 的算法参数，覆盖硬件参数（相机IP、PLC IP 等），
    生成一个兼容 create_camera(config) 和 DeviceDetector(config, ...) 的 Config。
    """
    cfg = Config()

    # 复制基础算法参数
    algo_attrs = [
        "DEV_MODE", "FRAME_WIDTH", "FRAME_HEIGHT", "CHANNELS", "TARGET_FPS",
        "DEV_FRAME_WIDTH", "DEV_FRAME_HEIGHT", "DEV_FPS",
        "USE_ECC", "ECC_PROCESS_WIDTH", "ECC_PROCESS_HEIGHT",
        "ECC_MAX_ITERATIONS", "ECC_EPSILON",
        "CLAHE_CLIP_LIMIT", "CLAHE_TILE_SIZE",
        "GRID_VISIBLE_THRESHOLD", "COAL_COVERAGE_THRESHOLD",
        "VOTE_WINDOW_SIZE", "VOTE_THRESHOLD",
        "USE_CUDA", "LOG_LEVEL",
        "SAVE_ALARM_IMAGES", "SAVE_INTERVAL_FRAMES", "IMAGE_SAVE_DIR",
        "REFERENCE_IMAGE_PATH", "MOCK_SOURCE_DIR",
        "MOCK_CAMERA_FAIL_RATE", "MOCK_PLC_DELAY_MAX", "MOCK_ENABLE_FAULT_INJECTION",
        "USE_REAL_GRID_IN_DEV",
    ]
    for attr in algo_attrs:
        if hasattr(base_config, attr):
            setattr(cfg, attr, getattr(base_config, attr))

    # 覆盖漏斗硬件参数
    cfg.CAMERA_IP = funnel.camera_ip
    cfg.CAMERA_PIXEL_FORMAT = funnel.pixel_format
    cfg.CAMERA_TIMEOUT_MS = funnel.camera_timeout_ms
    cfg.GRID_MANUAL_PATH = funnel.grid_config_path

    # 覆盖 PLC 参数
    cfg.PLC_IP = machine.plc_ip
    cfg.PLC_TIMEOUT_MS = machine.plc_timeout_ms
    cfg.PLC_HEARTBEAT_INTERVAL_MS = machine.plc_heartbeat_interval_ms

    return cfg
