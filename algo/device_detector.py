#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
设备级检测器
设备1: 125个格栅口的完整检测系统
"""

import cv2
import numpy as np
import time
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass
from loguru import logger

from .detector import CoalDetector, DetectionResult, GridInfo


@dataclass
class DeviceResult:
    """设备检测结果"""
    device_id: str = "device-1"
    total_grids: int = 0
    visible_grids: int = 0
    coal_grids: int = 0
    device_has_coal: bool = False
    device_confidence: str = "NORMAL"
    device_alert_level: str = "NORMAL"  # NORMAL/ATTENTION/WARNING/CRITICAL
    coal_percentage: float = 0.0
    visible_percentage: float = 0.0
    quality_ok: bool = True
    fault_code: int = 0               # 0=正常, 3=画质问题

    # 性能指标
    process_time_ms: float = 0.0
    frame_id: int = 0

    # 详细信息
    grid_details: List[GridInfo] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "device_id": self.device_id,
            "total_grids": self.total_grids,
            "visible_grids": self.visible_grids,
            "coal_grids": self.coal_grids,
            "device_has_coal": self.device_has_coal,
            "device_confidence": self.device_confidence,
            "device_alert_level": self.device_alert_level,
            "coal_percentage": self.coal_percentage,
            "visible_percentage": self.visible_percentage,
            "process_time_ms": self.process_time_ms,
            "frame_id": self.frame_id,
            "grid_count": len(self.grid_details) if self.grid_details else 0
        }


class DeviceDetector(CoalDetector):
    """
    设备级检测器

    管理设备1的125个格栅口检测
    """

    def __init__(self, config, device_id: str = "device-1", grid_count: int = 125):
        """
        初始化设备检测器

        Args:
            config: 系统配置
            device_id: 设备ID
            grid_count: 设备包含的格栅口数量
        """
        # 先初始化父类获取所有格栅
        super().__init__(config)

        self.device_id = device_id
        self.grid_count = grid_count

        # 验证格栅数量
        if not self.grid_rois:
            raise ValueError("未找到格栅配置，请确保grid_manual.yaml存在")

        available_grids = len(self.grid_rois)
        if grid_count > available_grids:
            logger.warning(f"[DeviceDetector] 请求{grid_count}个格栅，但只有{available_grids}个可用")
            grid_count = available_grids

        # 为设备1分配所有125个格栅口
        self.device_grids = self.grid_rois[:grid_count]
        self.grid_rois = self.device_grids  # 更新检测器使用的格栅

        # ★ 重建 grid_mask 以匹配截断后的 grid_rois
        if hasattr(self, '_create_grid_mask') and callable(self._create_grid_mask):
            self.grid_mask = self._create_grid_mask()

        # 设备级统计
        self.detection_count = 0
        self.device_coal_detections = 0
        self.avg_process_time = 0.0

        logger.info(f"[DeviceDetector] 设备初始化完成")
        logger.info(f"[DeviceDetector] 设备ID: {device_id}")
        logger.info(f"[DeviceDetector] 格栅口数量: {len(self.device_grids)}")
        logger.info(f"[DeviceDetector] 格栅范围: 0-{len(self.device_grids)-1}")

    def detect_device(self, frame: np.ndarray, frame_id: int = 0) -> DeviceResult:
        """
        设备级检测主入口

        Args:
            frame: 输入图像
            frame_id: 帧号

        Returns:
            DeviceResult: 设备检测结果
        """
        start_time = time.perf_counter()

        # 创建结果对象
        result = DeviceResult()
        result.device_id = self.device_id
        result.frame_id = frame_id
        result.total_grids = len(self.device_grids)

        try:
            # 调用父类检测方法（检测所有125个格栅口）
            detection_result = self.detect(frame, frame_id)

            # ★ 画质自检失败 → 故障码3，不允许翻车
            if not detection_result.quality_ok:
                result.quality_ok = False
                result.fault_code = 3  # 画质问题
                result.device_has_coal = False  # 不确定，但不允许翻车
                result.device_confidence = "LOW"
                result.device_alert_level = "WARNING"
                result.process_time_ms = detection_result.process_time_ms
                logger.debug(f"[DeviceDetector] 画质不合格: {detection_result.quality_reason}")
                return result

            # 汇总设备级结果
            if detection_result.grid_details:
                result.grid_details = detection_result.grid_details

                # 统计格栅状态
                visible_grids = sum(1 for g in detection_result.grid_details if g.is_visible)
                coal_grids = sum(1 for g in detection_result.grid_details if g.has_coal)

                result.visible_grids = visible_grids
                result.coal_grids = coal_grids
                result.visible_percentage = visible_grids / result.total_grids * 100
                result.coal_percentage = coal_grids / result.total_grids * 100

                # 设备级判断
                device_status = self._judge_device_status(coal_grids, result.total_grids)
                result.device_has_coal = device_status['has_coal']
                result.device_confidence = device_status['confidence']
                result.device_alert_level = device_status['alert_level']

                # 更新统计
                self.detection_count += 1
                if result.device_has_coal:
                    self.device_coal_detections += 1

            else:
                result.quality_ok = False
                result.fault_code = 3
                result.device_confidence = "LOW"
                result.device_alert_level = "WARNING"

        except Exception as e:
            logger.error(f"[DeviceDetector] 设备检测异常: {e}")
            result.quality_ok = False
            result.fault_code = 3  # 检测异常视为画质/算法故障
            result.device_has_coal = False  # fault_code≠0 → can_tip=False
            result.device_confidence = "LOW"
            result.device_alert_level = "WARNING"

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

    def _judge_device_status(self, coal_grids: int, total_grids: int) -> Dict[str, Any]:
        """
        设备级积煤判断逻辑

        Args:
            coal_grids: 有积煤的格栅口数量
            total_grids: 总格栅口数量

        Returns:
            dict: 包含has_coal, confidence, alert_level
        """
        coal_ratio = coal_grids / total_grids if total_grids > 0 else 0.0

        # 设备级判断规则
        if coal_ratio >= 0.15:  # 15%以上格栅有煤 -> 严重
            return {
                'has_coal': True,
                'confidence': 'HIGH',
                'alert_level': 'CRITICAL'
            }
        elif coal_ratio >= 0.10:  # 10%以上格栅有煤 -> 警告
            return {
                'has_coal': True,
                'confidence': 'HIGH',
                'alert_level': 'WARNING'
            }
        elif coal_ratio >= 0.05:  # 5%以上格栅有煤 -> 注意
            return {
                'has_coal': True,
                'confidence': 'MEDIUM',
                'alert_level': 'ATTENTION'
            }
        elif coal_ratio >= 0.02:  # 2%以上格栅有煤 -> 正常但需关注
            return {
                'has_coal': False,
                'confidence': 'MEDIUM',
                'alert_level': 'NORMAL'
            }
        else:  # 很少或没有积煤 -> 正常
            return {
                'has_coal': False,
                'confidence': 'HIGH',
                'alert_level': 'NORMAL'
            }

    def reset_statistics(self):
        """重置设备级统计"""
        self.detection_count = 0
        self.device_coal_detections = 0
        self.avg_process_time = 0.0
        logger.info(f"[DeviceDetector] 统计已重置: {self.device_id}")

    def get_device_statistics(self) -> Dict[str, Any]:
        """获取设备统计信息"""
        device_coal_rate = (self.device_coal_detections / self.detection_count
                           if self.detection_count > 0 else 0.0)

        return {
            "device_id": self.device_id,
            "total_detections": self.detection_count,
            "device_coal_detections": self.device_coal_detections,
            "device_coal_rate": device_coal_rate,
            "avg_process_time_ms": self.avg_process_time,
            "grid_count": len(self.device_grids),
            "device_grid_range": f"0-{len(self.device_grids)-1}",
            "performance_target": "< 500ms (124格栅口)"
        }

    def visualize_device(self, frame: np.ndarray, result: DeviceResult) -> np.ndarray:
        """
        设备级可视化

        显示所有125个格栅口的状态
        """
        vis_frame = frame.copy()

        if not result.grid_details:
            return vis_frame

        # 绘制每个格栅口
        for grid in result.grid_details:
            x, y, w, h = grid.x, grid.y, grid.w, grid.h

            # 根据状态选择颜色
            if grid.has_coal:
                color = (0, 0, 255)  # 红色 - 有积煤
                thickness = 2
            elif grid.is_visible:
                color = (0, 255, 0)  # 绿色 - 正常
                thickness = 1
            else:
                color = (0, 165, 255)  # 橙色 - 不可见
                thickness = 1

            cv2.rectangle(vis_frame, (x, y), (x + w, y + h), color, thickness)

        # 设备级状态信息
        device_info = [
            f"Device: {result.device_id}",
            f"Grids: {result.total_grids}",
            f"Visible: {result.visible_grids} ({result.visible_percentage:.1f}%)",
            f"Coal: {result.coal_grids} ({result.coal_percentage:.1f}%)",
            f"Status: {result.device_alert_level}",
            f"Time: {result.process_time_ms:.1f}ms"
        ]

        # 绘制设备信息
        for i, info in enumerate(device_info):
            color = (255, 255, 255)
            if "CRITICAL" in info:
                color = (0, 0, 255)
            elif "WARNING" in info:
                color = (0, 165, 255)
            elif "ATTENTION" in info:
                color = (0, 255, 255)

            cv2.putText(vis_frame, info, (10, 30 + i * 25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        return vis_frame
