"""
兼容层：历史 CoalJudge 接口

当前实现复用 CoalDetector 的综合判定逻辑。
"""

from .detector import CoalDetector


class CoalJudge:
    def __init__(self, config):
        self._detector = CoalDetector(config)

    def judge(self, grid_ratio: float, coverage: float) -> dict:
        has_coal, confidence, score, need_manual = self._detector._judge(grid_ratio, coverage)
        # 兼容历史测试语义：NORMAL 视作高置信度干净
        if confidence == "NORMAL":
            confidence = "HIGH"
        return {
            "coal_present": has_coal,
            "confidence": confidence,
            "confidence_score": score,
            "need_manual": need_manual,
        }
