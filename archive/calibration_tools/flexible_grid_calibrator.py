"""
工业级柔性网格标定工具 (Flexible Grid Calibrator)
处理透视畸变、遮挡、格栅大小不一等复杂现场情况
三步流程：ROI Masking -> Logical Topology -> Mesh Fitting
"""

import cv2
import numpy as np
import json
import math
from pathlib import Path
import argparse
from typing import List, Tuple, Optional, Dict


class FlexibleGridCalibrator:
    """工业级柔性网格标定工具"""

    def __init__(self, image_path: str):
        # 图像相关
        self.image_path = image_path
        self.original_image = None
        self.display_image = None
        self.scale_factor = 1.0

        # 状态机
        self.current_step = 1  # 1: ROI Masking, 2: Logical Topology, 3: Mesh Fitting

        # Step 1: ROI Masking
        self.roi_points = []  # 多边形顶点
        self.roi_mask = None
        self.temp_point = None  # 跟随鼠标的临时点

        # Step 2: Logical Topology
        self.rows = 0
        self.cols = 0

        # Step 3: Mesh Fitting
        self.mesh_vertices = None  # (rows+1) x (cols+1) 网格顶点
        self.selected_vertex = None
        self.dragging = False
        self.hover_vertex = None

        # 交互状态
        self.valid_cells_count = 0

        print("=== 工业级柔性网格标定工具 ===")
        print("处理透视畸变、遮挡、格栅大小不一等复杂现场情况")

    def load_and_prepare_image(self):
        """加载图像并准备显示"""
        self.original_image = cv2.imread(self.image_path)
        if self.original_image is None:
            raise ValueError(f"无法加载图片: {self.image_path}")

        h, w = self.original_image.shape[:2]
        print(f"原图尺寸: {w} x {h}")

        # 计算显示缩放比例
        max_display_width = 1280
        max_display_height = 960

        if w > max_display_width or h > max_display_height:
            self.scale_factor = min(max_display_width / w, max_display_height / h)
            display_w = int(w * self.scale_factor)
            display_h = int(h * self.scale_factor)
            self.display_image = cv2.resize(self.original_image, (display_w, display_h))
            print(f"显示缩放: {display_w} x {display_h} (比例: {self.scale_factor:.3f})")
        else:
            self.display_image = self.original_image.copy()
            self.scale_factor = 1.0
            print("显示原始尺寸")

    def display_to_original(self, x: float, y: float) -> Tuple[float, float]:
        """显示坐标转换为原图坐标"""
        return x / self.scale_factor, y / self.scale_factor

    def original_to_display(self, x: float, y: float) -> Tuple[int, int]:
        """原图坐标转换为显示坐标"""
        return int(x * self.scale_factor), int(y * self.scale_factor)

    def mouse_callback(self, event, x, y, flags, param):
        """鼠标事件回调"""
        if self.current_step == 1:
            self._handle_roi_masking(event, x, y)
        elif self.current_step == 3:
            self._handle_mesh_fitting(event, x, y, flags)

    def _handle_roi_masking(self, event, x, y):
        """Step 1: 处理ROI多边形绘制"""
        if event == cv2.EVENT_LBUTTONDOWN:
            # 添加多边形顶点
            orig_x, orig_y = self.display_to_original(x, y)
            self.roi_points.append([orig_x, orig_y])
            print(f"ROI顶点 {len(self.roi_points)}: ({orig_x:.1f}, {orig_y:.1f})")

        elif event == cv2.EVENT_MOUSEMOVE:
            # 更新临时点（预览下一个连线）
            if len(self.roi_points) > 0:
                self.temp_point = (x, y)

    def _handle_mesh_fitting(self, event, x, y, flags):
        """Step 3: 处理网格拖拽调整"""
        if event == cv2.EVENT_LBUTTONDOWN:
            self.selected_vertex = self._get_nearest_vertex(x, y)
            if self.selected_vertex is not None:
                self.dragging = True
                r, c = self.selected_vertex
                print(f"选中顶点: [{r},{c}]")

        elif event == cv2.EVENT_MOUSEMOVE:
            self.hover_vertex = self._get_nearest_vertex(x, y)

            if self.dragging and self.selected_vertex is not None:
                # 拖拽顶点
                r, c = self.selected_vertex
                orig_x, orig_y = self.display_to_original(x, y)
                self.mesh_vertices[r, c] = [orig_x, orig_y]

        elif event == cv2.EVENT_LBUTTONUP:
            if self.dragging and self.selected_vertex is not None:
                r, c = self.selected_vertex
                orig_x, orig_y = self.display_to_original(x, y)
                print(f"顶点[{r},{c}]移动到: ({orig_x:.1f}, {orig_y:.1f})")
            self.dragging = False
            self.selected_vertex = None

    def _get_nearest_vertex(self, x: int, y: int, threshold: int = 20) -> Optional[Tuple[int, int]]:
        """查找最近的网格顶点"""
        if self.mesh_vertices is None:
            return None

        min_dist = threshold
        nearest = None

        for r in range(self.mesh_vertices.shape[0]):
            for c in range(self.mesh_vertices.shape[1]):
                vx, vy = self.original_to_display(*self.mesh_vertices[r, c])
                dist = math.hypot(x - vx, y - vy)
                if dist < min_dist:
                    min_dist = dist
                    nearest = (r, c)

        return nearest

    def create_roi_mask(self):
        """创建ROI掩码"""
        h, w = self.original_image.shape[:2]
        self.roi_mask = np.zeros((h, w), dtype=np.uint8)

        if len(self.roi_points) >= 3:
            pts = np.array(self.roi_points, dtype=np.int32)
            cv2.fillPoly(self.roi_mask, [pts], 255)
            print(f"ROI掩码创建完成: {len(self.roi_points)}个顶点")

    def init_logical_topology(self):
        """Step 2: 初始化逻辑拓扑"""
        print(f"\n=== Step 2: 逻辑拓扑定义 ===")

        # 如果已经设置了行列数，直接使用
        if self.rows > 0 and self.cols > 0:
            print(f"使用预设网格: {self.rows}行 x {self.cols}列")
            self._init_uniform_mesh()
            return True

        # 否则进行交互式输入
        print("定义格栅的理论行列数（即使有些被遮挡）")
        try:
            self.rows = int(input("格栅行数 (Rows): "))
            self.cols = int(input("格栅列数 (Cols): "))

            if self.rows <= 0 or self.cols <= 0:
                raise ValueError("行列数必须大于0")

            print(f"逻辑拓扑: {self.rows}行 x {self.cols}列")

            # 初始化均匀网格
            self._init_uniform_mesh()
            return True

        except (ValueError, EOFError) as e:
            print(f"输入错误: {e}")
            return False

    def _init_uniform_mesh(self):
        """在ROI区域内初始化均匀网格"""
        # 计算ROI外接矩形
        if len(self.roi_points) < 3:
            return

        roi_array = np.array(self.roi_points)
        x_min, y_min = np.min(roi_array, axis=0)
        x_max, y_max = np.max(roi_array, axis=0)

        # 添加边距
        margin_x = (x_max - x_min) * 0.05
        margin_y = (y_max - y_min) * 0.05

        grid_x_min = x_min + margin_x
        grid_x_max = x_max - margin_x
        grid_y_min = y_min + margin_y
        grid_y_max = y_max - margin_y

        # 创建网格顶点矩阵
        self.mesh_vertices = np.zeros((self.rows + 1, self.cols + 1, 2), dtype=np.float32)

        for r in range(self.rows + 1):
            for c in range(self.cols + 1):
                x = grid_x_min + c * (grid_x_max - grid_x_min) / self.cols
                y = grid_y_min + r * (grid_y_max - grid_y_min) / self.rows
                self.mesh_vertices[r, c] = [x, y]

        print(f"初始化网格: {self.rows+1} x {self.cols+1} 顶点")

    def is_cell_valid(self, row: int, col: int) -> bool:
        """判断格子是否在ROI内（有效）"""
        if self.roi_mask is None or self.mesh_vertices is None:
            return False
        if row >= self.rows or col >= self.cols:
            return False

        # 计算格子中心点
        p1 = self.mesh_vertices[row, col]
        p2 = self.mesh_vertices[row, col + 1]
        p3 = self.mesh_vertices[row + 1, col + 1]
        p4 = self.mesh_vertices[row + 1, col]

        center_x = (p1[0] + p2[0] + p3[0] + p4[0]) / 4
        center_y = (p1[1] + p2[1] + p3[1] + p4[1]) / 4

        # 检查中心点是否在ROI掩码内
        cx, cy = int(center_x), int(center_y)
        if 0 <= cx < self.roi_mask.shape[1] and 0 <= cy < self.roi_mask.shape[0]:
            return self.roi_mask[cy, cx] > 0
        return False

    def render_current_step(self):
        """渲染当前步骤的界面"""
        canvas = self.display_image.copy()

        if self.current_step == 1:
            canvas = self._render_roi_masking(canvas)
        elif self.current_step == 3:
            canvas = self._render_mesh_fitting(canvas)

        # 绘制步骤信息
        self._draw_step_info(canvas)

        return canvas

    def _render_roi_masking(self, canvas):
        """渲染Step 1: ROI多边形绘制"""
        # 绘制已确定的顶点
        for i, point in enumerate(self.roi_points):
            px, py = self.original_to_display(*point)
            cv2.circle(canvas, (px, py), 6, (0, 255, 0), -1)
            cv2.putText(canvas, str(i+1), (px+10, py-10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # 绘制多边形边
        if len(self.roi_points) > 1:
            display_pts = [self.original_to_display(*pt) for pt in self.roi_points]
            pts_array = np.array(display_pts, dtype=np.int32)
            cv2.polylines(canvas, [pts_array], False, (0, 255, 0), 2)

        # 绘制临时连线
        if self.temp_point and len(self.roi_points) > 0:
            last_pt = self.original_to_display(*self.roi_points[-1])
            cv2.line(canvas, last_pt, self.temp_point, (255, 255, 0), 1)

        # 绘制闭合预览
        if len(self.roi_points) > 2 and self.temp_point:
            first_pt = self.original_to_display(*self.roi_points[0])
            cv2.line(canvas, self.temp_point, first_pt, (255, 255, 0), 1)

        return canvas

    def _render_mesh_fitting(self, canvas):
        """渲染Step 3: 网格拟合"""
        if self.mesh_vertices is None:
            return canvas

        # 统计有效格子
        self.valid_cells_count = 0

        # 绘制网格线
        for r in range(self.rows + 1):
            for c in range(self.cols + 1):
                vx, vy = self.original_to_display(*self.mesh_vertices[r, c])

                # 水平线
                if c < self.cols:
                    next_vx, next_vy = self.original_to_display(*self.mesh_vertices[r, c + 1])
                    cv2.line(canvas, (vx, vy), (next_vx, next_vy), (0, 255, 0), 1)

                # 垂直线
                if r < self.rows:
                    next_vx, next_vy = self.original_to_display(*self.mesh_vertices[r + 1, c])
                    cv2.line(canvas, (vx, vy), (next_vx, next_vy), (0, 255, 0), 1)

        # 绘制格子状态和顶点
        for r in range(self.rows):
            for c in range(self.cols):
                is_valid = self.is_cell_valid(r, c)

                # 格子四个顶点
                pts = []
                for dr, dc in [(0, 0), (0, 1), (1, 1), (1, 0)]:
                    vx, vy = self.original_to_display(*self.mesh_vertices[r + dr, c + dc])
                    pts.append([vx, vy])

                pts_array = np.array(pts, dtype=np.int32)

                if is_valid:
                    # 有效格子：绿色边框 + ID
                    cv2.polylines(canvas, [pts_array], True, (0, 255, 0), 2)
                    self.valid_cells_count += 1

                    # 格子ID
                    center_x = sum(pt[0] for pt in pts) // 4
                    center_y = sum(pt[1] for pt in pts) // 4
                    cell_id = r * self.cols + c + 1
                    cv2.putText(canvas, str(cell_id), (center_x-10, center_y+5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 2)
                    cv2.putText(canvas, str(cell_id), (center_x-10, center_y+5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
                else:
                    # 无效格子：灰色填充
                    cv2.fillPoly(canvas, [pts_array], (128, 128, 128))
                    cv2.polylines(canvas, [pts_array], True, (100, 100, 100), 1)

        # 绘制网格顶点
        for r in range(self.rows + 1):
            for c in range(self.cols + 1):
                vx, vy = self.original_to_display(*self.mesh_vertices[r, c])

                # 顶点颜色状态
                if (r, c) == self.selected_vertex:
                    color, radius = (0, 0, 255), 8  # 红色：选中
                elif (r, c) == self.hover_vertex:
                    color, radius = (255, 255, 0), 6  # 黄色：悬停
                else:
                    color, radius = (0, 255, 0), 4  # 绿色：默认

                cv2.circle(canvas, (vx, vy), radius, color, -1)

        # 绘制ROI边界
        if len(self.roi_points) > 2:
            display_pts = [self.original_to_display(*pt) for pt in self.roi_points]
            pts_array = np.array(display_pts, dtype=np.int32)
            cv2.polylines(canvas, [pts_array], True, (255, 0, 255), 2)

        return canvas

    def _draw_step_info(self, canvas):
        """绘制步骤信息（优化界面，不遮挡格栅）"""
        h, w = canvas.shape[:2]

        if self.current_step == 1:
            title = f"Step 1: ROI ({len(self.roi_points)} pts)"
            instruction = "Click: Add | SPACE: Next | R: Reset"
        elif self.current_step == 2:
            title = f"Step 2: Grid {self.rows}x{self.cols}"
            instruction = "Input in terminal"
        elif self.current_step == 3:
            total_cells = self.rows * self.cols if self.rows > 0 and self.cols > 0 else 0
            title = f"Step 3: Valid {self.valid_cells_count}/{total_cells}"
            instruction = "Drag: Adjust | S: Save | R: Reset"

        # 使用更小的文字和紧凑布局
        font_scale = 0.5
        thickness = 1

        # 计算文字尺寸
        title_size = cv2.getTextSize(title, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)[0]
        instr_size = cv2.getTextSize(instruction, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)[0]

        # 背景框尺寸
        bg_width = max(title_size[0], instr_size[0]) + 20
        bg_height = 40

        # 绘制半透明背景（右下角）
        overlay = canvas.copy()
        bg_x = w - bg_width - 10
        bg_y = h - bg_height - 10

        cv2.rectangle(overlay, (bg_x, bg_y), (w - 10, h - 10), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, canvas, 0.3, 0, canvas)

        # 绘制边框
        cv2.rectangle(canvas, (bg_x, bg_y), (w - 10, h - 10), (255, 255, 255), 1)

        # 绘制文字（右下角）
        cv2.putText(canvas, title, (bg_x + 10, bg_y + 15),
                   cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 255), thickness)
        cv2.putText(canvas, instruction, (bg_x + 10, bg_y + 30),
                   cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), thickness)

    def save_calibration_data(self, output_path: str):
        """保存标定数据"""
        if self.mesh_vertices is None or self.roi_mask is None:
            raise ValueError("标定数据不完整")

        # 生成有效格子列表
        valid_cells = []

        for r in range(self.rows):
            for c in range(self.cols):
                if self.is_cell_valid(r, c):
                    # 格子四个顶点（原图坐标）
                    points = [
                        self.mesh_vertices[r, c].tolist(),
                        self.mesh_vertices[r, c + 1].tolist(),
                        self.mesh_vertices[r + 1, c + 1].tolist(),
                        self.mesh_vertices[r + 1, c].tolist()
                    ]

                    # 计算中心和面积
                    center_x = sum(pt[0] for pt in points) / 4
                    center_y = sum(pt[1] for pt in points) / 4

                    pts_array = np.array(points, dtype=np.float32)
                    area = cv2.contourArea(pts_array)

                    cell_data = {
                        "id": r * self.cols + c,
                        "row": r,
                        "col": c,
                        "points": points,
                        "center": [center_x, center_y],
                        "area": float(area)
                    }

                    valid_cells.append(cell_data)

        # 构建完整数据结构
        h, w = self.original_image.shape[:2]
        calibration_data = {
            "calibration_meta": {
                "image_width": w,
                "image_height": h,
                "logical_rows": self.rows,
                "logical_cols": self.cols
            },
            "valid_cells": valid_cells
        }

        # 保存文件
        Path(output_path).parent.mkdir(exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(calibration_data, f, ensure_ascii=False, indent=2)

        print(f"\n[SAVED] 标定数据已保存: {output_path}")
        print(f"         图片尺寸: {w} x {h}")
        print(f"         逻辑网格: {self.rows}行 x {self.cols}列")
        print(f"         有效格子: {len(valid_cells)}/{self.rows * self.cols}")
        print(f"         覆盖率: {len(valid_cells)/(self.rows * self.cols)*100:.1f}%")

    def run_calibration(self, output_path: str = "config/grid_baseline.json"):
        """运行标定流程"""
        self.load_and_prepare_image()

        window_name = "Flexible Grid Calibrator"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(window_name, self.mouse_callback)

        print(f"\n=== Step 1: ROI Masking ===")
        print("用鼠标绘制格栅有效区域多边形，避开遮挡物")

        while True:
            canvas = self.render_current_step()
            cv2.imshow(window_name, canvas)

            key = cv2.waitKey(30) & 0xFF

            if self.current_step == 1:  # ROI Masking
                if key == ord(' '):  # 确认多边形
                    if len(self.roi_points) >= 3:
                        self.create_roi_mask()
                        print(f"\n=== Step 2: Logical Topology ===")
                        if self.init_logical_topology():
                            self.current_step = 3
                            print(f"\n=== Step 3: Mesh Fitting ===")
                            print("拖拽网格顶点以贴合实际格栅")
                    else:
                        print("至少需要3个点形成多边形")

                elif key == ord('r'):  # 重置
                    print("重置ROI多边形")
                    self.roi_points = []
                    self.temp_point = None

            elif self.current_step == 3:  # Mesh Fitting
                if key == ord('s'):  # 保存
                    try:
                        self.save_calibration_data(output_path)
                    except Exception as e:
                        print(f"保存失败: {e}")

                elif key == ord('r'):  # 重置网格
                    print("重置为均匀网格")
                    self._init_uniform_mesh()

            if key == ord('q'):  # 退出
                break

        cv2.destroyAllWindows()
        print("\n标定工具退出")


def main():
    parser = argparse.ArgumentParser(description="工业级柔性网格标定工具")
    parser.add_argument("image_path", help="格栅图片路径")
    parser.add_argument("--output", default="config/grid_baseline.json",
                       help="输出配置文件路径")
    parser.add_argument("--rows", type=int, default=13, help="格栅行数 (默认: 13)")
    parser.add_argument("--cols", type=int, default=10, help="格栅列数 (默认: 10)")

    args = parser.parse_args()

    try:
        calibrator = FlexibleGridCalibrator(args.image_path)
        calibrator.rows = args.rows
        calibrator.cols = args.cols
        calibrator.run_calibration(args.output)

        print("\n=== 标定完成 ===")
        print(f"配置文件: {args.output}")
        print("现在可以使用此配置进行精确的格栅检测")

    except Exception as e:
        print(f"标定失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()