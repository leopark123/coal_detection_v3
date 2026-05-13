#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置文件转换工具
将 grid_baseline.json 转换为检测系统期望的 grid_manual.yaml 格式
"""

import json
import yaml
import numpy as np
from pathlib import Path

def convert_json_to_yaml():
    """转换JSON配置为YAML配置"""

    json_path = "config/grid_baseline.json"
    yaml_path = "config/grid_manual.yaml"

    print(f"正在转换配置文件...")
    print(f"输入: {json_path}")
    print(f"输出: {yaml_path}")

    try:
        # 读取JSON配置
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)

        # 提取数据
        grid_vertices = np.array(json_data["grid_vertices"])
        cell_states = np.array(json_data["cell_states"])
        rows = json_data["rows"]
        cols = json_data["cols"]

        print(f"网格尺寸: {rows}行 × {cols}列")
        print(f"顶点数量: {len(grid_vertices)} × {len(grid_vertices[0])}")
        print(f"格子数量: {len(cell_states)} × {len(cell_states[0])}")

        # 创建格栅ROI列表
        rois = []
        roi_id = 1

        for i in range(rows):
            for j in range(cols):
                if cell_states[i][j]:  # 只保存有效的格子
                    # 获取格子的四个顶点
                    top_left = grid_vertices[i][j]
                    top_right = grid_vertices[i][j+1]
                    bottom_right = grid_vertices[i+1][j+1]
                    bottom_left = grid_vertices[i+1][j]

                    # 创建ROI配置
                    roi_config = {
                        f'roi_{roi_id:03d}': {
                            'corners': [
                                [float(top_left[0]), float(top_left[1])],
                                [float(top_right[0]), float(top_right[1])],
                                [float(bottom_right[0]), float(bottom_right[1])],
                                [float(bottom_left[0]), float(bottom_left[1])]
                            ],
                            'grid_pos': [i, j],
                            'enabled': True
                        }
                    }
                    rois.append(roi_config)
                    roi_id += 1

        # 创建YAML配置结构
        yaml_config = {
            'grid_config': {
                'image_source': json_data["image_path"],
                'grid_dimensions': {
                    'rows': rows,
                    'cols': cols
                },
                'scale_factor': json_data.get("scale_factor", 1.0),
                'total_rois': len(rois),
                'created_by': 'stable_grid_editor',
                'timestamp': '2026-01-18'
            },
            'grid_rois': {}
        }

        # 添加所有ROI到配置中
        for roi in rois:
            yaml_config['grid_rois'].update(roi)

        # 保存YAML配置
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump(yaml_config, f, default_flow_style=False, allow_unicode=True, indent=2)

        print(f"[OK] 转换成功!")
        print(f"   有效ROI数量: {len(rois)}")
        print(f"   配置文件: {yaml_path}")

        return True

    except Exception as e:
        print(f"[ERROR] 转换失败: {e}")
        return False

if __name__ == "__main__":
    convert_json_to_yaml()