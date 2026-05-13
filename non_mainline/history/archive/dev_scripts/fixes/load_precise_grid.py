#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
加载GridEditorToolKit精确标注的格栅配置
转换为检测系统可用的四边形ROI格式
"""

import json
import yaml
import numpy as np
from pathlib import Path
import cv2


def load_grid_editor_config(config_path):
    """
    加载GridEditorToolKit生成的配置文件

    Returns:
        dict: 解析后的格栅配置
    """
    print(f"[INFO] 加载精确标注配置: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    print(f"[INFO] 图片尺寸: {config['image_size']['width']}×{config['image_size']['height']}")
    print(f"[INFO] 格栅维度: {config['grid_dimensions']['rows']}行×{config['grid_dimensions']['cols']}列")
    print(f"[INFO] 有效格栅: {config['valid_cells']}/{config['total_cells']}")

    return config


def extract_quadrilateral_rois(config):
    """
    从grid_vertices和cell_states提取四边形ROI

    Returns:
        list: 有效格栅的四边形顶点列表
    """
    vertices = config['grid_vertices']
    cell_states = config['cell_states']
    rows = config['grid_dimensions']['rows']
    cols = config['grid_dimensions']['cols']

    quadrilateral_rois = []

    print("[INFO] 计算四边形ROI...")

    # 遍历每个格栅单元
    for row in range(rows):
        for col in range(cols):
            # 检查该格栅是否有效
            if not cell_states[row][col]:
                continue

            # 计算四个顶点
            # 左上: vertices[row][col]
            # 右上: vertices[row][col+1]
            # 右下: vertices[row+1][col+1]
            # 左下: vertices[row+1][col]

            try:
                top_left = vertices[row][col]
                top_right = vertices[row][col + 1]
                bottom_right = vertices[row + 1][col + 1]
                bottom_left = vertices[row + 1][col]

                # 四边形顶点（顺时针）
                corners = [
                    [float(top_left[0]), float(top_left[1])],
                    [float(top_right[0]), float(top_right[1])],
                    [float(bottom_right[0]), float(bottom_right[1])],
                    [float(bottom_left[0]), float(bottom_left[1])]
                ]

                quadrilateral_rois.append({
                    'id': len(quadrilateral_rois) + 1,
                    'grid_pos': [row, col],
                    'corners': corners,
                    'enabled': True
                })

            except IndexError as e:
                print(f"[WARNING] 格栅[{row},{col}]顶点计算失败: {e}")
                continue

    print(f"[SUCCESS] 提取到 {len(quadrilateral_rois)} 个有效四边形ROI")
    return quadrilateral_rois


def create_system_config(quadrilateral_rois, source_config):
    """
    创建系统兼容的配置格式
    """
    config = {
        'grid_config': {
            'created_by': 'GridEditorToolKit_precise',
            'source_tool': 'GridEditorToolKit_v1.0.0',
            'grid_dimensions': {
                'rows': source_config['grid_dimensions']['rows'],
                'cols': source_config['grid_dimensions']['cols'],
            },
            'image_source': source_config['image_path'],
            'image_size': source_config['image_size'],
            'scale_factor': source_config['scale_factor'],
            'timestamp': '2026-02-18',
            'total_rois': len(quadrilateral_rois),
            'roi_type': 'quadrilateral'  # 四边形ROI标识
        },
        'grid_rois': {}
    }

    # 转换为系统格式
    for i, roi in enumerate(quadrilateral_rois):
        roi_id = f"roi_{i+1:03d}"
        config['grid_rois'][roi_id] = {
            'corners': roi['corners'],
            'enabled': roi['enabled'],
            'grid_pos': roi['grid_pos']
        }

    return config


def save_system_config(config, output_path):
    """
    保存系统配置文件
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    print(f"[SUCCESS] 已保存系统配置: {output_path}")


def visualize_rois(image_path, quadrilateral_rois, output_path):
    """
    可视化ROI区域
    """
    if not Path(image_path).exists():
        print(f"[WARNING] 图片不存在，跳过可视化: {image_path}")
        return

    print("[INFO] 生成ROI可视化图像...")

    image = cv2.imread(image_path)
    if image is None:
        print(f"[ERROR] 无法加载图片: {image_path}")
        return

    # 绘制每个ROI
    for i, roi in enumerate(quadrilateral_rois):
        corners = np.array(roi['corners'], dtype=np.int32)

        # 绘制四边形
        cv2.polylines(image, [corners], True, (0, 255, 0), 2)

        # 绘制ROI编号
        center_x = int(np.mean(corners[:, 0]))
        center_y = int(np.mean(corners[:, 1]))
        cv2.putText(image, str(i+1), (center_x-10, center_y+5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)

    # 保存结果
    cv2.imwrite(output_path, image)
    print(f"[SUCCESS] ROI可视化已保存: {output_path}")


def main():
    """
    主处理流程
    """
    print("=" * 60)
    print("  加载GridEditorToolKit精确标注数据")
    print("=" * 60)

    # 输入路径
    config_path = "GridEditorToolKit_v1.0.0_20260119_092150/config/grid_config.json"
    image_path = "GridEditorToolKit_v1.0.0_20260119_092150/samples/sample_image.png"

    # 输出路径
    output_config = "config/grid_precise.yaml"
    output_visual = "logs/grid_precise_visualization.jpg"

    try:
        # 1. 加载原始配置
        source_config = load_grid_editor_config(config_path)

        # 2. 提取四边形ROI
        quadrilateral_rois = extract_quadrilateral_rois(source_config)

        # 3. 创建系统配置
        system_config = create_system_config(quadrilateral_rois, source_config)

        # 4. 保存配置
        save_system_config(system_config, output_config)

        # 5. 生成可视化
        visualize_rois(image_path, quadrilateral_rois, output_visual)

        print(f"\n[SUCCESS] 配置转换完成!")
        print(f"[INFO] 精确格栅数量: {len(quadrilateral_rois)}个")
        print(f"[INFO] 系统配置文件: {output_config}")
        print(f"[INFO] 可视化结果: {output_visual}")

    except Exception as e:
        print(f"[ERROR] 配置加载失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()