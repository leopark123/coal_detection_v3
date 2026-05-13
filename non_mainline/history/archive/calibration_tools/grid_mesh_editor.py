"""
柔性网格精细标定工具
功能：鼠标拖拽调整每一个格栅角点，解决格栅大小不一、弯曲变形问题
解决现场复杂情况：物理形变、安装误差、非线性畸变
"""

import cv2
import numpy as np
import json
import yaml
import math
from pathlib import Path
import argparse


class GridMeshEditor:
    """柔性网格编辑器"""

    def __init__(self, image_path: str, rows: int = 8, cols: int = 8):
        self.image_path = image_path
        self.rows = rows
        self.cols = cols

        # 网格状态
        self.points = None  # (rows+1) x (cols+1) 的网格点矩阵
        self.selected_point = None
        self.dragging = False
        self.hover_point = None

        # 显示相关
        self.original_img = None
        self.display_img = None
        self.scale_factor = 1.0

        print(f"\n=== 柔性网格标定工具 ===")
        print(f"目标：{rows}行 x {cols}列 格栅网格")
        print(f"图片：{image_path}")

    def _load_image(self):
        """加载图片并调整显示尺寸"""
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
            print(f"显示尺寸: {display_w} x {display_h} (缩放比例: {self.scale_factor:.2f})")
        else:
            self.display_img = self.original_img.copy()
            self.scale_factor = 1.0
            print("显示原始尺寸")

    def _init_uniform_grid(self):
        """初始化均匀网格作为起点"""
        h, w = self.display_img.shape[:2]

        # 留边距，生成均匀网格
        margin_x = w * 0.1
        margin_y = h * 0.1

        grid_w = w - 2 * margin_x
        grid_h = h - 2 * margin_y

        step_x = grid_w / self.cols
        step_y = grid_h / self.rows

        self.points = np.zeros((self.rows + 1, self.cols + 1, 2), dtype=np.float32)

        for r in range(self.rows + 1):
            for c in range(self.cols + 1):
                x = margin_x + c * step_x
                y = margin_y + r * step_y
                self.points[r, c] = [x, y]

        print(f"初始化网格完成：{self.rows+1} x {self.cols+1} 个控制点")

    def _scale_point_to_original(self, x: float, y: float) -> tuple:
        """将显示坐标转换为原图坐标"""
        orig_x = x / self.scale_factor
        orig_y = y / self.scale_factor
        return orig_x, orig_y

    def _scale_points_to_original(self, points: np.ndarray) -> np.ndarray:
        """将显示坐标矩阵转换为原图坐标"""
        return points / self.scale_factor

    def _get_closest_point(self, x: float, y: float, threshold: float = 15) -> tuple:
        """找到鼠标点击处最近的网格点"""
        min_dist = threshold
        closest = None

        for r in range(self.rows + 1):
            for c in range(self.cols + 1):
                px, py = self.points[r, c]
                dist = math.hypot(x - px, y - py)
                if dist < min_dist:
                    min_dist = dist
                    closest = (r, c)

        return closest

    def _mouse_callback(self, event, x, y, flags, param):
        """鼠标事件处理"""
        if event == cv2.EVENT_LBUTTONDOWN:
            # 开始拖拽
            self.selected_point = self._get_closest_point(x, y)
            if self.selected_point:
                self.dragging = True
                print(f"选中控制点: 第{self.selected_point[0]}行 第{self.selected_point[1]}列")

        elif event == cv2.EVENT_MOUSEMOVE:
            # 更新悬停点
            self.hover_point = self._get_closest_point(x, y)

            # 拖拽中
            if self.dragging and self.selected_point:
                r, c = self.selected_point
                self.points[r, c] = [x, y]

        elif event == cv2.EVENT_LBUTTONUP:
            # 结束拖拽
            if self.dragging and self.selected_point:
                r, c = self.selected_point
                orig_x, orig_y = self._scale_point_to_original(x, y)
                print(f"控制点[{r},{c}]移动到: ({orig_x:.1f}, {orig_y:.1f})")

            self.dragging = False
            self.selected_point = None

    def _draw_grid(self) -> np.ndarray:
        """绘制当前网格状态"""
        canvas = self.display_img.copy()

        # 绘制网格线
        for r in range(self.rows + 1):
            for c in range(self.cols + 1):
                cur_pt = tuple(map(int, self.points[r, c]))

                # 绘制水平线
                if c < self.cols:
                    next_pt = tuple(map(int, self.points[r, c + 1]))
                    cv2.line(canvas, cur_pt, next_pt, (0, 255, 0), 2)

                # 绘制垂直线
                if r < self.rows:
                    next_pt = tuple(map(int, self.points[r + 1, c]))
                    cv2.line(canvas, cur_pt, next_pt, (0, 255, 0), 2)

        # 绘制控制点
        for r in range(self.rows + 1):
            for c in range(self.cols + 1):
                pt = tuple(map(int, self.points[r, c]))

                # 根据状态选择颜色
                if (r, c) == self.selected_point:
                    color = (0, 0, 255)  # 红色：选中
                    radius = 6
                elif (r, c) == self.hover_point:
                    color = (255, 255, 0)  # 青色：悬停
                    radius = 5
                else:
                    color = (0, 255, 0)  # 绿色：默认
                    radius = 4

                cv2.circle(canvas, pt, radius, color, -1)

                # 绘制控制点标号（仅在角点）
                if (r % self.rows == 0 or r == self.rows) and (c % self.cols == 0 or c == self.cols):
                    cv2.putText(canvas, f"{r},{c}", (pt[0] + 8, pt[1] - 8),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

        # 绘制格子编号（中心点）
        for r in range(self.rows):
            for c in range(self.cols):
                # 计算格子中心
                p1 = self.points[r, c]
                p2 = self.points[r, c + 1]
                p3 = self.points[r + 1, c + 1]
                p4 = self.points[r + 1, c]

                center = (p1 + p2 + p3 + p4) / 4
                center = tuple(map(int, center))

                cell_id = r * self.cols + c + 1
                cv2.putText(canvas, str(cell_id), (center[0] - 10, center[1] + 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                cv2.putText(canvas, str(cell_id), (center[0] - 10, center[1] + 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        return canvas

    def _generate_rois(self) -> list:
        """生成不规则四边形ROI列表"""
        # 转换为原图坐标
        original_points = self._scale_points_to_original(self.points)

        rois = []
        for r in range(self.rows):
            for c in range(self.cols):
                # 四个角点：左上、右上、右下、左下
                p1 = original_points[r, c].tolist()       # 左上
                p2 = original_points[r, c + 1].tolist()   # 右上
                p3 = original_points[r + 1, c + 1].tolist() # 右下
                p4 = original_points[r + 1, c].tolist()   # 左下

                cell_id = r * self.cols + c

                # 计算面积（用于后续检测基准）
                points_array = np.array([p1, p2, p3, p4], dtype=np.float32)
                area = cv2.contourArea(points_array)

                roi_data = {
                    "id": cell_id,
                    "row": r,
                    "col": c,
                    "points": [p1, p2, p3, p4],
                    "area": float(area)
                }

                rois.append(roi_data)

        return rois

    def _save_config(self, output_path: str):
        """保存柔性网格配置"""
        rois = self._generate_rois()

        config_data = {
            "source_image": self.image_path,
            "calibration_method": "flexible_mesh",
            "grid_shape": [self.rows, self.cols],
            "mesh_type": "irregular_quadrilaterals",
            "total_rois": len(rois),
            "rois": rois
        }

        # 确保目录存在
        Path(output_path).parent.mkdir(exist_ok=True)

        # 保存为YAML（更易读）或JSON
        if output_path.endswith('.yaml') or output_path.endswith('.yml'):
            with open(output_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, default_flow_style=False,
                         allow_unicode=True, sort_keys=False)
        else:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)

        print(f"\n[SAVED] 柔性网格配置已保存: {output_path}")
        print(f"         总ROI数量: {len(rois)}")
        print(f"         网格形状: {self.rows}行 x {self.cols}列")

    def run(self, output_path: str = "config/grid_flexible.yaml"):
        """运行柔性网格编辑器"""
        # 1. 加载图片
        self._load_image()

        # 2. 初始化网格
        self._init_uniform_grid()

        # 3. 设置交互界面
        window_name = "Flexible Grid Editor"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(window_name, self._mouse_callback)

        print(f"\n=== 操作说明 ===")
        print(f"鼠标操作:")
        print(f"  - 拖拽绿色控制点：调整网格形状")
        print(f"  - 悬停显示青色：预览选择")
        print(f"  - 点击显示红色：开始拖拽")
        print(f"")
        print(f"键盘操作:")
        print(f"  - 's'：保存当前网格配置")
        print(f"  - 'r'：重置为均匀网格")
        print(f"  - 'q'：退出编辑器")
        print(f"")
        print(f"目标：让绿色网格线完美贴合真实的格栅结构")
        print(f"{'='*50}")

        # 4. 主循环
        while True:
            # 绘制当前状态
            canvas = self._draw_grid()
            cv2.imshow(window_name, canvas)

            # 处理按键
            key = cv2.waitKey(30) & 0xFF

            if key == ord('s'):
                # 保存配置
                self._save_config(output_path)

            elif key == ord('r'):
                # 重置网格
                print("\n重置为均匀网格...")
                self._init_uniform_grid()

            elif key == ord('q'):
                # 退出
                break

        cv2.destroyAllWindows()
        print(f"\n柔性网格标定完成!")
        return self._generate_rois()


def main():
    parser = argparse.ArgumentParser(description="柔性网格精细标定工具")
    parser.add_argument("image_path", help="格栅图片路径")
    parser.add_argument("--rows", type=int, default=8, help="网格行数")
    parser.add_argument("--cols", type=int, default=8, help="网格列数")
    parser.add_argument("--output", default="config/grid_flexible.yaml",
                       help="输出配置文件路径")

    args = parser.parse_args()

    try:
        editor = GridMeshEditor(args.image_path, args.rows, args.cols)
        editor.run(args.output)

        print(f"\n🎉 标定成功！")
        print(f"配置文件: {args.output}")
        print(f"现在可以运行支持柔性网格的检测器")

    except Exception as e:
        print(f"❌ 标定失败: {e}")


if __name__ == "__main__":
    main()