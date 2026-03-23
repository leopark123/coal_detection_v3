"""
稳定通用网格标定工具 (Stable Grid Editor)
功能完整、运行稳定的格栅标定工具

特点:
- 支持任意行列数网格
- 多种启动方式（命令行参数、配置文件、图形界面输入）
- 稳定的错误处理
- 配置保存/加载
- 一键启动功能
"""

import cv2
import numpy as np
import json
import math
import os
from pathlib import Path
import argparse
from typing import List, Tuple, Optional, Dict
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog


class StableGridEditor:
    """稳定的通用网格标定工具"""

    def __init__(self, image_path: str = "", rows: int = 14, cols: int = 10):
        # 基本参数
        self.image_path = image_path
        self.rows = rows
        self.cols = cols

        # 图像相关
        self.original_image = None
        self.display_image = None
        self.scale_factor = 1.0
        self.window_name = "Stable Grid Editor - Press S:Save R:Reset Q:Quit"

        # 网格数据
        self.grid_vertices = None  # (rows+1) x (cols+1) 顶点矩阵
        self.cell_states = None    # rows x cols 格子状态矩阵

        # 交互状态
        self.selected_vertex = None
        self.dragging = False
        self.hover_vertex = None

        # 配置
        self.config_path = "config/grid_baseline.json"

    def setup_with_gui(self):
        """使用图形界面设置参数"""
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口

        try:
            # 1. 选择图片
            if not self.image_path:
                print("请选择图片文件...")
                self.image_path = filedialog.askopenfilename(
                    title="选择格栅图片",
                    filetypes=[
                        ("图片文件", "*.jpg *.jpeg *.png *.bmp"),
                        ("所有文件", "*.*")
                    ],
                    initialdir="tests/mock_data"
                )

                if not self.image_path:
                    print("未选择图片，使用默认图片")
                    self.image_path = "tests/mock_data/clean/2.png"

            # 2. 设置网格尺寸
            if self.rows <= 0:
                rows_input = simpledialog.askinteger(
                    "网格设置",
                    "请输入网格行数:",
                    initialvalue=14,
                    minvalue=1,
                    maxvalue=50
                )
                if rows_input:
                    self.rows = rows_input
                else:
                    self.rows = 14

            if self.cols <= 0:
                cols_input = simpledialog.askinteger(
                    "网格设置",
                    "请输入网格列数:",
                    initialvalue=10,
                    minvalue=1,
                    maxvalue=50
                )
                if cols_input:
                    self.cols = cols_input
                else:
                    self.cols = 10

            # 3. 是否加载现有配置
            if os.path.exists(self.config_path):
                load_config = messagebox.askyesno(
                    "配置文件",
                    f"发现现有配置文件: {self.config_path}\\n是否加载现有配置？"
                )
                if load_config:
                    if self.load_config():
                        print(f"已加载配置: {self.config_path}")
                    else:
                        print("配置加载失败，将使用默认设置")

        except Exception as e:
            print(f"图形界面设置出错: {e}")
            print("将使用默认参数或命令行参数")

        finally:
            root.destroy()

    def setup_with_defaults(self):
        """使用默认参数设置"""
        if not self.image_path:
            # 寻找可用的测试图片
            test_images = [
                "tests/mock_data/clean/2.png",
                "tests/mock_data/clean/3.png",
                "tests/mock_data/clean/4.png"
            ]

            for img_path in test_images:
                if os.path.exists(img_path):
                    self.image_path = img_path
                    break

            if not self.image_path:
                raise FileNotFoundError("未找到可用的测试图片")

        if self.rows <= 0:
            self.rows = 14
        if self.cols <= 0:
            self.cols = 10

        print(f"使用默认设置:")
        print(f"  图片: {self.image_path}")
        print(f"  网格: {self.rows}行 × {self.cols}列")

    def load_image(self):
        """加载图像"""
        if not os.path.exists(self.image_path):
            raise FileNotFoundError(f"图片文件不存在: {self.image_path}")

        self.original_image = cv2.imread(self.image_path)
        if self.original_image is None:
            raise ValueError(f"无法读取图片: {self.image_path}")

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

        print(f"图像加载成功: {width}x{height} -> {new_width}x{new_height} (比例: {self.scale_factor:.2f})")

    def initialize_grid(self):
        """初始化网格"""
        height, width = self.display_image.shape[:2]

        # 设置边距（避免贴边）
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

        print(f"网格初始化完成: {self.rows+1}×{self.cols+1}个顶点")

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

        cv2.imshow(self.window_name, display_copy)

    def save_config(self):
        """保存配置"""
        try:
            # 确保配置目录存在
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

            # 转换到原图坐标系
            original_vertices = self.grid_vertices / self.scale_factor

            config_data = {
                "image_path": self.image_path,
                "rows": self.rows,
                "cols": self.cols,
                "grid_vertices": original_vertices.tolist(),
                "cell_states": self.cell_states.tolist(),
                "scale_factor": self.scale_factor
            }

            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            print(f"配置已保存: {self.config_path}")
            return True

        except Exception as e:
            print(f"保存配置失败: {e}")
            return False

    def load_config(self):
        """加载配置"""
        try:
            if not os.path.exists(self.config_path):
                return False

            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            # 验证配置
            if (config_data.get("rows") != self.rows or
                config_data.get("cols") != self.cols):
                print(f"配置文件网格尺寸不匹配 (文件: {config_data.get('rows')}x{config_data.get('cols')}, 当前: {self.rows}x{self.cols})")
                return False

            # 加载配置
            original_vertices = np.array(config_data["grid_vertices"], dtype=np.float32)
            self.grid_vertices = original_vertices * self.scale_factor
            self.cell_states = np.array(config_data["cell_states"], dtype=bool)

            print(f"配置已加载: {self.config_path}")
            return True

        except Exception as e:
            print(f"加载配置失败: {e}")
            return False

    def reset_grid(self):
        """重置网格"""
        self.initialize_grid()
        self.update_display()
        print("网格已重置")

    def run_editor(self):
        """运行编辑器主循环"""
        try:
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(self.window_name, self.mouse_callback)

            self.update_display()

            print()
            print("=" * 50)
            print("网格标定工具已启动")
            print(f"图片: {self.image_path}")
            print(f"网格: {self.rows}行 × {self.cols}列")
            print("=" * 50)

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

        except Exception as e:
            print(f"编辑器运行出错: {e}")
            cv2.destroyAllWindows()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="稳定通用网格标定工具")
    parser.add_argument("--image", type=str, default="", help="图片路径")
    parser.add_argument("--rows", type=int, default=14, help="网格行数")
    parser.add_argument("--cols", type=int, default=10, help="网格列数")
    parser.add_argument("--gui", action="store_true", help="使用图形界面设置参数")
    parser.add_argument("--auto", action="store_true", help="使用默认参数自动启动")

    args = parser.parse_args()

    try:
        editor = StableGridEditor(args.image, args.rows, args.cols)

        if args.auto:
            # 自动模式：使用默认参数
            editor.setup_with_defaults()
        elif args.gui or (not args.image and args.rows <= 0):
            # GUI模式：参数不完整时自动启用
            editor.setup_with_gui()
        else:
            # 命令行模式：使用提供的参数
            if not args.image:
                editor.setup_with_defaults()

        # 加载图像和初始化网格
        editor.load_image()
        editor.initialize_grid()

        # 运行编辑器
        editor.run_editor()

        print("编辑器正常退出")

    except KeyboardInterrupt:
        print("\\n用户中断")
    except Exception as e:
        print(f"启动失败: {e}")
        input("按Enter键退出...")


if __name__ == "__main__":
    main()