"""
翻车机积煤检测系统 V3.0 - 配置模块

支持开发/生产模式切换

模式切换方式（优先级从高到低）：
1. 命令行参数 --dev
2. 环境变量 COAL_ENV=DEV
3. 配置文件中的 DEV_MODE
4. 默认值 False（生产模式）
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import yaml


def _get_dev_mode_from_env() -> bool:
    """
    从环境变量获取 DEV_MODE
    
    环境变量：COAL_ENV
    - "DEV" → 开发模式
    - "PROD" 或其他 → 生产模式
    
    By Gemini 建议：使用环境变量控制模式，便于部署
    """
    env_value = os.getenv("COAL_ENV", "PROD").upper()
    return env_value == "DEV"


def _get_bool_from_env(env_key: str, default: bool = False) -> bool:
    """
    从环境变量读取布尔值。

    支持值：
    - True: 1/true/yes/y/on
    - False: 0/false/no/n/off
    - 未设置或非法值：返回 default
    """
    raw_value = os.getenv(env_key)
    if raw_value is None:
        return default

    value = raw_value.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


@dataclass
class Config:
    """
    系统配置
    
    核心开关：DEV_MODE
    - True: 开发模式（Mock驱动、低分辨率、无GPU）
    - False: 生产模式（真实硬件、全分辨率、CUDA）
    """
    
    # ═══════════════════════════════════════════════════════════════
    # 核心开关
    # ═══════════════════════════════════════════════════════════════
    # 默认从环境变量读取，如果没有设置则默认为生产模式（安全起见）
    # 设置环境变量：set COAL_ENV=DEV（Windows）或 export COAL_ENV=DEV（Linux）
    DEV_MODE: bool = field(default_factory=_get_dev_mode_from_env)
    
    # ═══════════════════════════════════════════════════════════════
    # 硬件参数（生产环境）
    # ═══════════════════════════════════════════════════════════════
    FRAME_WIDTH: int = 3072          # 海康 600W 相机
    FRAME_HEIGHT: int = 2048
    CHANNELS: int = 3
    TARGET_FPS: float = 10.0
    
    # 相机配置（Basler GigE）
    CAMERA_TYPE: str = "basler"
    CAMERA_IP: str = "192.168.1.100"
    CAMERA_TIMEOUT_MS: int = 5000
    
    # PLC 配置
    PLC_IP: str = "192.168.1.200"
    PLC_HEARTBEAT_INTERVAL_MS: int = 500
    PLC_TIMEOUT_MS: int = 3000
    
    # ═══════════════════════════════════════════════════════════════
    # 开发环境覆盖
    # ═══════════════════════════════════════════════════════════════
    DEV_FRAME_WIDTH: int = 1024
    DEV_FRAME_HEIGHT: int = 768
    DEV_FPS: float = 1.0             # 1秒1帧，低配电脑友好
    
    # 模拟数据目录
    MOCK_SOURCE_DIR: str = "tests/mock_data"
    
    # 故障注入概率（开发调试用）
    MOCK_CAMERA_FAIL_RATE: float = 0.01    # 1% 概率模拟掉线
    MOCK_PLC_DELAY_MAX: float = 0.5        # 最大模拟延迟（秒）
    MOCK_ENABLE_FAULT_INJECTION: bool = False  # 是否启用故障注入
    
    # ═══════════════════════════════════════════════════════════════
    # 算法参数
    # ═══════════════════════════════════════════════════════════════
    # ECC 配准
    USE_ECC: bool = True
    ECC_PROCESS_WIDTH: int = 320
    ECC_PROCESS_HEIGHT: int = 240
    ECC_MAX_ITERATIONS: int = 5
    ECC_EPSILON: float = 0.01
    
    # CLAHE 增强
    CLAHE_CLIP_LIMIT: float = 3.0
    CLAHE_TILE_SIZE: int = 8
    
    # 检测阈值
    GRID_VISIBLE_THRESHOLD: float = 0.85
    COAL_COVERAGE_THRESHOLD: float = 0.05
    
    # 多帧投票
    VOTE_WINDOW_SIZE: int = 5
    VOTE_THRESHOLD: int = 3
    
    # ═══════════════════════════════════════════════════════════════
    # GPU 加速
    # ═══════════════════════════════════════════════════════════════
    USE_CUDA: bool = False           # DEV_MODE 下自动关闭
    
    # ═══════════════════════════════════════════════════════════════
    # 日志与存图
    # ═══════════════════════════════════════════════════════════════
    LOG_LEVEL: str = "INFO"
    SAVE_ALARM_IMAGES: bool = True   # 报警时存图
    SAVE_INTERVAL_FRAMES: int = 100  # 每N帧存一张（回放用）
    IMAGE_SAVE_DIR: str = "logs/images"
    
    # ═══════════════════════════════════════════════════════════════
    # 路径
    # ═══════════════════════════════════════════════════════════════
    REFERENCE_IMAGE_PATH: str = "config/reference.jpg"
    GRID_BASELINE_PATH: str = "config/grid_baseline.yaml"
    GRID_MANUAL_PATH: str = "config/grid_manual.yaml"
    # 允许通过环境变量 USE_REAL_GRID_IN_DEV 覆盖
    USE_REAL_GRID_IN_DEV: bool = field(default_factory=lambda: _get_bool_from_env("USE_REAL_GRID_IN_DEV", False))
    
    # ═══════════════════════════════════════════════════════════════
    # 计算属性
    # ═══════════════════════════════════════════════════════════════
    @property
    def frame_width(self) -> int:
        """当前使用的帧宽度"""
        return self.DEV_FRAME_WIDTH if self.DEV_MODE else self.FRAME_WIDTH
    
    @property
    def frame_height(self) -> int:
        """当前使用的帧高度"""
        return self.DEV_FRAME_HEIGHT if self.DEV_MODE else self.FRAME_HEIGHT
    
    @property
    def frame_size(self) -> int:
        """帧大小（字节）"""
        return self.frame_width * self.frame_height * self.CHANNELS
    
    @property
    def frame_interval(self) -> float:
        """帧间隔（秒）"""
        fps = self.DEV_FPS if self.DEV_MODE else self.TARGET_FPS
        return 1.0 / fps
    
    @property
    def ecc_scale_x(self) -> float:
        """ECC 缩放比例 X"""
        return self.frame_width / self.ECC_PROCESS_WIDTH
    
    @property
    def ecc_scale_y(self) -> float:
        """ECC 缩放比例 Y"""
        return self.frame_height / self.ECC_PROCESS_HEIGHT
    
    @property
    def use_cuda_actual(self) -> bool:
        """实际是否使用 CUDA"""
        return self.USE_CUDA and not self.DEV_MODE
    
    @property
    def use_ecc_actual(self) -> bool:
        """实际是否使用 ECC"""
        return self.USE_ECC and not self.DEV_MODE
    
    # ═══════════════════════════════════════════════════════════════
    # 加载/保存
    # ═══════════════════════════════════════════════════════════════
    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        """从 YAML 文件加载配置"""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        config = cls()
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        
        return config
    
    def to_yaml(self, path: str):
        """保存配置到 YAML 文件"""
        data = {
            k: v for k, v in self.__dict__.items()
            if not k.startswith("_") and not callable(v)
        }
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    
    def print_summary(self):
        """打印配置摘要"""
        mode = "[DEV] 开发模式" if self.DEV_MODE else "[PROD] 生产模式"
        env_value = os.getenv("COAL_ENV", "未设置")
        print("=" * 60)
        print(f"  翻车机积煤检测系统 V3.0 配置")
        print("=" * 60)
        print(f"  当前模式: {mode}")
        print(f"  环境变量 COAL_ENV: {env_value}")
        print(f"  分辨率: {self.frame_width} x {self.frame_height}")
        print(f"  帧率: {1/self.frame_interval:.1f} FPS")
        print(f"  ECC 配准: {'启用' if self.use_ecc_actual else '禁用'}")
        print(f"  CUDA 加速: {'启用' if self.use_cuda_actual else '禁用'}")
        print(f"  故障注入: {'启用' if self.MOCK_ENABLE_FAULT_INJECTION else '禁用'}")
        print("=" * 60)


# 默认配置实例
default_config = Config()
