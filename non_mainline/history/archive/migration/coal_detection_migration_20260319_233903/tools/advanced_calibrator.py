"""
高级柔性网格标定工具
处理复杂非标现场：遮挡、异形、变形格栅
三步走流程：ROI掩码 → 逻辑网格 → 柔性精调
"""

import cv2
import numpy as np
import json
import math
from pathlib import Path
import argparse
from typing import List, Tuple, Dict, Optional


class AdvancedCalibrator:
    """高级柔性网格标定工具"""

    def __init__(self, image_path: str):
        self.image_path = image_path
        self.original_img = None
        self.display_img = None
        self.scale_factor = 1.0

        # Step 1: ROI Mask
        self.roi_polygon = []  # 可见区域多边形点列表
        self.temp_point = None  # 临时点（跟随鼠标）
        self.roi_complete = False

        # Step 2: Logical Grid
        self.total_rows = 0
        self.total_cols = 0
        self.logical_complete = False

        # Step 3: Mesh Editing
        self.mesh_points = None  # (rows+1) x (cols+1) 网格点矩阵
        self.selected_point = None
        self.dragging = False
        self.shift_dragging = False  # 整体平移模式
        self.drag_offset = (0, 0)

        # 显示状态
        self.current_step = 1
        self.hover_point = None

        print(f"\n=== 高级柔性网格标定工具 ===")
        print(f"图片: {image_path}")
        print(f"处理非标现场：遮挡、异形、变形格栅")

    def _load_image(self):
        """加载并缩放图片"""
        self.original_img = cv2.imread(self.image_path)
        if self.original_img is None:
            raise ValueError(f"无法加载图片: {self.image_path}")

        h, w = self.original_img.shape[:2]
        print(f"原图尺寸: {w} x {h}")

        # 调整显示尺寸
        max_width, max_height = 1200, 800
        if w > max_width or h > max_height:
            self.scale_factor = min(max_width/w, max_height/h)
            display_w = int(w * self.scale_factor)
            display_h = int(h * self.scale_factor)
            self.display_img = cv2.resize(self.original_img, (display_w, display_h))
            print(f"显示尺寸: {display_w} x {display_h} (缩放: {self.scale_factor:.2f})")
        else:
            self.display_img = self.original_img.copy()
            print("显示原始尺寸")

    def _scale_to_original(self, x: float, y: float) -> Tuple[float, float]:
        """将显示坐标转换为原图坐标"""
        return x / self.scale_factor, y / self.scale_factor

    def _scale_to_display(self, x: float, y: float) -> Tuple[int, int]:
        """将原图坐标转换为显示坐标"""
        return int(x * self.scale_factor), int(y * self.scale_factor)

    def _mouse_callback(self, event, x, y, flags, param):
        """鼠标事件处理"""
        if self.current_step == 1:
            self._handle_roi_drawing(event, x, y, flags)
        elif self.current_step == 3:
            self._handle_mesh_editing(event, x, y, flags)

    def _handle_roi_drawing(self, event, x, y, flags):
        """处理ROI多边形绘制"""
        if event == cv2.EVENT_LBUTTONDOWN:
            # 添加点到多边形
            orig_x, orig_y = self._scale_to_original(x, y)
            self.roi_polygon.append([orig_x, orig_y])
            print(f"添加ROI点 {len(self.roi_polygon)}: ({orig_x:.1f}, {orig_y:.1f})")

        elif event == cv2.EVENT_MOUSEMOVE:
            # 更新临时点（预览）
            if not self.roi_complete and len(self.roi_polygon) > 0:
                self.temp_point = (x, y)

    def _handle_mesh_editing(self, event, x, y, flags):
        """处理网格编辑"""
        if event == cv2.EVENT_LBUTTONDOWN:
            if flags & cv2.EVENT_FLAG_SHIFTKEY:
                # Shift + 拖动 = 整体平移
                self.shift_dragging = True
                self.drag_offset = (x, y)
            else:
                # 普通拖动 = 节点调整
                self.selected_point = self._get_closest_point(x, y)
                if self.selected_point:
                    self.dragging = True
                    r, c = self.selected_point
                    print(f"选中节点: [{r},{c}]")

        elif event == cv2.EVENT_MOUSEMOVE:
            self.hover_point = self._get_closest_point(x, y)

            if self.shift_dragging:
                # 整体平移
                dx = x - self.drag_offset[0]
                dy = y - self.drag_offset[1]
                self.mesh_points[:, :, 0] += dx / self.scale_factor
                self.mesh_points[:, :, 1] += dy / self.scale_factor
                self.drag_offset = (x, y)

            elif self.dragging and self.selected_point:
                # 节点拖动
                r, c = self.selected_point
                orig_x, orig_y = self._scale_to_original(x, y)
                self.mesh_points[r, c] = [orig_x, orig_y]

        elif event == cv2.EVENT_LBUTTONUP:
            self.dragging = False
            self.shift_dragging = False
            self.selected_point = None

    def _get_closest_point(self, x: float, y: float, threshold: float = 15) -> Optional[Tuple[int, int]]:
        """找到最近的网格点"""
        if self.mesh_points is None:
            return None

        min_dist = threshold
        closest = None

        for r in range(self.mesh_points.shape[0]):
            for c in range(self.mesh_points.shape[1]):
                px, py = self._scale_to_display(*self.mesh_points[r, c])
                dist = math.hypot(x - px, y - py)
                if dist < min_dist:
                    min_dist = dist
                    closest = (r, c)

        return closest

    def _init_logical_grid(self):
        """初始化逻辑网格"""
        if not self.roi_polygon or len(self.roi_polygon) < 3:
            print("错误：ROI多边形无效")
            return False

        # 计算ROI外接矩形
        polygon_array = np.array(self.roi_polygon, dtype=np.float32)
        x_min, y_min = np.min(polygon_array, axis=0)
        x_max, y_max = np.max(polygon_array, axis=0)

        print(f"ROI外接矩形: ({x_min:.1f},{y_min:.1f}) - ({x_max:.1f},{y_max:.1f})")

        # 在外接矩形内生成均匀网格
        grid_w = x_max - x_min
        grid_h = y_max - y_min

        step_x = grid_w / self.total_cols
        step_y = grid_h / self.total_rows

        self.mesh_points = np.zeros((self.total_rows + 1, self.total_cols + 1, 2), dtype=np.float32)

        for r in range(self.total_rows + 1):
            for c in range(self.total_cols + 1):
                x = x_min + c * step_x
                y = y_min + r * step_y
                self.mesh_points[r, c] = [x, y]

        print(f"初始化网格: {self.total_rows+1} x {self.total_cols+1} 控制点")
        return True

    def _is_cell_valid(self, r: int, c: int) -> bool:
        """判断格子是否在ROI内"""
        if r >= self.total_rows or c >= self.total_cols:
            return False

        # 计算格子中心点
        p1 = self.mesh_points[r, c]
        p2 = self.mesh_points[r, c + 1]
        p3 = self.mesh_points[r + 1, c + 1]
        p4 = self.mesh_points[r + 1, c]

        center = (p1 + p2 + p3 + p4) / 4

        # 点在多边形内部检测
        polygon_array = np.array(self.roi_polygon, dtype=np.float32)
        result = cv2.pointPolygonTest(polygon_array, tuple(center), False)

        return result >= 0

    def _draw_current_state(self) -> np.ndarray:
        """绘制当前状态"""
        canvas = self.display_img.copy()

        if self.current_step == 1:
            # Step 1: 绘制ROI多边形
            canvas = self._draw_roi_polygon(canvas)
        elif self.current_step == 3:
            # Step 3: 绘制网格
            canvas = self._draw_mesh_grid(canvas)

        # 绘制步骤提示
        self._draw_step_info(canvas)

        return canvas

    def _draw_roi_polygon(self, canvas: np.ndarray) -> np.ndarray:
        """绘制ROI多边形"""
        # 绘制已确定的点
        for i, point in enumerate(self.roi_polygon):
            display_pt = self._scale_to_display(*point)
            cv2.circle(canvas, display_pt, 5, (0, 255, 0), -1)
            cv2.putText(canvas, str(i+1), (display_pt[0] + 10, display_pt[1] - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # 绘制多边形边
        if len(self.roi_polygon) > 1:
            display_pts = [self._scale_to_display(*pt) for pt in self.roi_polygon]
            pts_array = np.array(display_pts, dtype=np.int32)
            cv2.polylines(canvas, [pts_array], False, (0, 255, 0), 2)

        # 绘制临时线（到鼠标位置）
        if self.temp_point and len(self.roi_polygon) > 0:
            last_pt = self._scale_to_display(*self.roi_polygon[-1])
            cv2.line(canvas, last_pt, self.temp_point, (255, 255, 0), 1)

        # 绘制闭合预览
        if len(self.roi_polygon) > 2:
            first_pt = self._scale_to_display(*self.roi_polygon[0])
            if self.temp_point:
                cv2.line(canvas, self.temp_point, first_pt, (255, 255, 0), 1)

        return canvas

    def _draw_mesh_grid(self, canvas: np.ndarray) -> np.ndarray:
        """绘制网格"""
        # 绘制网格线
        for r in range(self.total_rows + 1):
            for c in range(self.total_cols + 1):
                cur_pt = self._scale_to_display(*self.mesh_points[r, c])

                # 水平线
                if c < self.total_cols:
                    next_pt = self._scale_to_display(*self.mesh_points[r, c + 1])
                    cv2.line(canvas, cur_pt, next_pt, (0, 255, 0), 1)

                # 垂直线
                if r < self.total_rows:
                    next_pt = self._scale_to_display(*self.mesh_points[r + 1, c])
                    cv2.line(canvas, cur_pt, next_pt, (0, 255, 0), 1)

        # 绘制网格节点
        for r in range(self.total_rows + 1):
            for c in range(self.total_cols + 1):
                pt = self._scale_to_display(*self.mesh_points[r, c])

                # 节点颜色
                if (r, c) == self.selected_point:
                    color, radius = (0, 0, 255), 6  # 红色：选中
                elif (r, c) == self.hover_point:
                    color, radius = (255, 255, 0), 5  # 黄色：悬停
                else:
                    color, radius = (0, 255, 0), 3  # 绿色：默认

                cv2.circle(canvas, pt, radius, color, -1)

        # 绘制格子状态（有效/无效）
        for r in range(self.total_rows):
            for c in range(self.total_cols):
                is_valid = self._is_cell_valid(r, c)

                # 格子四个角点
                p1 = self._scale_to_display(*self.mesh_points[r, c])
                p2 = self._scale_to_display(*self.mesh_points[r, c + 1])
                p3 = self._scale_to_display(*self.mesh_points[r + 1, c + 1])
                p4 = self._scale_to_display(*self.mesh_points[r + 1, c])

                pts = np.array([p1, p2, p3, p4], dtype=np.int32)

                if is_valid:
                    # 有效格子：绿色边框
                    cv2.polylines(canvas, [pts], True, (0, 255, 0), 2)
                    # 格子编号
                    center = np.mean(pts, axis=0).astype(int)
                    cell_id = r * self.total_cols + c + 1
                    cv2.putText(canvas, str(cell_id), tuple(center),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                else:
                    # 无效格子：灰色填充
                    cv2.fillPoly(canvas, [pts], (128, 128, 128))
                    cv2.polylines(canvas, [pts], True, (100, 100, 100), 1)

        # 绘制ROI掩码边界
        if len(self.roi_polygon) > 2:
            display_pts = [self._scale_to_display(*pt) for pt in self.roi_polygon]
            pts_array = np.array(display_pts, dtype=np.int32)
            cv2.polylines(canvas, [pts_array], True, (255, 0, 255), 2)

        return canvas

    def _draw_step_info(self, canvas: np.ndarray):
        """绘制步骤信息"""
        if self.current_step == 1:
            info = f"Step 1/3: 绘制可见区域 - 已添加{len(self.roi_polygon)}个点"
            cv2.putText(canvas, info, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(canvas, "点击添加点 | SPACE完成多边形 | 'r'重置", (20, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        elif self.current_step == 2:
            info = f"Step 2/3: 设置网格 - {self.total_rows}行 x {self.total_cols}列"
            cv2.putText(canvas, info, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(canvas, "在终端输入行列数后按任意键继续", (20, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        elif self.current_step == 3:
            valid_count = sum(1 for r in range(self.total_rows) for c in range(self.total_cols)
                             if self._is_cell_valid(r, c))
            info = f"Step 3/3: 精调网格 - {valid_count}/{self.total_rows * self.total_cols}格有效"
            cv2.putText(canvas, info, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(canvas, "拖拽节点调整 | Shift+拖拽整体移动 | 's'保存", (20, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

    def _input_grid_size(self):
        """输入网格尺寸"""
        print(f"\n=== Step 2: 逻辑拓扑定义 ===")
        print(f"即使有部分格子被遮挡，也要输入格栅的理论总尺寸")

        try:
            self.total_rows = int(input("总行数 (Total Rows): "))
            self.total_cols = int(input("总列数 (Total Cols): "))

            if self.total_rows <= 0 or self.total_cols <= 0:
                raise ValueError("行列数必须大于0")

            print(f"设置网格: {self.total_rows}行 x {self.total_cols}列")
            return True

        except ValueError as e:
            print(f"输入错误: {e}")
            return False

    def _save_config(self, output_path: str):
        """保存标定配置"""
        # 生成有效格子列表
        valid_cells = []
        for r in range(self.total_rows):
            for c in range(self.total_cols):
                if self._is_cell_valid(r, c):
                    # 格子四个角点
                    p1 = self.mesh_points[r, c].tolist()
                    p2 = self.mesh_points[r, c + 1].tolist()
                    p3 = self.mesh_points[r + 1, c + 1].tolist()
                    p4 = self.mesh_points[r + 1, c].tolist()

                    cell_id = r * self.total_cols + c

                    # 计算面积
                    pts_array = np.array([p1, p2, p3, p4], dtype=np.float32)
                    area = cv2.contourArea(pts_array)

                    valid_cells.append({
                        "id": cell_id,
                        "row": r,
                        "col": c,
                        "points": [p1, p2, p3, p4],
                        "area": float(area)
                    })

        config_data = {
            "source_image": self.image_path,
            "calibration_method": "advanced_flexible",
            "mask_polygon": self.roi_polygon,
            "logic_shape": [self.total_rows, self.total_cols],
            "mesh_points": self.mesh_points.tolist(),
            "total_theoretical": self.total_rows * self.total_cols,
            "valid_cells": valid_cells,
            "valid_count": len(valid_cells)
        }

        # 保存配置
        Path(output_path).parent.mkdir(exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)

        print(f"\n[SAVED] 高级标定配置已保存: {output_path}")
        print(f"         理论网格: {self.total_rows}行 x {self.total_cols}列")
        print(f"         有效格子: {len(valid_cells)}/{self.total_rows * self.total_cols}")
        print(f"         覆盖率: {len(valid_cells)/(self.total_rows * self.total_cols)*100:.1f}%")

    def run(self, output_path: str = "config/grid_advanced.json"):
        """运行高级标定工具"""
        self._load_image()

        window_name = "Advanced Grid Calibrator"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(window_name, self._mouse_callback)

        print(f"\n=== Step 1: 外部形状定义 ===")
        print(f"用鼠标点击绘制可见区域多边形")
        print(f"避开遮挡物（如横梁、电机）和黑边")

        while True:
            canvas = self._draw_current_state()
            cv2.imshow(window_name, canvas)

            key = cv2.waitKey(30) & 0xFF

            if self.current_step == 1:
                if key == ord(' '):  # 完成ROI绘制
                    if len(self.roi_polygon) >= 3:
                        print(f"ROI多边形完成，共{len(self.roi_polygon)}个点")
                        self.roi_complete = True
                        self.current_step = 2

                        # 输入网格尺寸
                        if self._input_grid_size():
                            if self._init_logical_grid():
                                self.current_step = 3
                                print(f"\n=== Step 3: 柔性网格精调 ===")
                        else:
                            self.current_step = 1
                    else:
                        print("至少需要3个点才能形成多边形")

                elif key == ord('r'):  # 重置ROI
                    print("重置ROI多边形")
                    self.roi_polygon = []
                    self.temp_point = None

            elif self.current_step == 3:
                if key == ord('s'):  # 保存配置
                    self._save_config(output_path)

                elif key == ord('r'):  # 重置网格
                    print("重置为均匀网格")
                    self._init_logical_grid()

            if key == ord('q'):  # 退出
                break

        cv2.destroyAllWindows()
        print(f"\n高级柔性网格标定完成！")


def main():
    parser = argparse.ArgumentParser(description="高级柔性网格标定工具")
    parser.add_argument("image_path", help="格栅图片路径")
    parser.add_argument("--output", default="config/grid_advanced.json", help="输出配置文件")

    args = parser.parse_args()

    try:
        calibrator = AdvancedCalibrator(args.image_path)
        calibrator.run(args.output)

        print(f"\n标定成功！")
        print(f"配置文件: {args.output}")
        print(f"现在可以用此配置进行精确检测")

    except Exception as e:
        print(f"标定失败: {e}")


if __name__ == "__main__":
    main()