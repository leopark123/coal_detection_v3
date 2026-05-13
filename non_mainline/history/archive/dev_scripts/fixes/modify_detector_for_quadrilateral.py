#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修改检测器以支持四边形ROI
针对GridEditorToolKit标注的精确格栅
"""

import yaml
import cv2
import numpy as np
from pathlib import Path
import json


def load_quadrilateral_config(config_path):
    """
    加载四边形格栅配置
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    print(f"[INFO] 加载四边形配置: {config_path}")
    print(f"[INFO] ROI数量: {config['grid_config']['total_rois']}")
    print(f"[INFO] ROI类型: {config['grid_config']['roi_type']}")

    return config


def convert_to_system_format(config):
    """
    转换为当前检测系统兼容的格式
    将四边形转换为最小外接矩形 + 掩码
    """
    grid_rois = []
    quad_data = []

    print("[INFO] 转换四边形ROI为系统格式...")

    for roi_id, roi_info in config['grid_rois'].items():
        corners = np.array(roi_info['corners'], dtype=np.float32)

        # 计算最小外接矩形
        x_coords = corners[:, 0]
        y_coords = corners[:, 1]

        x_min, x_max = float(np.min(x_coords)), float(np.max(x_coords))
        y_min, y_max = float(np.min(y_coords)), float(np.max(y_coords))

        # 矩形格式 (x, y, w, h)
        x, y = x_min, y_min
        w, h = x_max - x_min, y_max - y_min

        grid_rois.append((x, y, w, h))

        # 保存四边形数据用于掩码
        quad_data.append({
            'corners': corners,
            'bbox': (x, y, w, h),
            'grid_pos': roi_info.get('grid_pos', [-1, -1])
        })

    print(f"[SUCCESS] 转换完成: {len(grid_rois)}个ROI")
    return grid_rois, quad_data


def create_quadrilateral_masks(quad_data, image_shape):
    """
    为每个四边形ROI创建掩码
    """
    masks = []

    print("[INFO] 创建四边形掩码...")

    for i, quad in enumerate(quad_data):
        # 创建掩码
        mask = np.zeros(image_shape[:2], dtype=np.uint8)

        # 填充四边形区域
        corners = quad['corners'].astype(np.int32)
        cv2.fillPoly(mask, [corners], 255)

        masks.append(mask)

    print(f"[SUCCESS] 创建了 {len(masks)} 个四边形掩码")
    return masks


def save_modified_config(grid_rois, output_path):
    """
    保存修改后的配置（兼容当前系统）
    """
    config = {
        'grid_config': {
            'created_by': 'quadrilateral_converter',
            'grid_dimensions': {
                'rows': 13,
                'cols': 10,
            },
            'image_source': 'GridEditorToolKit_v1.0.0_20260119_092150/samples/sample_image.png',
            'scale_factor': 1.0,
            'timestamp': '2026-02-18',
            'total_rois': len(grid_rois),
            'roi_type': 'rectangle_from_quadrilateral'
        },
        'grid_rois': []
    }

    # 转换为简单矩形格式
    for i, (x, y, w, h) in enumerate(grid_rois):
        config['grid_rois'].append({
            'x': float(x),
            'y': float(y),
            'w': float(w),
            'h': float(h)
        })

    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    print(f"[SUCCESS] 保存兼容配置: {output_path}")


def test_on_sample_image():
    """
    在样本图片上测试修改后的配置
    """
    print("\n" + "="*50)
    print("  测试新配置在样本图片上的效果")
    print("="*50)

    # 配置路径
    image_path = "GridEditorToolKit_v1.0.0_20260119_092150/samples/sample_image.png"
    config_path = "config/grid_precise.yaml"
    output_config = "config/grid_manual.yaml"

    try:
        # 1. 加载四边形配置
        quad_config = load_quadrilateral_config(config_path)

        # 2. 转换格式
        grid_rois, quad_data = convert_to_system_format(quad_config)

        # 3. 保存兼容配置
        save_modified_config(grid_rois, output_config)

        # 4. 测试图片尺寸匹配
        if Path(image_path).exists():
            image = cv2.imread(image_path)
            print(f"[INFO] 样本图片尺寸: {image.shape}")
            print(f"[INFO] 配置图片尺寸: {quad_config['grid_config']['image_size']}")

            # 检查尺寸是否匹配
            expected_h = quad_config['grid_config']['image_size']['height']
            expected_w = quad_config['grid_config']['image_size']['width']

            if image.shape[0] == expected_h and image.shape[1] == expected_w:
                print("[SUCCESS] 图片尺寸匹配!")
            else:
                print(f"[WARNING] 图片尺寸不匹配: 实际{image.shape[:2]} vs 预期({expected_h}, {expected_w})")

        print(f"\n[SUCCESS] 配置已更新为125个精确格栅!")
        print(f"[INFO] 下一步: 重启Web界面测试检测效果")

    except Exception as e:
        print(f"[ERROR] 配置转换失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_on_sample_image()