"""
改进的网格提取器
通过分析蓝色网格线的交点来确定每个格子位置
"""

import cv2
import numpy as np
import json
from pathlib import Path
import argparse
from typing import List, Dict, Tuple


class GridCellExtractor:
    """网格格子提取器"""

    def __init__(self, annotated_image_path: str):
        self.image_path = annotated_image_path
        self.image = None
        self.blue_mask = None
        self.grid_cells = []

    def extract_grid_lines(self) -> Tuple[List[Tuple[int, int, int, int]], List[Tuple[int, int, int, int]]]:
        """提取水平和垂直网格线"""
        # 1. 加载图片
        self.image = cv2.imread(self.image_path)
        if self.image is None:
            raise ValueError(f"无法加载图片: {self.image_path}")

        print(f"分析标注图片: {Path(self.image_path).name}")
        print(f"图片尺寸: {self.image.shape[1]} x {self.image.shape[0]}")

        # 2. 转换为HSV并提取蓝色
        hsv = cv2.cvtColor(self.image, cv2.COLOR_BGR2HSV)

        # 调整蓝色HSV范围
        lower_blue = np.array([90, 50, 50])
        upper_blue = np.array([130, 255, 255])

        self.blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)

        # 形态学操作
        kernel = np.ones((3, 3), np.uint8)
        self.blue_mask = cv2.morphologyEx(self.blue_mask, cv2.MORPH_CLOSE, kernel)
        self.blue_mask = cv2.morphologyEx(self.blue_mask, cv2.MORPH_OPEN, kernel)

        # 3. 使用霍夫变换检测直线
        lines = cv2.HoughLinesP(self.blue_mask, 1, np.pi/180, threshold=50,
                               minLineLength=30, maxLineGap=10)

        if lines is None:
            return [], []

        # 4. 分类线条：水平线和垂直线
        horizontal_lines = []
        vertical_lines = []

        for line in lines:
            x1, y1, x2, y2 = line[0]

            # 计算角度
            angle = np.arctan2(abs(y2 - y1), abs(x2 - x1)) * 180 / np.pi

            if angle < 20:  # 接近水平
                horizontal_lines.append((x1, y1, x2, y2))
            elif angle > 70:  # 接近垂直
                vertical_lines.append((x1, y1, x2, y2))

        print(f"检测到 {len(horizontal_lines)} 条水平线, {len(vertical_lines)} 条垂直线")
        return horizontal_lines, vertical_lines

    def find_grid_intersections(self, h_lines: List, v_lines: List) -> List[Tuple[int, int]]:
        """找到网格交点"""
        intersections = []

        for h_line in h_lines:
            hx1, hy1, hx2, hy2 = h_line

            for v_line in v_lines:
                vx1, vy1, vx2, vy2 = v_line

                # 计算两条线的交点
                intersection = self._line_intersection(
                    (hx1, hy1, hx2, hy2),
                    (vx1, vy1, vx2, vy2)
                )

                if intersection:
                    x, y = intersection
                    # 检查交点是否在图像范围内
                    if 0 <= x < self.image.shape[1] and 0 <= y < self.image.shape[0]:
                        intersections.append((int(x), int(y)))

        # 去重（合并相近的点）
        unique_intersections = []
        for x, y in intersections:
            is_duplicate = False
            for ux, uy in unique_intersections:
                if abs(x - ux) < 10 and abs(y - uy) < 10:
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_intersections.append((x, y))

        print(f"找到 {len(unique_intersections)} 个网格交点")
        return unique_intersections

    def _line_intersection(self, line1: Tuple, line2: Tuple) -> Tuple[float, float]:
        """计算两条线段的交点"""
        x1, y1, x2, y2 = line1
        x3, y3, x4, y4 = line2

        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-10:
            return None

        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
        u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom

        # 检查交点是否在线段范围内
        if 0 <= t <= 1 and 0 <= u <= 1:
            x = x1 + t * (x2 - x1)
            y = y1 + t * (y2 - y1)
            return (x, y)

        return None

    def create_grid_cells(self, intersections: List[Tuple[int, int]]) -> List[Dict]:
        """基于交点创建网格格子"""
        if len(intersections) < 4:
            print("交点数量不足，无法构建网格")
            return []

        # 按Y坐标排序，然后按X坐标排序
        sorted_points = sorted(intersections, key=lambda p: (p[1], p[0]))

        # 估算行列数
        # 统计每个Y坐标的点数
        y_groups = {}
        for x, y in sorted_points:
            y_key = y // 20 * 20  # 20像素容差分组
            if y_key not in y_groups:
                y_groups[y_key] = []
            y_groups[y_key].append((x, y))

        # 找到最常见的列数
        col_counts = [len(points) for points in y_groups.values()]
        most_common_cols = max(col_counts) if col_counts else 0

        # 估算行数
        rows = len(y_groups)
        cols = most_common_cols

        print(f"估算网格: {rows-1}行 x {cols-1}列 (使用 {rows}x{cols} 交点)")

        # 重新整理交点为规则矩阵
        grid_points = self._organize_points_to_grid(sorted_points, rows, cols)

        # 创建格子
        cells = []
        cell_id = 0

        for r in range(rows - 1):
            for c in range(cols - 1):
                try:
                    # 格子的四个角点
                    top_left = grid_points[r][c]
                    top_right = grid_points[r][c + 1]
                    bottom_right = grid_points[r + 1][c + 1]
                    bottom_left = grid_points[r + 1][c]

                    # 计算格子中心和面积
                    center_x = (top_left[0] + bottom_right[0]) // 2
                    center_y = (top_left[1] + bottom_right[1]) // 2

                    width = abs(top_right[0] - top_left[0])
                    height = abs(bottom_left[1] - top_left[1])
                    area = width * height

                    cell = {
                        'id': cell_id,
                        'row': r,
                        'col': c,
                        'center_x': center_x,
                        'center_y': center_y,
                        'width': width,
                        'height': height,
                        'area': float(area),
                        'points': [
                            list(top_left),
                            list(top_right),
                            list(bottom_right),
                            list(bottom_left)
                        ]
                    }

                    cells.append(cell)
                    cell_id += 1

                except (IndexError, KeyError):
                    continue

        print(f"成功创建 {len(cells)} 个网格格子")
        self.grid_cells = cells
        return cells

    def _organize_points_to_grid(self, points: List[Tuple[int, int]],
                                rows: int, cols: int) -> List[List[Tuple[int, int]]]:
        """将交点整理为规则的网格矩阵"""
        # 按Y坐标分组
        y_groups = {}
        for x, y in points:
            y_key = y // 20 * 20  # 容差分组
            if y_key not in y_groups:
                y_groups[y_key] = []
            y_groups[y_key].append((x, y))

        # 排序Y组
        sorted_y_keys = sorted(y_groups.keys())

        grid = []
        for y_key in sorted_y_keys:
            # 每一行按X坐标排序
            row_points = sorted(y_groups[y_key], key=lambda p: p[0])
            grid.append(row_points)

        # 补齐不足的行列
        while len(grid) < rows:
            grid.append([])

        for row in grid:
            while len(row) < cols:
                row.append((0, 0))  # 占位符

        return grid

    def generate_config(self, output_path: str):
        """生成检测配置"""
        if not self.grid_cells:
            raise ValueError("没有提取到网格格子")

        # 估算总行列数
        max_row = max(cell['row'] for cell in self.grid_cells) + 1
        max_col = max(cell['col'] for cell in self.grid_cells) + 1

        # 生成全图ROI掩码
        h, w = self.image.shape[:2]
        mask_polygon = [[0, 0], [w, 0], [w, h], [0, h]]

        config_data = {
            "source_image": self.image_path,
            "calibration_method": "grid_line_intersection",
            "mask_polygon": mask_polygon,
            "logic_shape": [max_row, max_col],
            "total_theoretical": max_row * max_col,
            "valid_cells": self.grid_cells,
            "valid_count": len(self.grid_cells),
            "extraction_info": {
                "method": "hough_lines + intersections",
                "estimated_grid": f"{max_row}x{max_col}",
                "coverage_ratio": len(self.grid_cells) / (max_row * max_col)
            }
        }

        # 保存配置
        Path(output_path).parent.mkdir(exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)

        print(f"\n[SAVED] 网格提取配置已保存: {output_path}")
        print(f"         网格形状: {max_row}行 x {max_col}列")
        print(f"         有效格子: {len(self.grid_cells)}")
        print(f"         覆盖率: {len(self.grid_cells)/(max_row*max_col)*100:.1f}%")

    def visualize_extraction(self, output_path: str = None):
        """可视化提取结果"""
        if not self.grid_cells:
            return None

        canvas = self.image.copy()

        # 绘制提取的格子
        for cell in self.grid_cells:
            points = np.array(cell['points'], dtype=np.int32)

            # 绘制格子边框
            cv2.polylines(canvas, [points], True, (0, 255, 0), 2)

            # 绘制格子ID
            center = (cell['center_x'], cell['center_y'])
            cv2.putText(canvas, str(cell['id'] + 1), center,
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            cv2.putText(canvas, str(cell['id'] + 1), center,
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

        # 添加统计信息
        max_row = max(cell['row'] for cell in self.grid_cells) + 1 if self.grid_cells else 0
        max_col = max(cell['col'] for cell in self.grid_cells) + 1 if self.grid_cells else 0

        info_text = f"Extracted: {len(self.grid_cells)} cells, Grid: {max_row}x{max_col}"
        cv2.putText(canvas, info_text, (20, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        if output_path:
            cv2.imwrite(output_path, canvas)
            print(f"可视化结果已保存: {output_path}")

        return canvas

    def run_extraction(self, output_config: str, output_visual: str = None):
        """执行完整的提取流程"""
        print("开始网格格子提取...")

        # 1. 提取网格线
        h_lines, v_lines = self.extract_grid_lines()

        # 2. 找到交点
        intersections = self.find_grid_intersections(h_lines, v_lines)

        # 3. 创建格子
        cells = self.create_grid_cells(intersections)

        # 4. 生成配置
        if cells:
            self.generate_config(output_config)

            # 5. 可视化
            if output_visual:
                self.visualize_extraction(output_visual)

            return True
        else:
            print("未能成功提取网格格子")
            return False


def main():
    parser = argparse.ArgumentParser(description="改进的网格格子提取器")
    parser.add_argument("annotated_image", help="标注图片路径")
    parser.add_argument("--output", default="config/grid_extracted.json", help="输出配置文件")
    parser.add_argument("--visualize", help="保存可视化结果图片路径")

    args = parser.parse_args()

    try:
        extractor = GridCellExtractor(args.annotated_image)

        success = extractor.run_extraction(args.output, args.visualize)

        if success:
            print(f"\n网格提取完成！")
            print(f"配置文件: {args.output}")
        else:
            print(f"\n网格提取失败，请检查输入图片")

    except Exception as e:
        print(f"提取失败: {e}")


if __name__ == "__main__":
    main()