#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修正格栅配置脚本
根据标注图片生成正确的格栅ROI配置
"""

import cv2
import numpy as np
import yaml
from pathlib import Path


def generate_correct_grid_config():
    """
    根据标注图片生成正确的12×9格栅配置
    """
    print("[INFO] 开始修正格栅配置...")

    # 基于标注图片的真实格栅布局
    config = {
        'grid_config': {
            'created_by': 'fix_grid_config_script',
            'grid_dimensions': {
                'cols': 12,  # 标注显示12列
                'rows': 9,   # 标注显示9行
            },
            'image_source': 'tests/mock_data/clean/step_02_enhanced.jpg',
            'scale_factor': 1.0,
            'timestamp': '2026-02-18',
            'total_rois': 108  # 12 × 9 = 108
        },
        'grid_rois': []
    }

    # 图像尺寸 (从之前分析得到)
    img_width = 459
    img_height = 600

    # 根据标注图片估算格栅区域
    grid_start_x = int(img_width * 0.05)
    grid_start_y = int(img_height * 0.05)
    grid_width = int(img_width * 0.90)
    grid_height = int(img_height * 0.85)

    # 单个格栅孔尺寸
    cell_width = grid_width // 12
    cell_height = grid_height // 9

    # 生成108个ROI
    roi_list = []

    for row in range(9):
        for col in range(12):
            # 计算每个格栅孔的位置
            x = grid_start_x + col * cell_width
            y = grid_start_y + row * cell_height
            w = cell_width - 2  # 留一点间隙
            h = cell_height - 2

            # 格式: 简单矩形格式
            roi_dict = {
                'x': float(x),
                'y': float(y),
                'w': float(w),
                'h': float(h)
            }
            roi_list.append(roi_dict)

    config['grid_rois'] = roi_list

    # 保存到新文件
    output_path = Path("config/grid_corrected.yaml")
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    print(f"[SUCCESS] 已生成修正配置: {output_path}")
    print(f"[INFO] 格栅布局: 9行 × 12列 = 108个ROI")
    print(f"[INFO] 单个ROI尺寸: {cell_width}×{cell_height} 像素")

    return str(output_path)


def backup_old_config():
    """备份原配置文件"""
    old_config = Path("config/grid_manual.yaml")
    if old_config.exists():
        backup_path = Path("config/grid_manual_backup.yaml")
        import shutil
        shutil.copy(old_config, backup_path)
        print(f"[INFO] 已备份原配置: {backup_path}")


if __name__ == "__main__":
    print("=" * 60)
    print("  翻车机积煤检测系统 - 格栅配置修正工具")
    print("=" * 60)

    # 备份原配置
    backup_old_config()

    # 生成修正配置
    config_path = generate_correct_grid_config()

    print(f"[INFO] 修正完成!")
    print(f"[NEXT] 运行测试: python test_grid_detection.py")
    print("=" * 60)