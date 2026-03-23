#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
单格栅检测器 - 用于算法验证和参数调优

阶段1实现：专门检测单个格栅，确保准确率后再扩展
"""

import cv2
import numpy as np
from typing import Optional, Tuple, Dict, Any
from pathlib import Path
import time
import yaml
from loguru import logger

from .detector import CoalDetector, DetectionResult, GridInfo


class SingleGridResult:
    """单格栅检测结果"""

    def __init__(self):
        self.grid_id: int = 0
        self.grid_detail: Optional[GridInfo] = None
        self.has_coal: bool = False
        self.confidence: str = "UNKNOWN"
        self.confidence_score: float = 0.0
        self.process_time_ms: float = 0.0
        self.frame_id: int = 0

        # 验证相关指标
        self.grid_visible_ratio: float = 0.0
        self.coal_coverage: float = 0.0
        self.roi_area: int = 0
        self.roi_coords: Tuple[int, int, int, int] = (0, 0, 0, 0)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "grid_id": self.grid_id,
            "has_coal": self.has_coal,
            "confidence": self.confidence,
            "confidence_score": self.confidence_score,
            "process_time_ms": self.process_time_ms,
            "frame_id": self.frame_id,
            "grid_visible_ratio": self.grid_visible_ratio,
            "coal_coverage": self.coal_coverage,
            "roi_area": self.roi_area,
            "roi_coords": self.roi_coords,
            "grid_detail": {
                "id": self.grid_detail.id,
                "x": self.grid_detail.x,
                "y": self.grid_detail.y,
                "w": self.grid_detail.w,
                "h": self.grid_detail.h,
                "is_visible": self.grid_detail.is_visible,
                "visibility_score": self.grid_detail.visibility_score,
                "has_coal": self.grid_detail.has_coal,
                "coal_coverage": self.grid_detail.coal_coverage
            } if self.grid_detail else None
        }


class SingleGridDetector(CoalDetector):
    """
    单格栅检测器

    专门用于验证单个格栅的检测准确率
    支持参数调优和性能测试
    """

    def __init__(self, config, target_grid_id: int = 0):
        """
        初始化单格栅检测器

        Args:
            config: 系统配置
            target_grid_id: 目标格栅ID (0-124)
        """
        # 先初始化父类以加载所有格栅
        super().__init__(config)

        if not self.grid_rois:
            raise ValueError("未找到格栅配置，请确保grid_manual.yaml存在")

        # 验证目标格栅ID
        if target_grid_id >= len(self.grid_rois):
            raise ValueError(f"格栅ID {target_grid_id} 超出范围 (0-{len(self.grid_rois)-1})")

        self.target_grid_id = target_grid_id
        self.original_grid_count = len(self.grid_rois)

        # 只保留目标格栅
        target_roi = self.grid_rois[target_grid_id]
        self.grid_rois = [target_roi]

        # 统计信息
        self.detection_count = 0
        self.coal_detections = 0
        self.avg_process_time = 0.0

        logger.info(f"[SingleGridDetector] 初始化完成")
        logger.info(f"[SingleGridDetector] 目标格栅: {target_grid_id}/{self.original_grid_count}")
        logger.info(f"[SingleGridDetector] ROI坐标: {target_roi}")

    def detect_single_grid(self, frame: np.ndarray, frame_id: int = 0) -> SingleGridResult:
        """
        单格栅检测主入口

        Args:
            frame: 输入图像
            frame_id: 帧号

        Returns:
            SingleGridResult: 单格栅检测结果
        """
        start_time = time.perf_counter()

        result = SingleGridResult()
        result.frame_id = frame_id
        result.grid_id = self.target_grid_id

        try:
            # 调用父类检测方法
            detection_result = self.detect(frame, frame_id)

            # 提取单格栅结果
            if detection_result.grid_details:
                grid_detail = detection_result.grid_details[0]
                result.grid_detail = grid_detail
                result.has_coal = grid_detail.has_coal
                result.grid_visible_ratio = grid_detail.visibility_score  # 使用正确的属性名
                result.coal_coverage = detection_result.coal_coverage
                result.roi_coords = (grid_detail.x, grid_detail.y, grid_detail.w, grid_detail.h)
                result.roi_area = grid_detail.w * grid_detail.h

            # 使用父类的判断结果
            result.confidence = detection_result.confidence
            result.confidence_score = detection_result.confidence_score

            # 更新统计
            self.detection_count += 1
            if result.has_coal:
                self.coal_detections += 1

        except Exception as e:
            logger.error(f"[SingleGridDetector] 检测异常: {e}")
            result.confidence = "ERROR"
            result.confidence_score = 0.0

        # 记录处理时间
        process_time = (time.perf_counter() - start_time) * 1000
        result.process_time_ms = process_time

        # 更新平均处理时间
        if self.detection_count > 0:
            self.avg_process_time = (
                (self.avg_process_time * (self.detection_count - 1) + process_time)
                / self.detection_count
            )

        return result

    def get_statistics(self) -> Dict[str, Any]:
        """获取检测统计信息"""
        coal_rate = (self.coal_detections / self.detection_count
                    if self.detection_count > 0 else 0.0)

        return {
            "target_grid_id": self.target_grid_id,
            "total_detections": self.detection_count,
            "coal_detections": self.coal_detections,
            "coal_detection_rate": coal_rate,
            "avg_process_time_ms": self.avg_process_time,
            "roi_coords": self.grid_rois[0] if self.grid_rois else None,
            "original_grid_count": self.original_grid_count
        }

    def save_detection_log(self, result: SingleGridResult, output_dir: str = "logs/single_grid"):
        """保存检测日志"""
        log_dir = Path(output_dir)
        log_dir.mkdir(exist_ok=True, parents=True)

        log_file = log_dir / f"grid_{self.target_grid_id}_detections.yaml"

        # 读取现有日志
        logs = []
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    logs = yaml.safe_load(f) or []
            except Exception as e:
                logger.warning(f"读取日志文件失败: {e}")

        # 添加新记录
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "frame_id": result.frame_id,
            "has_coal": result.has_coal,
            "confidence": result.confidence,
            "confidence_score": result.confidence_score,
            "process_time_ms": result.process_time_ms,
            "grid_visible_ratio": result.grid_visible_ratio,
            "coal_coverage": result.coal_coverage
        }

        logs.append(log_entry)

        # 保持最近1000条记录
        if len(logs) > 1000:
            logs = logs[-1000:]

        # 保存日志
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                yaml.dump(logs, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            logger.error(f"保存日志失败: {e}")

    def visualize_single_grid(self, frame: np.ndarray, result: SingleGridResult) -> np.ndarray:
        """
        可视化单格栅检测结果

        Args:
            frame: 原始图像
            result: 检测结果

        Returns:
            带标注的图像
        """
        vis_frame = frame.copy()

        if not result.grid_detail:
            return vis_frame

        grid = result.grid_detail
        x, y, w, h = grid.x, grid.y, grid.w, grid.h

        # 绘制格栅边框
        if grid.has_coal:
            color = (0, 0, 255)  # 红色 - 有积煤
            thickness = 3
        elif grid.is_visible:
            color = (0, 255, 0)  # 绿色 - 正常可见
            thickness = 2
        else:
            color = (0, 165, 255)  # 橙色 - 不可见
            thickness = 2

        cv2.rectangle(vis_frame, (x, y), (x + w, y + h), color, thickness)

        # 绘制格栅ID
        cv2.putText(vis_frame, f"Grid {self.target_grid_id}",
                   (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        # 绘制状态信息
        status_text = "COAL" if grid.has_coal else ("VISIBLE" if grid.is_visible else "BLOCKED")
        cv2.putText(vis_frame, status_text,
                   (x, y + h + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # 绘制置信度
        conf_text = f"{result.confidence} ({result.confidence_score:.2f})"
        cv2.putText(vis_frame, conf_text,
                   (x, y + h + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # 绘制详细信息
        info_lines = [
            f"Visible: {grid.visibility_score:.2%}",
            f"Coverage: {result.coal_coverage:.2%}",
            f"Time: {result.process_time_ms:.1f}ms"
        ]

        for i, line in enumerate(info_lines):
            cv2.putText(vis_frame, line,
                       (10, 30 + i * 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        return vis_frame


def create_single_grid_config(target_grid_id: int, output_path: str = "config/single_grid_config.yaml"):
    """
    创建单格栅检测配置文件

    Args:
        target_grid_id: 目标格栅ID
        output_path: 输出路径
    """
    config = {
        "single_grid_mode": {
            "enabled": True,
            "target_grid_id": target_grid_id,
            "verification_mode": True,
            "save_detection_logs": True,
            "log_directory": "logs/single_grid"
        },
        "detection_parameters": {
            "grid_visible_threshold": 0.85,
            "coal_coverage_threshold": 0.05,
            "confidence_thresholds": {
                "high": 0.95,
                "medium": 0.80,
                "low": 0.50
            }
        },
        "performance_targets": {
            "accuracy_target": 0.95,
            "recall_target": 0.90,
            "precision_target": 0.98,
            "max_process_time_ms": 50
        }
    }

    output_file = Path(output_path)
    output_file.parent.mkdir(exist_ok=True, parents=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    logger.info(f"[Config] 单格栅配置已保存: {output_path}")
    return config