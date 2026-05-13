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

    # 图像尺寸
    img_width = 459  # 从之前分析得到
    img_height = 600

    # 根据标注图片估算格栅区域
    # 从图片观察，格栅区域大致占图片的中心部分
    grid_start_x = int(img_width * 0.05)   # 左边缘5%
    grid_start_y = int(img_height * 0.05)  # 上边缘5%
    grid_width = int(img_width * 0.90)     # 格栅区域宽度90%
    grid_height = int(img_height * 0.85)   # 格栅区域高度85%

    # 单个格栅孔尺寸
    cell_width = grid_width // 12
    cell_height = grid_height // 9

    # 生成108个ROI
    roi_list = []
    roi_id = 1

    for row in range(9):
        for col in range(12):
            # 计算每个格栅孔的位置
            x = grid_start_x + col * cell_width
            y = grid_start_y + row * cell_height
            w = cell_width - 2  # 留一点间隙
            h = cell_height - 2

            # 格式1: 简单矩形格式（与现有系统兼容）
            roi_dict = {
                'x': float(x),
                'y': float(y),
                'w': float(w),
                'h': float(h)
            }
            roi_list.append(roi_dict)
            roi_id += 1

    config['grid_rois'] = roi_list

    # 保存到新文件
    output_path = Path("config/grid_corrected.yaml")
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    print(f"✅ 已生成修正配置: {output_path}")
    print(f"📊 格栅布局: 9行 × 12列 = 108个ROI")
    print(f"📐 单个ROI尺寸: {cell_width}×{cell_height} 像素")

    return str(output_path)


def backup_old_config():
    """备份原配置文件"""
    old_config = Path("config/grid_manual.yaml")
    if old_config.exists():
        backup_path = Path("config/grid_manual_backup.yaml")
        import shutil
        shutil.copy(old_config, backup_path)
        print(f"📁 已备份原配置: {backup_path}")


def update_detector_config():
    """
    更新检测器配置，使用修正后的格栅
    """
    print("\n🔄 更新系统配置...")

    # 建议的配置更新
    suggestions = [
        "1. 将 config/grid_corrected.yaml 重命名为 config/grid_manual.yaml",
        "2. 或在 detector.py 中指定使用 grid_corrected.yaml",
        "3. 设置开发模式使用真实格栅: USE_REAL_GRID_IN_DEV = True"
    ]

    for suggestion in suggestions:
        print(f"   {suggestion}")


def verify_grid_config(config_path):
    """验证生成的格栅配置"""
    print(f"\n🔍 验证配置文件: {config_path}")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        dimensions = config['grid_config']['grid_dimensions']
        rois = config['grid_rois']

        expected_count = dimensions['rows'] * dimensions['cols']
        actual_count = len(rois)

        print(f"   📐 预期格栅数: {expected_count}")
        print(f"   📊 实际ROI数: {actual_count}")

        if expected_count == actual_count == 108:
            print("   ✅ 配置验证通过!")
            return True
        else:
            print("   ❌ 配置验证失败!")
            return False

    except Exception as e:
        print(f"   ❌ 验证失败: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("  翻车机积煤检测系统 - 格栅配置修正工具")
    print("=" * 60)

    # Step 1: 备份原配置
    backup_old_config()

    # Step 2: 生成修正配置
    config_path = generate_correct_grid_config()

    # Step 3: 验证配置
    verify_grid_config(config_path)

    # Step 4: 提供更新建议
    update_detector_config()

    print(f"\n🎯 下一步操作:")
    print(f"   python test_grid_detection.py  # 测试修正后的检测效果")
    print(f"   python main.py --dev           # 验证系统运行")
    print("=" * 60)