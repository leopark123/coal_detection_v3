"""
兼容层：历史 GridCounter 接口

当前实现复用 CoalDetector 的格栅计数逻辑。
"""

from .detector import CoalDetector


class GridCounter:
    def __init__(self, config):
        self._detector = CoalDetector(config)

    def count_visible_holes(self, frame) -> float:
        if frame is None:
            raise ValueError("frame cannot be None")

        enhanced = self._detector._enhance(frame)
        ratio, _ = self._detector._count_grids(enhanced)
        return float(ratio)
