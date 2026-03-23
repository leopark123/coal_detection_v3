"""
专门检测格栅口开口的检测器
基于边缘检测图，只检测真正的格栅口开口
"""

import cv2
import numpy as np
from pathlib import Path
import argparse
from typing import List, Tuple


class GridOpeningDetector:
    """专门检测格栅口开口的检测器"""

    def __init__(self):
        self.debug_counter = 0
        self.debug_dir = Path("logs/opening_debug")
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

    def step1_load_edge_image(self, edges_path: str, original_path: str):
        """步骤1: 加载边缘检测图"""
        print("\n=== 步骤1: 加载边缘检测图 ===")

        # 读取边缘图和原图
        edges = cv2.imread(edges_path, cv2.IMREAD_GRAYSCALE)
        original = cv2.imread(original_path)

        print(f"边缘图尺寸: {edges.shape[1]} x {edges.shape[0]}")

        self.save_debug_image(cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR),
                            "edges_input", "输入的边缘检测图")

        return edges, original

    def step2_preprocess_edges(self, edges: np.ndarray):
        """步骤2: 预处理边缘图"""
        print("\n=== 步骤2: 边缘图预处理 ===")

        # 形态学闭操作，连接断裂的边缘
        kernel = np.ones((3, 3), np.uint8)
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

        self.save_debug_image(cv2.cvtColor(closed, cv2.COLOR_GRAY2BGR),
                            "edges_closed", "闭操作后的边缘")

        # 反转图像 - 让格栅口变成白色区域
        inverted = cv2.bitwise_not(closed)

        self.save_debug_image(cv2.cvtColor(inverted, cv2.COLOR_GRAY2BGR),
                            "edges_inverted", "反转后的边缘（格栅口变白）")

        # 填充小孔洞
        kernel_small = np.ones((2, 2), np.uint8)
        filled = cv2.morphologyEx(inverted, cv2.MORPH_OPEN, kernel_small)

        self.save_debug_image(cv2.cvtColor(filled, cv2.COLOR_GRAY2BGR),
                            "edges_filled", "填充小孔洞后")

        return filled

    def step3_find_contours(self, processed_edges: np.ndarray, original: np.ndarray):
        """步骤3: 寻找轮廓"""
        print("\n=== 步骤3: 轮廓检测 ===")

        # 寻找轮廓 - 使用RETR_LIST检测所有轮廓，包括内部轮廓
        contours, _ = cv2.findContours(processed_edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        print(f"检测到 {len(contours)} 个轮廓")

        # 绘制所有轮廓
        all_contours_img = original.copy()
        cv2.drawContours(all_contours_img, contours, -1, (0, 255, 0), 1)

        self.save_debug_image(all_contours_img, "all_contours", f"所有轮廓 ({len(contours)}个)")

        return contours

    def step4_filter_rectangular_contours(self, contours: List, original: np.ndarray):
        """步骤4: 过滤矩形轮廓"""
        print("\n=== 步骤4: 矩形轮廓过滤 ===")

        rectangular_contours = []

        for contour in contours:
            # 计算轮廓面积
            area = cv2.contourArea(contour)
            if area < 50:  # 降低面积要求
                continue

            # 计算外接矩形
            x, y, w, h = cv2.boundingRect(contour)

            # 基本尺寸检查
            if w < 5 or h < 5:  # 太小的忽略
                continue

            # 检查长宽比（放宽要求）
            aspect_ratio = w / h if h > 0 else 0
            if 0.2 <= aspect_ratio <= 5.0:  # 放宽长宽比范围

                # 检查轮廓面积与外接矩形面积的比例
                rect_area = w * h
                fill_ratio = area / rect_area if rect_area > 0 else 0

                # 放宽填充度要求
                if fill_ratio > 0.3:  # 降低填充度要求
                    # 检查轮廓是否相对规整（不要太复杂）
                    perimeter = cv2.arcLength(contour, True)
                    circularity = 4 * np.pi * area / (perimeter * perimeter) if perimeter > 0 else 0

                    # 允许一定的不规则性
                    if circularity > 0.1:  # 不要太不规则
                        rectangular_contours.append(contour)

        print(f"矩形轮廓过滤后: {len(rectangular_contours)} 个")

        # 绘制矩形轮廓
        rect_contours_img = original.copy()
        cv2.drawContours(rect_contours_img, rectangular_contours, -1, (0, 255, 0), 2)

        self.save_debug_image(rect_contours_img, "rectangular_contours",
                            f"矩形轮廓 ({len(rectangular_contours)}个)")

        return rectangular_contours

    def step5_filter_by_size(self, contours: List, original: np.ndarray):
        """步骤5: 智能大小过滤"""
        print("\n=== 步骤5: 智能大小过滤 ===")

        if not contours:
            print("没有轮廓可供分析")
            return []

        # 计算所有轮廓的尺寸统计
        candidate_data = []
        for i, contour in enumerate(contours):
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            aspect_ratio = w / h if h > 0 else 0
            candidate_data.append({
                'index': i,
                'contour': contour,
                'x': x, 'y': y, 'w': w, 'h': h,
                'area': area,
                'aspect_ratio': aspect_ratio
            })

        widths = [d['w'] for d in candidate_data]
        heights = [d['h'] for d in candidate_data]
        areas = [d['area'] for d in candidate_data]

        print(f"候选轮廓统计:")
        print(f"  总数: {len(candidate_data)}")
        print(f"  宽度范围: {min(widths)} - {max(widths)}, 平均: {np.mean(widths):.1f}")
        print(f"  高度范围: {min(heights)} - {max(heights)}, 平均: {np.mean(heights):.1f}")
        print(f"  面积范围: {min(areas)} - {max(areas)}, 平均: {np.mean(areas):.1f}")

        # 使用四分位数方法找到合理的大小范围
        areas_sorted = sorted(areas)
        q1 = np.percentile(areas, 25)  # 第一四分位数
        q3 = np.percentile(areas, 75)  # 第三四分位数
        iqr = q3 - q1
        median_area = np.median(areas)

        print(f"  面积四分位数: Q1={q1:.1f}, Median={median_area:.1f}, Q3={q3:.1f}, IQR={iqr:.1f}")

        # 保守的面积范围：使用IQR方法去除异常值
        min_area = max(50, q1 - 0.5 * iqr)  # 下界
        max_area = q3 + 0.5 * iqr  # 上界

        # 如果范围太大，使用更严格的标准
        if max_area / min_area > 10:  # 比例过大说明有异常值
            # 使用更接近中位数的范围
            min_area = max(50, median_area * 0.3)
            max_area = median_area * 3.0

        print(f"  过滤面积范围: {min_area:.1f} - {max_area:.1f}")

        # 同样处理宽度和高度
        median_w = np.median(widths)
        median_h = np.median(heights)

        # 宽度和高度的合理范围
        min_w = max(5, median_w * 0.4)
        max_w = median_w * 2.5
        min_h = max(5, median_h * 0.4)
        max_h = median_h * 2.5

        print(f"  过滤宽度范围: {min_w:.1f} - {max_w:.1f}")
        print(f"  过滤高度范围: {min_h:.1f} - {max_h:.1f}")

        # 应用过滤条件
        filtered_contours = []
        filtered_data = []

        for data in candidate_data:
            area = data['area']
            w = data['w']
            h = data['h']
            aspect_ratio = data['aspect_ratio']

            # 面积过滤
            if not (min_area <= area <= max_area):
                continue

            # 尺寸过滤
            if not (min_w <= w <= max_w and min_h <= h <= max_h):
                continue

            # 长宽比过滤（格栅口应该相对规整）
            if not (0.3 <= aspect_ratio <= 3.0):
                continue

            # 形状规整性检查
            contour_area = cv2.contourArea(data['contour'])
            rect_area = w * h
            fill_ratio = contour_area / rect_area if rect_area > 0 else 0

            # 格栅口应该相对饱满
            if fill_ratio < 0.4:
                continue

            filtered_contours.append(data['contour'])
            filtered_data.append(data)

        print(f"智能过滤后: {len(filtered_contours)} 个格栅口")

        if filtered_data:
            final_widths = [d['w'] for d in filtered_data]
            final_heights = [d['h'] for d in filtered_data]
            final_areas = [d['area'] for d in filtered_data]

            print(f"最终结果统计:")
            print(f"  宽度: {min(final_widths)} - {max(final_widths)}, 平均: {np.mean(final_widths):.1f}")
            print(f"  高度: {min(final_heights)} - {max(final_heights)}, 平均: {np.mean(final_heights):.1f}")
            print(f"  面积: {min(final_areas)} - {max(final_areas)}, 平均: {np.mean(final_areas):.1f}")

        # 绘制最终结果
        final_img = original.copy()
        for i, contour in enumerate(filtered_contours):
            x, y, w, h = cv2.boundingRect(contour)

            # 绘制矩形框
            cv2.rectangle(final_img, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # 绘制编号
            center_x = x + w // 2
            center_y = y + h // 2
            cv2.putText(final_img, f"{i+1}", (center_x - 10, center_y + 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            cv2.putText(final_img, f"{i+1}", (center_x - 10, center_y + 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        # 添加统计信息
        info_text = f"Grid Openings: {len(filtered_contours)} found"
        cv2.putText(final_img, info_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(final_img, info_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 1)

        self.save_debug_image(final_img, "final_openings",
                            f"最终格栅口检测结果 ({len(filtered_contours)}个)")

        return filtered_contours

    def detect_grid_openings(self, original_path: str, edges_path: str = None):
        """完整的格栅口开口检测流程"""
        print(f"\n{'='*60}")
        print(f"开始格栅口开口检测: {Path(original_path).name}")
        print(f"{'='*60}")

        # 重置计数器
        self.debug_counter = 0

        # 如果没有提供边缘图路径，则生成边缘图
        if edges_path is None:
            original = cv2.imread(original_path)
            gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)

            # CLAHE增强
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)

            # Canny边缘检测
            edges = cv2.Canny(enhanced, 50, 150)

            # 保存生成的边缘图
            edges_path = self.debug_dir / "generated_edges.jpg"
            cv2.imwrite(str(edges_path), edges)
        else:
            original = cv2.imread(original_path)

        # 步骤1: 加载边缘图
        edges, original = self.step1_load_edge_image(edges_path, original_path)

        # 步骤2: 预处理边缘图
        processed_edges = self.step2_preprocess_edges(edges)

        # 步骤3: 寻找轮廓
        contours = self.step3_find_contours(processed_edges, original)

        if len(contours) == 0:
            print("未找到任何轮廓")
            return []

        # 步骤4: 过滤矩形轮廓
        rect_contours = self.step4_filter_rectangular_contours(contours, original)

        if len(rect_contours) == 0:
            print("未找到矩形轮廓")
            return []

        # 步骤5: 按大小过滤
        final_openings = self.step5_filter_by_size(rect_contours, original)

        # 转换为ROI格式
        rois = []
        for contour in final_openings:
            x, y, w, h = cv2.boundingRect(contour)
            rois.append((x, y, w, h))

        print(f"\n{'='*60}")
        print(f"格栅口检测完成！共 {self.debug_counter} 个步骤")
        print(f"最终结果: 检测到 {len(rois)} 个格栅口开口")
        print(f"调试图片保存在: {self.debug_dir}")
        print(f"{'='*60}")

        return rois


def main():
    parser = argparse.ArgumentParser(description="格栅口开口检测工具")
    parser.add_argument("image_path", help="原始格栅图片路径")
    parser.add_argument("--edges-path", help="边缘检测图片路径")

    args = parser.parse_args()

    detector = GridOpeningDetector()
    openings = detector.detect_grid_openings(args.image_path, args.edges_path)

    print(f"\n最终检测结果: {len(openings)} 个格栅口开口")

    if openings:
        print("\n格栅口坐标:")
        for i, (x, y, w, h) in enumerate(openings):
            print(f"  {i+1}: x={x}, y={y}, w={w}, h={h}")


if __name__ == "__main__":
    main()