"""
格栅口调试检测工具
每一步都生成图片供用户审核
"""

import cv2
import numpy as np
import yaml
from pathlib import Path
import argparse
from typing import List, Tuple


class DebugGridDetector:
    """调试版格栅检测器 - 每步生成图片"""

    def __init__(self):
        self.debug_counter = 0
        self.debug_dir = Path("logs/debug_detection")
        self.debug_dir.mkdir(exist_ok=True)

    def save_debug_image(self, image: np.ndarray, step_name: str, description: str = ""):
        """保存调试图片"""
        self.debug_counter += 1
        filename = f"step_{self.debug_counter:02d}_{step_name}.jpg"
        filepath = self.debug_dir / filename
        cv2.imwrite(str(filepath), image)
        print(f"[DEBUG {self.debug_counter}] {description}")
        print(f"    图片保存: {filepath}")
        return str(filepath)

    def step1_preprocessing(self, image_path: str):
        """步骤1: 预处理"""
        print("\n=== 步骤1: 图像预处理 ===")

        # 读取原图
        original = cv2.imread(image_path)
        h, w = original.shape[:2]
        print(f"原图尺寸: {w} x {h}")

        # 保存原图
        self.save_debug_image(original, "original", "原始图像")

        # 转灰度
        gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
        gray_3ch = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        self.save_debug_image(gray_3ch, "gray", "灰度图像")

        # 高斯模糊
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        blurred_3ch = cv2.cvtColor(blurred, cv2.COLOR_GRAY2BGR)
        self.save_debug_image(blurred_3ch, "blurred", "高斯模糊")

        return original, gray, blurred

    def step2_edge_detection(self, gray: np.ndarray):
        """步骤2: 边缘检测"""
        print("\n=== 步骤2: 边缘检测 ===")

        # Canny边缘检测 - 降低阈值检测更多边缘
        edges_low = cv2.Canny(gray, 30, 80)
        edges_med = cv2.Canny(gray, 50, 120)
        edges_high = cv2.Canny(gray, 80, 160)

        self.save_debug_image(cv2.cvtColor(edges_low, cv2.COLOR_GRAY2BGR),
                            "edges_low", "低阈值边缘检测(30,80)")
        self.save_debug_image(cv2.cvtColor(edges_med, cv2.COLOR_GRAY2BGR),
                            "edges_med", "中阈值边缘检测(50,120)")
        self.save_debug_image(cv2.cvtColor(edges_high, cv2.COLOR_GRAY2BGR),
                            "edges_high", "高阈值边缘检测(80,160)")

        return edges_low, edges_med, edges_high

    def step3_morphological(self, edges: np.ndarray, kernel_size: int = 3):
        """步骤3: 形态学操作"""
        print(f"\n=== 步骤3: 形态学操作 (核大小: {kernel_size}) ===")

        kernel = np.ones((kernel_size, kernel_size), np.uint8)

        # 闭操作 - 连接断裂的边缘
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
        self.save_debug_image(cv2.cvtColor(closed, cv2.COLOR_GRAY2BGR),
                            f"closed_k{kernel_size}", f"闭操作 核大小{kernel_size}")

        # 开操作 - 去除小噪声
        opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel)
        self.save_debug_image(cv2.cvtColor(opened, cv2.COLOR_GRAY2BGR),
                            f"opened_k{kernel_size}", f"开操作 核大小{kernel_size}")

        return closed, opened

    def step4_contour_detection(self, binary: np.ndarray, original: np.ndarray):
        """步骤4: 轮廓检测"""
        print("\n=== 步骤4: 轮廓检测 ===")

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        print(f"检测到 {len(contours)} 个轮廓")

        # 绘制所有轮廓
        all_contours = original.copy()
        cv2.drawContours(all_contours, contours, -1, (0, 255, 0), 1)
        self.save_debug_image(all_contours, "all_contours", f"所有轮廓 ({len(contours)}个)")

        return contours

    def step5_filter_by_area(self, contours: List, original: np.ndarray, min_area: int = 50, max_area: int = 2000):
        """步骤5: 按面积过滤轮廓"""
        print(f"\n=== 步骤5: 面积过滤 (范围: {min_area}-{max_area}) ===")

        filtered_contours = []
        areas = []

        for contour in contours:
            area = cv2.contourArea(contour)
            if min_area <= area <= max_area:
                filtered_contours.append(contour)
                areas.append(area)

        print(f"面积过滤后: {len(filtered_contours)} 个轮廓")
        if areas:
            print(f"面积范围: {min(areas):.1f} - {max(areas):.1f}")

        # 绘制过滤后的轮廓
        filtered_image = original.copy()
        cv2.drawContours(filtered_image, filtered_contours, -1, (0, 255, 0), 2)
        self.save_debug_image(filtered_image, f"filtered_area_{min_area}_{max_area}",
                            f"面积过滤 ({len(filtered_contours)}个)")

        return filtered_contours

    def step6_filter_by_shape(self, contours: List, original: np.ndarray):
        """步骤6: 按形状过滤轮廓"""
        print("\n=== 步骤6: 形状过滤 ===")

        good_contours = []

        for contour in contours:
            # 外接矩形
            x, y, w, h = cv2.boundingRect(contour)
            area = cv2.contourArea(contour)
            rect_area = w * h

            if rect_area == 0:
                continue

            # 形状特征
            aspect_ratio = w / h if h > 0 else 0
            rectangularity = area / rect_area if rect_area > 0 else 0

            # 放宽形状限制
            if (0.2 < aspect_ratio < 5.0 and  # 长宽比范围放宽
                rectangularity > 0.3):       # 矩形度放宽
                good_contours.append(contour)

        print(f"形状过滤后: {len(good_contours)} 个轮廓")

        # 绘制形状过滤后的轮廓
        shape_image = original.copy()
        cv2.drawContours(shape_image, good_contours, -1, (0, 255, 0), 2)
        self.save_debug_image(shape_image, "filtered_shape", f"形状过滤 ({len(good_contours)}个)")

        return good_contours

    def step7_convert_to_rois(self, contours: List, original: np.ndarray):
        """步骤7: 转换为ROI区域"""
        print("\n=== 步骤7: 生成最终ROI ===")

        rois = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            rois.append((x, y, w, h))

        # 绘制最终结果
        final_image = original.copy()
        for i, (x, y, w, h) in enumerate(rois):
            # 绘制矩形框
            cv2.rectangle(final_image, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # 绘制编号
            center_x = x + w // 2
            center_y = y + h // 2
            cv2.putText(final_image, f"{i+1}", (center_x - 10, center_y + 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            cv2.putText(final_image, f"{i+1}", (center_x - 10, center_y + 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        self.save_debug_image(final_image, "final_result", f"最终检测结果 ({len(rois)}个)")

        print(f"最终检测到 {len(rois)} 个格栅口")
        return rois

    def detect_with_debug(self, image_path: str,
                         edge_threshold: Tuple[int, int] = (50, 120),
                         morph_kernel: int = 3,
                         area_range: Tuple[int, int] = (50, 2000)):
        """完整的调试检测流程"""
        print(f"\n{'='*60}")
        print(f"开始调试检测: {Path(image_path).name}")
        print(f"参数: 边缘阈值{edge_threshold}, 形态核{morph_kernel}, 面积范围{area_range}")
        print(f"{'='*60}")

        # 重置计数器
        self.debug_counter = 0

        # 步骤1: 预处理
        original, gray, blurred = self.step1_preprocessing(image_path)

        # 步骤2: 边缘检测
        edges_low, edges_med, edges_high = self.step2_edge_detection(blurred)

        # 选择中等阈值的边缘
        selected_edges = edges_med

        # 步骤3: 形态学操作
        closed, opened = self.step3_morphological(selected_edges, morph_kernel)

        # 步骤4: 轮廓检测
        contours = self.step4_contour_detection(opened, original)

        # 步骤5: 面积过滤
        filtered_contours = self.step5_filter_by_area(contours, original,
                                                    area_range[0], area_range[1])

        # 步骤6: 形状过滤
        good_contours = self.step6_filter_by_shape(filtered_contours, original)

        # 步骤7: 生成ROI
        rois = self.step7_convert_to_rois(good_contours, original)

        print(f"\n{'='*60}")
        print(f"调试检测完成！共 {self.debug_counter} 个步骤")
        print(f"最终结果: 检测到 {len(rois)} 个格栅口")
        print(f"调试图片保存在: {self.debug_dir}")
        print(f"{'='*60}")

        return rois


def main():
    parser = argparse.ArgumentParser(description="格栅口调试检测工具")
    parser.add_argument("image_path", help="格栅图片路径")
    parser.add_argument("--edge-low", type=int, default=50, help="边缘检测低阈值")
    parser.add_argument("--edge-high", type=int, default=120, help="边缘检测高阈值")
    parser.add_argument("--morph-kernel", type=int, default=3, help="形态学核大小")
    parser.add_argument("--min-area", type=int, default=50, help="最小面积")
    parser.add_argument("--max-area", type=int, default=2000, help="最大面积")

    args = parser.parse_args()

    detector = DebugGridDetector()
    rois = detector.detect_with_debug(
        args.image_path,
        edge_threshold=(args.edge_low, args.edge_high),
        morph_kernel=args.morph_kernel,
        area_range=(args.min_area, args.max_area)
    )

    print(f"\n最终检测结果: {len(rois)} 个格栅口")


if __name__ == "__main__":
    main()