#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
为开发模式生成正确的格栅配置
"""

import yaml
from pathlib import Path
import cv2


def generate_dev_grid_config():
    """
    为开发模式(1024x768)生成12x9格栅配置
    """
    print("[INFO] 为开发模式生成格栅配置...")

    # 开发模式尺寸
    dev_width = 1024
    dev_height = 768

    config = {
        'grid_config': {
            'created_by': 'fix_grid_for_dev_script',
            'grid_dimensions': {
                'cols': 12,  # 12列
                'rows': 9,   # 9行
            },
            'image_source': 'tests/mock_data/clean/step_02_enhanced.jpg',
            'scale_factor': 1.0,
            'timestamp': '2026-02-18',
            'total_rois': 108,
            'target_resolution': f'{dev_width}x{dev_height}'
        },
        'grid_rois': []
    }

    # 格栅区域估算（适配开发模式分辨率）
    grid_start_x = int(dev_width * 0.08)   # 左边缘8%
    grid_start_y = int(dev_height * 0.10)  # 上边缘10%
    grid_width = int(dev_width * 0.84)     # 格栅区域宽度84%
    grid_height = int(dev_height * 0.80)   # 格栅区域高度80%

    # 单个格栅孔尺寸
    cell_width = grid_width // 12
    cell_height = grid_height // 9

    print(f"[INFO] 开发模式尺寸: {dev_width}x{dev_height}")
    print(f"[INFO] 格栅区域: {grid_width}x{grid_height}")
    print(f"[INFO] 单个格栅: {cell_width}x{cell_height}")

    # 生成108个ROI
    roi_list = []

    for row in range(9):
        for col in range(12):
            # 计算每个格栅孔的位置
            x = grid_start_x + col * cell_width
            y = grid_start_y + row * cell_height
            w = cell_width - 4  # 留一点间隙
            h = cell_height - 4

            roi_dict = {
                'x': float(x),
                'y': float(y),
                'w': float(w),
                'h': float(h)
            }
            roi_list.append(roi_dict)

    config['grid_rois'] = roi_list

    # 保存配置
    output_path = Path("config/grid_dev_corrected.yaml")
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    print(f"[SUCCESS] 已生成开发模式格栅配置: {output_path}")
    print(f"[INFO] 格栅数量: 12列 × 9行 = 108个")

    return str(output_path)


if __name__ == "__main__":
    print("=" * 50)
    print("  生成开发模式格栅配置")
    print("=" * 50)

    config_path = generate_dev_grid_config()

    print(f"[INFO] 下一步:")
    print(f"1. cp {config_path} config/grid_manual.yaml")
    print(f"2. python test_grid_final.py")
    print("=" * 50)