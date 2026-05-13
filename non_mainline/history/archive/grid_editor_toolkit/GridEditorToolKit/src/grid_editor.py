#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
独立网格标定工具 - 可移植版本
Grid Editor Toolkit - Portable Version

功能:
- 支持任意行列数的网格标定
- 精确的顶点拖拽调整
- 格子有效性切换
- 配置保存和加载
- 跨平台兼容

使用方法:
python grid_editor.py --image "your_image.jpg" --rows 14 --cols 10
"""

import cv2
import numpy as np
import json
import math
import os
import argparse
import sys
from pathlib import Path
from typing import Optional, List, Tuple

# 版本信息
VERSION = "1.0.0"
AUTHOR = "Grid Editor Toolkit"

class GridEditor:
    """独立网格标定工具"""

    def __init__(self, image_path: str = "", rows: int = 14, cols: int = 10):
        # 基本参数
        self.image_path = image_path
        self.rows = rows
        self.cols = cols

        # 图像相关
        self.original_image = None
        self.display_image = None
        self.scale_factor = 1.0
        self.window_name = "Grid Editor v{} - S:Save R:Reset Q:Quit".format(VERSION)

        # 网格数据
        self.grid_vertices = None  # (rows+1) x (cols+1) 顶点矩阵
        self.cell_states = None    # rows x cols 格子状态矩阵

        # 交互状态
        self.selected_vertex = None
        self.dragging = False

        # 配置
        self.config_path = "config/grid_config.json"

    def load_image(self):
        """加载图像"""
        if not os.path.exists(self.image_path):
            raise FileNotFoundError(f"Image file not found: {self.image_path}")

        self.original_image = cv2.imread(self.image_path)
        if self.original_image is None:
            raise ValueError(f"Cannot read image: {self.image_path}")

        # 计算显示比例
        height, width = self.original_image.shape[:2]
        max_display_width = 1200
        max_display_height = 800

        if width > max_display_width or height > max_display_height:
            scale_w = max_display_width / width
            scale_h = max_display_height / height
            self.scale_factor = min(scale_w, scale_h)
        else:
            self.scale_factor = 1.0

        # 创建显示图像
        new_width = int(width * self.scale_factor)
        new_height = int(height * self.scale_factor)
        self.display_image = cv2.resize(self.original_image, (new_width, new_height))

        print(f"Image loaded: {width}x{height} -> {new_width}x{new_height} (scale: {self.scale_factor:.2f})")

    def initialize_grid(self):
        """初始化网格"""
        height, width = self.display_image.shape[:2]

        # 设置边距
        margin_x = width * 0.1
        margin_y = height * 0.1

        # 计算网格区域
        grid_width = width - 2 * margin_x
        grid_height = height - 2 * margin_y

        # 创建规则网格顶点
        self.grid_vertices = np.zeros((self.rows + 1, self.cols + 1, 2), dtype=np.float32)

        for i in range(self.rows + 1):
            for j in range(self.cols + 1):
                x = margin_x + j * grid_width / self.cols
                y = margin_y + i * grid_height / self.rows
                self.grid_vertices[i, j] = [x, y]

        # 初始化格子状态（全部有效）
        self.cell_states = np.ones((self.rows, self.cols), dtype=bool)

        print(f"Grid initialized: {self.rows+1}x{self.cols+1} vertices, {self.rows}x{self.cols} cells")

    def mouse_callback(self, event, x, y, flags, param):
        """鼠标回调函数"""
        if event == cv2.EVENT_LBUTTONDOWN:
            # 查找最近的顶点
            min_dist = float('inf')
            closest_vertex = None

            for i in range(self.rows + 1):
                for j in range(self.cols + 1):
                    vx, vy = self.grid_vertices[i, j]
                    dist = math.sqrt((x - vx)**2 + (y - vy)**2)
                    if dist < min_dist and dist < 20:  # 20像素容忍度
                        min_dist = dist
                        closest_vertex = (i, j)

            if closest_vertex:
                self.selected_vertex = closest_vertex
                self.dragging = True

        elif event == cv2.EVENT_MOUSEMOVE:
            if self.dragging and self.selected_vertex:
                # 拖拽顶点
                i, j = self.selected_vertex
                self.grid_vertices[i, j] = [x, y]
                self.update_display()

        elif event == cv2.EVENT_LBUTTONUP:
            self.dragging = False
            self.selected_vertex = None

        elif event == cv2.EVENT_RBUTTONDOWN:
            # 右键切换格子状态
            cell_i, cell_j = self.get_cell_at_position(x, y)
            if cell_i is not None and cell_j is not None:
                self.cell_states[cell_i, cell_j] = not self.cell_states[cell_i, cell_j]
                self.update_display()

    def get_cell_at_position(self, x, y):
        """获取位置处的格子索引"""
        for i in range(self.rows):
            for j in range(self.cols):
                # 获取格子四个顶点
                p1 = self.grid_vertices[i, j]
                p2 = self.grid_vertices[i, j+1]
                p3 = self.grid_vertices[i+1, j+1]
                p4 = self.grid_vertices[i+1, j]

                # 简单的点在多边形内判断
                points = np.array([p1, p2, p3, p4], dtype=np.int32)
                result = cv2.pointPolygonTest(points, (x, y), False)
                if result >= 0:
                    return i, j
        return None, None

    def draw_grid(self, image):
        """绘制网格"""
        # 绘制网格线
        for i in range(self.rows + 1):
            for j in range(self.cols):
                p1 = tuple(map(int, self.grid_vertices[i, j]))
                p2 = tuple(map(int, self.grid_vertices[i, j+1]))
                cv2.line(image, p1, p2, (0, 255, 0), 1)

        for j in range(self.cols + 1):
            for i in range(self.rows):
                p1 = tuple(map(int, self.grid_vertices[i, j]))
                p2 = tuple(map(int, self.grid_vertices[i+1, j]))
                cv2.line(image, p1, p2, (0, 255, 0), 1)

        # 绘制格子状态
        for i in range(self.rows):
            for j in range(self.cols):
                # 计算格子中心
                center_x = int(np.mean(self.grid_vertices[i:i+2, j:j+2, 0]))
                center_y = int(np.mean(self.grid_vertices[i:i+2, j:j+2, 1]))

                if self.cell_states[i, j]:
                    # 有效格子：绿色圆点
                    cv2.circle(image, (center_x, center_y), 3, (0, 255, 0), -1)
                else:
                    # 无效格子：红色叉号
                    cv2.line(image, (center_x-5, center_y-5), (center_x+5, center_y+5), (0, 0, 255), 2)
                    cv2.line(image, (center_x-5, center_y+5), (center_x+5, center_y-5), (0, 0, 255), 2)

        # 绘制顶点
        for i in range(self.rows + 1):
            for j in range(self.cols + 1):
                center = tuple(map(int, self.grid_vertices[i, j]))
                if self.selected_vertex == (i, j):
                    cv2.circle(image, center, 5, (0, 255, 255), -1)  # 选中顶点：黄色
                else:
                    cv2.circle(image, center, 3, (255, 0, 0), -1)   # 普通顶点：蓝色

    def update_display(self):
        """更新显示"""
        display_copy = self.display_image.copy()
        self.draw_grid(display_copy)

        # 显示说明文字
        instructions = [
            "Instructions:",
            "Left Click + Drag: Move vertex",
            "Right Click: Toggle cell state",
            "S Key: Save config",
            "R Key: Reset grid",
            "Q Key: Quit"
        ]

        y_offset = 25
        for instruction in instructions:
            cv2.putText(display_copy, instruction, (10, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            y_offset += 25

        # 显示网格信息
        info_text = f"Grid: {self.rows}x{self.cols}, Valid cells: {np.sum(self.cell_states)}/{self.rows*self.cols}"
        cv2.putText(display_copy, info_text, (10, display_copy.shape[0] - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)

        cv2.imshow(self.window_name, display_copy)

    def save_config(self):
        """保存配置"""
        try:
            # 确保配置目录存在
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

            # 转换到原图坐标系
            original_vertices = self.grid_vertices / self.scale_factor

            config_data = {
                "version": VERSION,
                "image_path": self.image_path,
                "image_size": {
                    "width": self.original_image.shape[1],
                    "height": self.original_image.shape[0]
                },
                "grid_dimensions": {
                    "rows": self.rows,
                    "cols": self.cols
                },
                "scale_factor": self.scale_factor,
                "grid_vertices": original_vertices.tolist(),
                "cell_states": self.cell_states.tolist(),
                "valid_cells": int(np.sum(self.cell_states)),
                "total_cells": self.rows * self.cols,
                "created_by": "GridEditorToolKit",
                "timestamp": str(Path().resolve())
            }

            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            print(f"[SUCCESS] Config saved: {self.config_path}")
            print(f"  Valid cells: {np.sum(self.cell_states)}/{self.rows * self.cols}")
            return True

        except Exception as e:
            print(f"[ERROR] Save failed: {e}")
            return False

    def load_config(self):
        """加载配置"""
        try:
            if not os.path.exists(self.config_path):
                return False

            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            # 验证配置
            if (config_data.get("grid_dimensions", {}).get("rows") != self.rows or
                config_data.get("grid_dimensions", {}).get("cols") != self.cols):
                print(f"[WARN] Grid size mismatch in config file")
                return False

            # 加载配置
            original_vertices = np.array(config_data["grid_vertices"], dtype=np.float32)
            self.grid_vertices = original_vertices * self.scale_factor
            self.cell_states = np.array(config_data["cell_states"], dtype=bool)

            print(f"[SUCCESS] Config loaded: {self.config_path}")
            print(f"  Version: {config_data.get('version', 'unknown')}")
            print(f"  Valid cells: {np.sum(self.cell_states)}/{self.rows * self.cols}")
            return True

        except Exception as e:
            print(f"[ERROR] Load failed: {e}")
            return False

    def reset_grid(self):
        """重置网格"""
        self.initialize_grid()
        self.update_display()
        print("[INFO] Grid reset to default")

    def run_editor(self):
        """运行编辑器主循环"""
        try:
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(self.window_name, self.mouse_callback)

            # 尝试加载现有配置
            if os.path.exists(self.config_path):
                print(f"Found existing config: {self.config_path}")
                if self.load_config():
                    print("[INFO] Previous configuration loaded")
                else:
                    print("[INFO] Using default grid")

            self.update_display()

            print()
            print("=" * 60)
            print("    Grid Editor Started")
            print("=" * 60)
            print(f"Image: {self.image_path}")
            print(f"Grid: {self.rows} rows x {self.cols} columns")
            print("Controls:")
            print("  Left Click + Drag: Move vertex precisely")
            print("  Right Click: Toggle cell valid/invalid")
            print("  S Key: Save configuration")
            print("  R Key: Reset to default grid")
            print("  Q Key: Quit editor")
            print("=" * 60)

            while True:
                key = cv2.waitKey(1) & 0xFF

                if key == ord('q') or key == ord('Q'):
                    break
                elif key == ord('s') or key == ord('S'):
                    self.save_config()
                elif key == ord('r') or key == ord('R'):
                    self.reset_grid()
                elif key == 27:  # ESC
                    break

            cv2.destroyAllWindows()
            print("[INFO] Editor closed normally")

        except Exception as e:
            print(f"[ERROR] Editor failed: {e}")
            cv2.destroyAllWindows()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Grid Editor Toolkit v{} - Portable Grid Calibration Tool".format(VERSION),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python grid_editor.py --image image.jpg --rows 14 --cols 10
  python grid_editor.py --image sample.png --rows 10 --cols 8 --config custom.json

For more information, visit: https://github.com/your-repo/grid-editor-toolkit
        """
    )

    parser.add_argument("--image", type=str, required=True,
                       help="Path to the image file")
    parser.add_argument("--rows", type=int, default=14,
                       help="Number of grid rows (default: 14)")
    parser.add_argument("--cols", type=int, default=10,
                       help="Number of grid columns (default: 10)")
    parser.add_argument("--config", type=str, default="config/grid_config.json",
                       help="Path to configuration file")
    parser.add_argument("--version", action="version",
                       version=f"Grid Editor Toolkit v{VERSION}")

    args = parser.parse_args()

    # 验证参数
    if not os.path.exists(args.image):
        print(f"[ERROR] Image file not found: {args.image}")
        return 1

    if args.rows <= 0 or args.cols <= 0:
        print(f"[ERROR] Invalid grid size: {args.rows}x{args.cols}")
        return 1

    try:
        # 创建编辑器实例
        editor = GridEditor(args.image, args.rows, args.cols)
        editor.config_path = args.config

        # 加载图像和初始化网格
        editor.load_image()
        editor.initialize_grid()

        # 运行编辑器
        editor.run_editor()

        print("[SUCCESS] Grid editor completed successfully")
        return 0

    except KeyboardInterrupt:
        print("\n[INFO] User interrupted")
        return 0
    except Exception as e:
        print(f"[ERROR] Failed to start: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())