"""
基于网格模式的格栅口检测器
利用格栅的规律性排列和透视特性进行检测
"""

import cv2
import numpy as np
from pathlib import Path
import argparse
from typing import List, Tuple, Optional


class GridPatternDetector:
    """基于网格模式的格栅检测器"""

    def __init__(self):
        self.debug_counter = 0
        self.debug_dir = Path("logs/grid_pattern_debug")
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
        """步骤1: 图像预处理"""
        print("\n=== 步骤1: 图像预处理 ===")

        original = cv2.imread(image_path)
        h, w = original.shape[:2]
        print(f"原图尺寸: {w} x {h}")

        self.save_debug_image(original, "original", "原始图像")

        # 转灰度
        gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)

        # CLAHE增强对比度
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        self.save_debug_image(cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR),
                            "enhanced", "CLAHE对比度增强")

        return original, gray, enhanced

    def step2_detect_grid_lines(self, enhanced: np.ndarray, original: np.ndarray):
        """步骤2: 检测网格线"""
        print("\n=== 步骤2: 网格线检测 ===")

        # Canny边缘检测
        edges = cv2.Canny(enhanced, 50, 150)
        self.save_debug_image(cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR),
                            "edges", "Canny边缘检测")

        # Hough直线检测 - 更严格的参数
        lines = cv2.HoughLinesP(edges,
                               rho=1,           # 距离分辨率
                               theta=np.pi/180, # 角度分辨率
                               threshold=30,    # 最小投票数
                               minLineLength=20, # 最小线段长度
                               maxLineGap=10)   # 最大间隙

        print(f"检测到 {len(lines) if lines is not None else 0} 条直线")

        # 绘制所有检测到的直线
        line_image = original.copy()
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                cv2.line(line_image, (x1, y1), (x2, y2), (0, 255, 0), 1)

        self.save_debug_image(line_image, "all_lines", f"所有检测到的直线 ({len(lines) if lines is not None else 0}条)")

        return lines if lines is not None else []

    def step3_classify_lines(self, lines: List, original: np.ndarray):
        """步骤3: 分类水平线和垂直线"""
        print("\n=== 步骤3: 直线分类 ===")

        horizontal_lines = []
        vertical_lines = []

        for line in lines:
            x1, y1, x2, y2 = line[0]

            # 计算角度
            if x2 - x1 != 0:
                angle = np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi
            else:
                angle = 90  # 垂直线

            # 分类（允许一定角度偏差）
            if abs(angle) <= 15 or abs(angle) >= 165:  # 近似水平
                horizontal_lines.append(line[0])
            elif 75 <= abs(angle) <= 105:  # 近似垂直
                vertical_lines.append(line[0])

        print(f"水平线: {len(horizontal_lines)} 条")
        print(f"垂直线: {len(vertical_lines)} 条")

        # 绘制分类后的直线
        classified_image = original.copy()

        # 水平线用红色绘制
        for line in horizontal_lines:
            x1, y1, x2, y2 = line
            cv2.line(classified_image, (x1, y1), (x2, y2), (0, 0, 255), 2)

        # 垂直线用蓝色绘制
        for line in vertical_lines:
            x1, y1, x2, y2 = line
            cv2.line(classified_image, (x1, y1), (x2, y2), (255, 0, 0), 2)

        self.save_debug_image(classified_image, "classified_lines",
                            f"分类后直线 (红色:{len(horizontal_lines)}条水平, 蓝色:{len(vertical_lines)}条垂直)")

        return horizontal_lines, vertical_lines

    def step4_merge_similar_lines(self, lines: List, is_horizontal: bool, image_shape: Tuple):
        """步骤4: 合并相似的直线"""
        if not lines:
            return []

        h, w = image_shape[:2]
        merged_lines = []

        # 按位置排序
        if is_horizontal:
            # 水平线按y坐标排序
            lines.sort(key=lambda line: (line[1] + line[3]) // 2)
            threshold = h * 0.02  # 2%的高度作为合并阈值
        else:
            # 垂直线按x坐标排序
            lines.sort(key=lambda line: (line[0] + line[2]) // 2)
            threshold = w * 0.02  # 2%的宽度作为合并阈值

        # 合并相近的直线
        i = 0
        while i < len(lines):
            current_line = lines[i]

            if is_horizontal:
                current_pos = (current_line[1] + current_line[3]) // 2
            else:
                current_pos = (current_line[0] + current_line[2]) // 2

            # 找到所有与当前线相近的线
            similar_lines = [current_line]
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                if is_horizontal:
                    next_pos = (next_line[1] + next_line[3]) // 2
                else:
                    next_pos = (next_line[0] + next_line[2]) // 2

                if abs(next_pos - current_pos) <= threshold:
                    similar_lines.append(next_line)
                    j += 1
                else:
                    break

            # 合并相似的线段
            if is_horizontal:
                # 水平线：取y坐标平均值，x坐标取范围
                avg_y = int(np.mean([line[1] + line[3] for line in similar_lines]) / 2)
                min_x = min([min(line[0], line[2]) for line in similar_lines])
                max_x = max([max(line[0], line[2]) for line in similar_lines])
                merged_line = [min_x, avg_y, max_x, avg_y]
            else:
                # 垂直线：取x坐标平均值，y坐标取范围
                avg_x = int(np.mean([line[0] + line[2] for line in similar_lines]) / 2)
                min_y = min([min(line[1], line[3]) for line in similar_lines])
                max_y = max([max(line[1], line[3]) for line in similar_lines])
                merged_line = [avg_x, min_y, avg_x, max_y]

            merged_lines.append(merged_line)
            i = j

        return merged_lines

    def step5_generate_grid_intersections(self, horizontal_lines: List, vertical_lines: List,
                                        original: np.ndarray):
        """步骤5: 生成网格交点"""
        print("\n=== 步骤5: 网格交点生成 ===")

        h, w = original.shape[:2]

        # 合并相似直线
        merged_h_lines = self.step4_merge_similar_lines(horizontal_lines, True, (h, w))
        merged_v_lines = self.step4_merge_similar_lines(vertical_lines, False, (h, w))

        print(f"合并后 - 水平线: {len(merged_h_lines)} 条, 垂直线: {len(merged_v_lines)} 条")

        # 绘制合并后的直线
        merged_image = original.copy()
        for line in merged_h_lines:
            x1, y1, x2, y2 = line
            cv2.line(merged_image, (x1, y1), (x2, y2), (0, 0, 255), 3)
        for line in merged_v_lines:
            x1, y1, x2, y2 = line
            cv2.line(merged_image, (x1, y1), (x2, y2), (255, 0, 0), 3)

        self.save_debug_image(merged_image, "merged_lines",
                            f"合并后的网格线 (红色:{len(merged_h_lines)}, 蓝色:{len(merged_v_lines)})")

        # 计算所有交点
        intersections = []
        grid_cells = []

        for i in range(len(merged_h_lines)):
            h_line = merged_h_lines[i]
            h_y = h_line[1]  # 水平线的y坐标

            for j in range(len(merged_v_lines)):
                v_line = merged_v_lines[j]
                v_x = v_line[0]  # 垂直线的x坐标

                # 检查交点是否在有效范围内
                if (min(h_line[0], h_line[2]) <= v_x <= max(h_line[0], h_line[2]) and
                    min(v_line[1], v_line[3]) <= h_y <= max(v_line[1], v_line[3])):
                    intersections.append((v_x, h_y))

                    # 生成格栅单元（如果不是边界）
                    if i < len(merged_h_lines) - 1 and j < len(merged_v_lines) - 1:
                        next_h_line = merged_h_lines[i + 1]
                        next_v_line = merged_v_lines[j + 1]

                        x1, y1 = v_x, h_y
                        x2, y2 = next_v_line[0], next_h_line[1]

                        # 确保格栅单元有效
                        if x2 > x1 and y2 > y1:
                            grid_cells.append((x1, y1, x2 - x1, y2 - y1))

        print(f"生成 {len(intersections)} 个交点")
        print(f"生成 {len(grid_cells)} 个格栅单元")

        # 绘制交点
        intersection_image = original.copy()
        for x, y in intersections:
            cv2.circle(intersection_image, (int(x), int(y)), 3, (0, 255, 255), -1)

        self.save_debug_image(intersection_image, "intersections",
                            f"网格交点 ({len(intersections)}个)")

        return grid_cells, intersections

    def step6_generate_final_grid(self, grid_cells: List, original: np.ndarray):
        """步骤6: 生成最终格栅口"""
        print("\n=== 步骤6: 生成最终格栅口 ===")

        # 过滤太小的格栅单元
        min_area = 100  # 最小面积
        valid_cells = []

        for x, y, w, h in grid_cells:
            if w * h >= min_area and w > 5 and h > 5:
                valid_cells.append((x, y, w, h))

        print(f"过滤后有效格栅单元: {len(valid_cells)} 个")

        # 绘制最终结果
        final_image = original.copy()
        for i, (x, y, w, h) in enumerate(valid_cells):
            # 绘制矩形框
            cv2.rectangle(final_image, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # 绘制编号
            center_x = x + w // 2
            center_y = y + h // 2
            cv2.putText(final_image, f"{i+1}", (center_x - 10, center_y + 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            cv2.putText(final_image, f"{i+1}", (center_x - 10, center_y + 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        # 添加统计信息
        info_text = f"Grid Pattern Detection: {len(valid_cells)} cells"
        cv2.putText(final_image, info_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(final_image, info_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 1)

        self.save_debug_image(final_image, "final_grid", f"最终网格检测结果 ({len(valid_cells)}个)")

        return valid_cells

    def detect_grid_pattern(self, image_path: str):
        """完整的网格模式检测流程"""
        print(f"\n{'='*60}")
        print(f"开始网格模式检测: {Path(image_path).name}")
        print(f"{'='*60}")

        # 重置计数器
        self.debug_counter = 0

        # 步骤1: 预处理
        original, gray, enhanced = self.step1_preprocessing(image_path)

        # 步骤2: 检测直线
        lines = self.step2_detect_grid_lines(enhanced, original)

        if len(lines) == 0:
            print("未检测到足够的直线，无法继续")
            return []

        # 步骤3: 分类直线
        horizontal_lines, vertical_lines = self.step3_classify_lines(lines, original)

        if len(horizontal_lines) < 2 or len(vertical_lines) < 2:
            print(f"网格线不足：水平线{len(horizontal_lines)}条，垂直线{len(vertical_lines)}条")
            return []

        # 步骤5: 生成网格交点和单元
        grid_cells, intersections = self.step5_generate_grid_intersections(
            horizontal_lines, vertical_lines, original)

        # 步骤6: 生成最终格栅口
        final_grids = self.step6_generate_final_grid(grid_cells, original)

        print(f"\n{'='*60}")
        print(f"网格模式检测完成！共 {self.debug_counter} 个步骤")
        print(f"最终结果: 检测到 {len(final_grids)} 个格栅单元")
        print(f"调试图片保存在: {self.debug_dir}")
        print(f"{'='*60}")

        return final_grids


def main():
    parser = argparse.ArgumentParser(description="网格模式格栅检测工具")
    parser.add_argument("image_path", help="格栅图片路径")

    args = parser.parse_args()

    detector = GridPatternDetector()
    grids = detector.detect_grid_pattern(args.image_path)

    print(f"\n最终检测结果: {len(grids)} 个格栅单元")

    if grids:
        print("\n格栅单元坐标:")
        for i, (x, y, w, h) in enumerate(grids):
            print(f"  {i+1}: x={x}, y={y}, w={w}, h={h}")


if __name__ == "__main__":
    main()