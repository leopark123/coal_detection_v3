"""翻车机积煤检测系统 V3.0 - 算法模块"""

from .detector import CoalDetector, FrameVoter, DetectionResult
from .grid_counter import GridCounter
from .coal_detector import CoalAreaDetector
from .judge import CoalJudge

__all__ = [
    "CoalDetector",
    "FrameVoter",
    "DetectionResult",
    "GridCounter",
    "CoalAreaDetector",
    "CoalJudge",
]
