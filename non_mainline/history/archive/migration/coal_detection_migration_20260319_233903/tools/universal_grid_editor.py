"""
通用网格标定工具 (Universal Grid Editor)
支持任意行列数、图片选择、配置保存/加载
可复用的格栅标定小工具
"""

import cv2
import numpy as np
import json
import math
import os
from pathlib import Path
import argparse
from typing import List, Tuple, Optional, Dict


class UniversalGridEditor:
    """通用网格标定工具"""

    def __init__(self):
        # 基本参数（待设置）
        self.image_path = ""
        self.rows = 0
        self.cols = 0

        # 图像相关
        self.original_image = None
        self.display_image = None
        self.scale_factor = 1.0

        # 网格数据
        self.grid_vertices = None  # (rows+1) x (cols+1) 顶点矩阵
        self.cell_states = None    # rows x cols 格子状态矩阵 (True=有效, False=无效)

        # 交互状态
        self.selected_vertex = None
        self.dragging = False
        self.hover_vertex = None

    def setup_parameters(self):
        """设置工具参数"""
        print("=" * 50)
        print("    通用网格标定工具 V2.0")
        print("=" * 50)
        print("支持任意行列数的格栅网格标定")
        print()

        # 1. 选择图片
        self._select_image()

        # 2. 输入网格参数
        self._input_grid_parameters()

        # 3. 询问是否加载已有配置
        self._ask_load_config()

        print()
        print(f"设置完成:")
        print(f"  图片: {Path(self.image_path).name}")
        print(f"  网格: {self.rows}行 × {self.cols}列")
        print(f"  总格子: {self.rows * self.cols}个")

    def _select_image(self):
        """选择图片文件"""
        print("1. 选择图片文件")
        print("   可选图片:")

        # 列出可用图片
        image_dirs = [
            "tests/mock_data/clean/",
            "tests/mock_data/coal_light/",
            "tests/mock_data/coal_heavy/",
            "./"
        ]

        available_images = []
        for img_dir in image_dirs:
            if Path(img_dir).exists():
                for ext in ['*.png', '*.jpg', '*.jpeg', '*.bmp']:
                    available_images.extend(Path(img_dir).glob(ext))

        if available_images:
            for i, img in enumerate(available_images[:10]):  # 最多显示10个
                print(f"   [{i+1}] {img}")

        print()

        while True:
            choice = input("   请选择: [1-N] 输入数字, 或输入完整路径: ").strip()

            try:
                # 尝试解析为数字
                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(available_images):
                        self.image_path = str(available_images[idx])
                        break
                    else:
                        print(f"   错误: 请输入 1-{len(available_images)} 之间的数字")
                        continue
                else:
                    # 直接路径
                    if Path(choice).exists() and Path(choice).suffix.lower() in ['.png', '.jpg', '.jpeg', '.bmp']:
                        self.image_path = choice
                        break
                    else:
                        print("   错误: 文件不存在或不是有效的图片格式")
                        continue
            except:
                print("   错误: 输入格式不正确")
                continue

        print(f"   已选择: {self.image_path}")

    def _input_grid_parameters(self):
        """输入网格参数"""
        print()
        print("2. 设置网格参数")

        while True:
            try:
                self.rows = int(input("   格栅行数 (如14): ").strip())
                if self.rows <= 0:
                    print("   错误: 行数必须大于0")
                    continue
                break
            except ValueError:
                print("   错误: 请输入有效的数字")

        while True:
            try:
                self.cols = int(input("   格栅列数 (如10): ").strip())
                if self.cols <= 0:
                    print("   错误: 列数必须大于0")
                    continue
                break
            except ValueError:
                print("   错误: 请输入有效的数字")

    def _ask_load_config(self):
        """询问是否加载已有配置"""
        print()
        print("3. 配置选项")

        # 查找相关配置文件
        config_files = list(Path("config").glob("*.json"))
        if config_files:
            print("   发现已有配置文件:")
            for i, cfg in enumerate(config_files[:5]):
                print(f"   [{i+1}] {cfg.name}")

            choice = input("   是否加载已有配置? [y/N] 或输入数字选择: ").strip().lower()

            if choice == 'y' or choice == 'yes':
                # 加载最新的配置
                latest_config = max(config_files, key=lambda x: x.stat().st_mtime)
                self._load_existing_config(str(latest_config))
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(config_files):
                    self._load_existing_config(str(config_files[idx]))

    def _load_existing_config(self, config_path: str):
        """加载已有配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            if 'calibration_meta' in config:
                meta = config['calibration_meta']
                if 'rows' in meta and 'cols' in meta:
                    self.rows = meta['rows']
                    self.cols = meta['cols']
                    print(f"   已加载配置: {self.rows}行 × {self.cols}列")
        except:
            print(f"   警告: 配置文件加载失败")

    def load_and_prepare_image(self):
        """加载图片并准备显示"""
        self.original_image = cv2.imread(self.image_path)
        if self.original_image is None:
            raise ValueError(f"无法加载图片: {self.image_path}")

        h, w = self.original_image.shape[:2]
        print(f"\n图片信息: {w} x {h} 像素")

        # 显示缩放
        max_width, max_height = 1400, 1000
        if w > max_width or h > max_height:
            self.scale_factor = min(max_width / w, max_height / h)
            display_w = int(w * self.scale_factor)
            display_h = int(h * self.scale_factor)
            self.display_image = cv2.resize(self.original_image, (display_w, display_h))
            print(f"显示缩放: {display_w} x {display_h} (比例: {self.scale_factor:.3f})")
        else:
            self.display_image = self.original_image.copy()
            self.scale_factor = 1.0
            print("显示原始尺寸")

    def display_to_original(self, x: float, y: float) -> Tuple[float, float]:
        """显示坐标转原图坐标"""
        return x / self.scale_factor, y / self.scale_factor

    def original_to_display(self, x: float, y: float) -> Tuple[int, int]:
        """原图坐标转显示坐标"""
        return int(x * self.scale_factor), int(y * self.scale_factor)

    def initialize_grid(self):
        """初始化覆盖全图80%区域的均匀网格"""
        h, w = self.original_image.shape[:2]

        # 计算网格区域（留10%边距）
        margin_x = w * 0.1
        margin_y = h * 0.1

        grid_x_min = margin_x
        grid_x_max = w - margin_x
        grid_y_min = margin_y
        grid_y_max = h - margin_y

        # 创建顶点矩阵
        self.grid_vertices = np.zeros((self.rows + 1, self.cols + 1, 2), dtype=np.float32)

        for r in range(self.rows + 1):
            for c in range(self.cols + 1):
                x = grid_x_min + c * (grid_x_max - grid_x_min) / self.cols
                y = grid_y_min + r * (grid_y_max - grid_y_min) / self.rows
                self.grid_vertices[r, c] = [x, y]

        # 初始化格子状态（全部有效）
        self.cell_states = np.ones((self.rows, self.cols), dtype=bool)

        print(f"初始化网格: {self.rows+1}×{self.cols+1} 顶点")

    def get_nearest_vertex(self, x: int, y: int, threshold: int = 15) -> Optional[Tuple[int, int]]:
        """查找最近的顶点"""
        min_dist = threshold
        nearest = None

        for r in range(self.rows + 1):
            for c in range(self.cols + 1):
                vx, vy = self.original_to_display(*self.grid_vertices[r, c])
                dist = math.hypot(x - vx, y - vy)
                if dist < min_dist:
                    min_dist = dist
                    nearest = (r, c)

        return nearest

    def get_cell_at_point(self, x: int, y: int) -> Optional[Tuple[int, int]]:
        """获取指定点所在的格子"""
        orig_x, orig_y = self.display_to_original(x, y)

        for r in range(self.rows):
            for c in range(self.cols):
                # 获取格子四个顶点
                p1 = self.grid_vertices[r, c]
                p2 = self.grid_vertices[r, c + 1]
                p3 = self.grid_vertices[r + 1, c + 1]
                p4 = self.grid_vertices[r + 1, c]

                # 构建四边形
                quad = np.array([p1, p2, p3, p4], dtype=np.float32)

                # 点在多边形内测试
                result = cv2.pointPolygonTest(quad, (orig_x, orig_y), False)
                if result >= 0:
                    return (r, c)

        return None

    def mouse_callback(self, event, x, y, flags, param):
        """鼠标事件处理"""
        if event == cv2.EVENT_LBUTTONDOWN:
            # 左键：开始拖拽顶点
            self.selected_vertex = self.get_nearest_vertex(x, y)
            if self.selected_vertex:
                self.dragging = True
                r, c = self.selected_vertex
                print(f"选中顶点: [{r},{c}]")

        elif event == cv2.EVENT_RBUTTONDOWN:
            # 右键：切换格子状态
            cell = self.get_cell_at_point(x, y)
            if cell:
                r, c = cell
                self.cell_states[r, c] = not self.cell_states[r, c]
                state_text = "有效" if self.cell_states[r, c] else "无效"
                print(f"格子[{r},{c}] 状态切换为: {state_text}")

        elif event == cv2.EVENT_MOUSEMOVE:
            # 鼠标移动
            self.hover_vertex = self.get_nearest_vertex(x, y)

            if self.dragging and self.selected_vertex:
                # 拖拽中：只移动当前选中的点
                if not hasattr(self, 'last_mouse_pos'):
                    self.last_mouse_pos = (x, y)

                dx = (x - self.last_mouse_pos[0]) / self.scale_factor
                dy = (y - self.last_mouse_pos[1]) / self.scale_factor

                r, c = self.selected_vertex
                self.grid_vertices[r, c] += [dx, dy]

                self.last_mouse_pos = (x, y)

        elif event == cv2.EVENT_LBUTTONUP:
            # 左键释放：结束拖拽
            if self.dragging and self.selected_vertex:
                r, c = self.selected_vertex
                vx, vy = self.grid_vertices[r, c]
                print(f"顶点[{r},{c}]移动到: ({vx:.1f}, {vy:.1f})")

            self.dragging = False
            self.selected_vertex = None
            if hasattr(self, 'last_mouse_pos'):
                del self.last_mouse_pos

    def render_grid(self):
        """渲染当前网格状态"""
        canvas = self.display_image.copy()

        # 统计有效格子数
        valid_count = np.sum(self.cell_states)
        total_count = self.rows * self.cols

        # 绘制格子
        for r in range(self.rows):
            for c in range(self.cols):
                # 获取格子四个顶点
                pts = []
                for dr, dc in [(0, 0), (0, 1), (1, 1), (1, 0)]:
                    vx, vy = self.original_to_display(*self.grid_vertices[r + dr, c + dc])
                    pts.append([vx, vy])

                pts_array = np.array(pts, dtype=np.int32)

                if self.cell_states[r, c]:
                    # 有效格子：绿色边框 + ID
                    cv2.polylines(canvas, [pts_array], True, (0, 255, 0), 2)

                    # 格子ID
                    center_x = sum(pt[0] for pt in pts) // 4
                    center_y = sum(pt[1] for pt in pts) // 4
                    cell_id = r * self.cols + c + 1

                    cv2.putText(canvas, str(cell_id), (center_x - 10, center_y + 5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 2)
                    cv2.putText(canvas, str(cell_id), (center_x - 10, center_y + 5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
                else:
                    # 无效格子：灰色填充 + 红色交叉
                    cv2.fillPoly(canvas, [pts_array], (128, 128, 128))
                    cv2.polylines(canvas, [pts_array], True, (100, 100, 100), 1)

                    # 绘制红色交叉线
                    cv2.line(canvas, tuple(pts[0]), tuple(pts[2]), (0, 0, 255), 2)
                    cv2.line(canvas, tuple(pts[1]), tuple(pts[3]), (0, 0, 255), 2)

        # 绘制网格线
        for r in range(self.rows + 1):
            for c in range(self.cols + 1):
                vx, vy = self.original_to_display(*self.grid_vertices[r, c])

                # 水平线
                if c < self.cols:
                    next_vx, next_vy = self.original_to_display(*self.grid_vertices[r, c + 1])
                    cv2.line(canvas, (vx, vy), (next_vx, next_vy), (255, 255, 0), 1)

                # 垂直线
                if r < self.rows:
                    next_vx, next_vy = self.original_to_display(*self.grid_vertices[r + 1, c])
                    cv2.line(canvas, (vx, vy), (next_vx, next_vy), (255, 255, 0), 1)

        # 绘制顶点
        for r in range(self.rows + 1):
            for c in range(self.cols + 1):
                vx, vy = self.original_to_display(*self.grid_vertices[r, c])

                # 顶点颜色
                if (r, c) == self.selected_vertex:
                    color, radius = (0, 0, 255), 8  # 红色：选中
                elif (r, c) == self.hover_vertex:
                    color, radius = (255, 255, 0), 6  # 黄色：悬停
                else:
                    color, radius = (255, 255, 0), 4  # 黄色：默认

                cv2.circle(canvas, (vx, vy), radius, color, -1)

        # 绘制状态信息（右下角）
        h, w = canvas.shape[:2]
        status_text = f"Grid: {self.rows}x{self.cols} | Valid: {valid_count}/{total_count}"
        instruction_text = "Left: Drag | Right: Toggle | S: Save | R: Reset | Q: Quit"

        # 半透明背景
        overlay = canvas.copy()
        text_bg_x = w - 450
        text_bg_y = h - 50
        cv2.rectangle(overlay, (text_bg_x, text_bg_y), (w - 10, h - 10), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, canvas, 0.3, 0, canvas)

        # 绘制文字
        cv2.putText(canvas, status_text, (text_bg_x + 10, text_bg_y + 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        cv2.putText(canvas, instruction_text, (text_bg_x + 10, text_bg_y + 35),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

        return canvas

    def save_configuration(self, output_path: str = None):
        """保存配置文件"""
        if output_path is None:
            # 自动生成文件名
            timestamp = Path(self.image_path).stem
            output_path = f"config/grid_{timestamp}_{self.rows}x{self.cols}.json"

        # 生成有效格子列表
        valid_cells = []

        for r in range(self.rows):
            for c in range(self.cols):
                if self.cell_states[r, c]:  # 只保存有效格子
                    # 格子四个角点
                    points = [
                        self.grid_vertices[r, c].tolist(),
                        self.grid_vertices[r, c + 1].tolist(),
                        self.grid_vertices[r + 1, c + 1].tolist(),
                        self.grid_vertices[r + 1, c].tolist()
                    ]

                    # 计算面积
                    pts_array = np.array(points, dtype=np.float32)
                    area = cv2.contourArea(pts_array)

                    cell_data = {
                        "id": r * self.cols + c,
                        "row": r,
                        "col": c,
                        "points": points,
                        "area": float(area)
                    }

                    valid_cells.append(cell_data)

        # 构建配置数据
        h, w = self.original_image.shape[:2]
        config_data = {
            "calibration_meta": {
                "image_width": w,
                "image_height": h,
                "rows": self.rows,
                "cols": self.cols,
                "source_image": self.image_path,
                "calibration_method": "universal_grid_editor",
                "timestamp": str(Path(output_path).stem)
            },
            "valid_cells": valid_cells
        }

        # 保存文件
        Path(output_path).parent.mkdir(exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)

        print(f"\n[SAVED] 配置已保存: {output_path}")
        print(f"         网格规格: {self.rows}行 × {self.cols}列")
        print(f"         有效格子: {len(valid_cells)}/{self.rows * self.cols}")
        print(f"         覆盖率: {len(valid_cells)/(self.rows * self.cols)*100:.1f}%")

        return output_path

    def run_editor(self):
        """运行编辑器主循环"""
        print(f"\n=== 开始网格编辑 ===")
        print(f"操作说明:")
        print(f"  左键拖拽: 精确移动单个顶点")
        print(f"  右键点击: 切换格子有效/无效状态")
        print(f"  按键: S保存, R重置, Q退出")
        print(f"")

        self.load_and_prepare_image()
        self.initialize_grid()

        window_name = f"Universal Grid Editor - {self.rows}x{self.cols}"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(window_name, self.mouse_callback)

        while True:
            canvas = self.render_grid()
            cv2.imshow(window_name, canvas)

            key = cv2.waitKey(30) & 0xFF

            if key == ord('s'):
                # 保存配置
                try:
                    saved_path = self.save_configuration()
                    print(f"配置已保存，可在下次使用时加载")
                except Exception as e:
                    print(f"保存失败: {e}")

            elif key == ord('r'):
                # 重置网格
                print("重置网格...")
                self.initialize_grid()

            elif key == ord('q'):
                # 退出
                break

        cv2.destroyAllWindows()
        print("\n通用网格编辑器退出")


def main():
    parser = argparse.ArgumentParser(description="通用网格标定工具")
    parser.add_argument("--auto", help="自动模式：图片路径")
    parser.add_argument("--rows", type=int, help="行数（自动模式）")
    parser.add_argument("--cols", type=int, help="列数（自动模式）")
    parser.add_argument("--output", help="输出文件（自动模式）")

    args = parser.parse_args()

    try:
        editor = UniversalGridEditor()

        if args.auto and args.rows and args.cols:
            # 自动模式（命令行参数）
            editor.image_path = args.auto
            editor.rows = args.rows
            editor.cols = args.cols
            print(f"自动模式: {editor.rows}行 × {editor.cols}列")
        else:
            # 交互模式
            editor.setup_parameters()

        editor.run_editor()

        print("\n=== 标定完成 ===")
        print("配置文件已保存到 config/ 目录")

    except KeyboardInterrupt:
        print("\n用户取消操作")
    except Exception as e:
        print(f"运行失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()