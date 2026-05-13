"""
兼容层：历史 CoalAreaDetector 接口

当前实现复用 CoalDetector 的覆盖率检测逻辑。
"""

from .detector import CoalDetector


class CoalAreaDetector:
    def __init__(self, config):
        self._detector = CoalDetector(config)

    def detect_coal_coverage(self, frame) -> float:
        if frame is None:
            raise ValueError("frame cannot be None")

        enhanced = self._detector._enhance(frame)
        return float(self._detector._detect_coverage(enhanced))
