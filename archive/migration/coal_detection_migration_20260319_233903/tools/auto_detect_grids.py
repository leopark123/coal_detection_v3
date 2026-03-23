"""
格栅口自动检测工具
基于真实图片自动识别格栅口位置
"""

import cv2
import numpy as np
import yaml
from pathlib import Path
from typing import List, Tuple, Optional
import argparse


class GridDetector:
    """格栅口自动检测器"""

    def __init__(self):
        self.debug = False

    def detect_grids(self, image_path: str, debug: bool = False) -> List[Tuple[int, int, int, int]]:
        """
        自动检测格栅口位置

        Args:
            image_path: 图片路径
            debug: 是否显示调试信息

        Returns:
            格栅口ROI列表 [(x, y, w, h), ...]
        """
        self.debug = debug

        # 读取图片
        image = cv2.imread(image_path)
        if image is None:
            print(f"无法读取图片: {image_path}")
            return []

        print(f"图片尺寸: {image.shape[1]} x {image.shape[0]}")

        # 预处理
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # 格栅检测流程
        grid_rois = self._detect_grid_pattern(gray, image)

        if not grid_rois:
            print("未检测到格栅口，尝试备用方法...")
            grid_rois = self._detect_grid_fallback(gray, image)

        print(f"检测到 {len(grid_rois)} 个格栅口")

        if self.debug and grid_rois:
            self._show_debug_result(image.copy(), grid_rois)

        return grid_rois

    def _detect_grid_pattern(self, gray: np.ndarray, original: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """主要的格栅检测方法"""
        h, w = gray.shape

        # 自适应二值化
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 5
        )

        # 形态学操作
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (w//20, 1))
        kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h//20))

        # 检测水平线
        horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_h)
        # 检测垂直线
        vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_v)

        # 合并线条
        grid_lines = cv2.bitwise_or(horizontal, vertical)

        if self.debug:
            cv2.imshow("Binary", binary)
            cv2.imshow("Grid Lines", grid_lines)
            cv2.waitKey(0)

        # 查找轮廓来定位格栅口
        contours, _ = cv2.findContours(grid_lines, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        # 反转图像（格栅孔为白色）
        grid_holes = cv2.bitwise_not(grid_lines)
        hole_contours, _ = cv2.findContours(grid_holes, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        rois = []
        min_area = (w * h) // 2000  # 最小格栅口面积
        max_area = (w * h) // 50    # 最大格栅口面积

        for contour in hole_contours:
            area = cv2.contourArea(contour)

            if min_area < area < max_area:
                x, y, w_roi, h_roi = cv2.boundingRect(contour)

                # 过滤形状不合理的区域
                aspect_ratio = w_roi / h_roi
                if 0.3 < aspect_ratio < 3.0:  # 允许一定的长宽比变化
                    rois.append((x, y, w_roi, h_roi))

        return rois

    def _detect_grid_fallback(self, gray: np.ndarray, original: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """备用的格栅检测方法"""
        h, w = gray.shape

        # 使用边缘检测
        edges = cv2.Canny(gray, 50, 150)

        # 使用霍夫线变换检测直线
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=50, minLineLength=30, maxLineGap=10)

        if lines is None:
            return []

        # 分离水平线和垂直线
        horizontal_lines = []
        vertical_lines = []

        for line in lines:
            x1, y1, x2, y2 = line[0]

            # 计算线段角度
            angle = np.arctan2(abs(y2 - y1), abs(x2 - x1)) * 180 / np.pi

            if angle < 30:  # 水平线
                horizontal_lines.append(((x1, y1), (x2, y2)))
            elif angle > 60:  # 垂直线
                vertical_lines.append(((x1, y1), (x2, y2)))

        if len(horizontal_lines) < 2 or len(vertical_lines) < 2:
            return self._generate_uniform_grid(w, h)

        # 基于检测到的线条创建网格
        return self._create_grid_from_lines(horizontal_lines, vertical_lines, w, h)

    def _generate_uniform_grid(self, width: int, height: int, rows: int = 6, cols: int = 4) -> List[Tuple[int, int, int, int]]:
        """生成均匀网格（当自动检测失败时使用）"""
        print(f"自动检测失败，生成 {rows}x{cols} 均匀网格")

        # 预留边距
        margin_x = width // 10
        margin_y = height // 10

        grid_width = (width - 2 * margin_x) // cols
        grid_height = (height - 2 * margin_y) // rows

        rois = []
        for row in range(rows):
            for col in range(cols):
                x = margin_x + col * grid_width
                y = margin_y + row * grid_height

                # 稍微缩小每个格栅口，避免包含边框
                padding = min(grid_width, grid_height) // 10
                rois.append((
                    x + padding,
                    y + padding,
                    grid_width - 2 * padding,
                    grid_height - 2 * padding
                ))

        return rois

    def _create_grid_from_lines(self, h_lines: list, v_lines: list, w: int, h: int) -> List[Tuple[int, int, int, int]]:
        """根据检测到的线条创建格栅"""
        # 提取水平线的Y坐标
        h_y_coords = []
        for line in h_lines:
            y_avg = (line[0][1] + line[1][1]) // 2
            h_y_coords.append(y_avg)

        # 提取垂直线的X坐标
        v_x_coords = []
        for line in v_lines:
            x_avg = (line[0][0] + line[1][0]) // 2
            v_x_coords.append(x_avg)

        # 排序并去重
        h_y_coords = sorted(list(set(h_y_coords)))
        v_x_coords = sorted(list(set(v_x_coords)))

        # 创建格栅ROI
        rois = []
        for i in range(len(h_y_coords) - 1):
            for j in range(len(v_x_coords) - 1):
                x = v_x_coords[j]
                y = h_y_coords[i]
                w_roi = v_x_coords[j + 1] - x
                h_roi = h_y_coords[i + 1] - y

                # 缩小ROI避免包含边框
                padding = min(w_roi, h_roi) // 8
                if w_roi > 2 * padding and h_roi > 2 * padding:
                    rois.append((
                        x + padding,
                        y + padding,
                        w_roi - 2 * padding,
                        h_roi - 2 * padding
                    ))

        return rois

    def _show_debug_result(self, image: np.ndarray, rois: List[Tuple[int, int, int, int]]):
        """显示调试结果"""
        for i, (x, y, w, h) in enumerate(rois):
            cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(image, f"{i+1}", (x + 5, y + 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

        cv2.imshow("Detected Grids", image)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    def save_grid_config(self, rois: List[Tuple[int, int, int, int]],
                        output_path: str = "config/grid_real.yaml"):
        """保存格栅配置到文件"""
        config_data = {
            'grid_rois': [
                {'id': i + 1, 'x': x, 'y': y, 'w': w, 'h': h}
                for i, (x, y, w, h) in enumerate(rois)
            ],
            'total_grids': len(rois),
            'detection_method': 'auto_detected'
        }

        Path(output_path).parent.mkdir(exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, default_flow_style=False,
                     allow_unicode=True, sort_keys=False)

        print(f"格栅配置已保存到: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="自动检测格栅口位置")
    parser.add_argument("image_path", help="格栅图片路径")
    parser.add_argument("--debug", action="store_true", help="显示调试信息")
    parser.add_argument("--output", default="config/grid_real.yaml", help="输出配置文件路径")

    args = parser.parse_args()

    detector = GridDetector()
    rois = detector.detect_grids(args.image_path, debug=args.debug)

    if rois:
        detector.save_grid_config(rois, args.output)
        print(f"\n成功检测到 {len(rois)} 个格栅口")
        print("配置文件已生成，可以在检测系统中使用")
    else:
        print("格栅检测失败")


if __name__ == "__main__":
    main()