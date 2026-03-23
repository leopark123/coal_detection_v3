"""
智能格栅口检测工具 V2.0
基于几何规律和多阶段过滤的改进算法
"""

import cv2
import numpy as np
import yaml
from pathlib import Path
from typing import List, Tuple, Optional
import argparse
from collections import defaultdict


class SmartGridDetector:
    """智能格栅口检测器"""

    def __init__(self):
        self.debug = False

    def detect_grids(self, image_path: str, debug: bool = False) -> List[Tuple[int, int, int, int]]:
        """
        智能检测格栅口位置

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

        print(f"[INFO] 图片尺寸: {image.shape[1]} x {image.shape[0]}")

        # 执行智能检测流程
        grid_rois = self._smart_detect_pipeline(image)

        print(f"[SUCCESS] 检测到 {len(grid_rois)} 个格栅口")

        if self.debug and grid_rois:
            self._show_debug_result(image.copy(), grid_rois)

        return grid_rois

    def _smart_detect_pipeline(self, image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """智能检测流水线"""

        # Step 1: 预处理优化
        processed = self._enhanced_preprocessing(image)

        # Step 2: 几何结构分析
        grid_lines = self._detect_grid_structure(processed, image)

        # Step 3: 基于几何规律生成候选区域
        candidates = self._generate_grid_candidates(grid_lines, image.shape)

        # Step 4: 轮廓验证
        verified_rois = self._verify_with_contours(processed, candidates, image.shape)

        # Step 5: 规律性检查和优化
        final_rois = self._regularize_grid_layout(verified_rois)

        return final_rois

    def _enhanced_preprocessing(self, image: np.ndarray) -> np.ndarray:
        """增强预处理"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # 高斯模糊去噪
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)

        # CLAHE增强对比度
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(blurred)

        # 自适应二值化
        binary = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 11, 2
        )

        if self.debug:
            cv2.imshow("Enhanced Preprocessing", binary)
            cv2.waitKey(0)

        return binary

    def _detect_grid_structure(self, binary: np.ndarray, original: np.ndarray) -> dict:
        """检测格栅的几何结构"""
        h, w = binary.shape

        # 检测边缘
        edges = cv2.Canny(binary, 50, 150, apertureSize=3)

        # 霍夫直线检测
        lines = cv2.HoughLinesP(
            edges, 1, np.pi/180,
            threshold=min(w, h)//6,  # 动态阈值
            minLineLength=min(w, h)//8,
            maxLineGap=min(w, h)//20
        )

        horizontal_lines = []
        vertical_lines = []

        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]

                # 计算线段角度
                length = np.sqrt((x2-x1)**2 + (y2-y1)**2)
                if length < 20:  # 过滤太短的线段
                    continue

                angle = np.arctan2(abs(y2 - y1), abs(x2 - x1)) * 180 / np.pi

                if angle < 15:  # 水平线
                    horizontal_lines.append((x1, y1, x2, y2, (y1 + y2) // 2))
                elif angle > 75:  # 垂直线
                    vertical_lines.append((x1, y1, x2, y2, (x1 + x2) // 2))

        # 合并相近的线条
        h_groups = self._group_lines(horizontal_lines, axis=4)  # 按y坐标分组
        v_groups = self._group_lines(vertical_lines, axis=4)   # 按x坐标分组

        if self.debug:
            debug_img = original.copy()
            for y in h_groups:
                cv2.line(debug_img, (0, y), (w, y), (0, 255, 0), 2)
            for x in v_groups:
                cv2.line(debug_img, (x, 0), (x, h), (255, 0, 0), 2)
            cv2.imshow("Detected Grid Lines", debug_img)
            cv2.waitKey(0)

        print(f"[DETECT] 检测到 {len(h_groups)} 条水平线, {len(v_groups)} 条垂直线")

        return {
            'horizontal': sorted(h_groups),
            'vertical': sorted(v_groups),
            'spacing_h': self._calculate_spacing(h_groups),
            'spacing_v': self._calculate_spacing(v_groups)
        }

    def _group_lines(self, lines: List, axis: int, tolerance: int = 10) -> List[int]:
        """合并相近的线条"""
        if not lines:
            return []

        # 按指定轴坐标排序
        sorted_lines = sorted(lines, key=lambda x: x[axis])

        groups = []
        current_group = [sorted_lines[0][axis]]

        for line in sorted_lines[1:]:
            coord = line[axis]
            if abs(coord - current_group[-1]) <= tolerance:
                current_group.append(coord)
            else:
                # 结束当前组，开始新组
                groups.append(int(np.mean(current_group)))
                current_group = [coord]

        # 添加最后一组
        if current_group:
            groups.append(int(np.mean(current_group)))

        return groups

    def _calculate_spacing(self, coords: List[int]) -> int:
        """计算线条间距"""
        if len(coords) < 2:
            return 0

        spacings = []
        for i in range(1, len(coords)):
            spacings.append(coords[i] - coords[i-1])

        # 返回最常见的间距
        if spacings:
            return int(np.median(spacings))
        return 0

    def _generate_grid_candidates(self, grid_lines: dict, image_shape: Tuple) -> List[Tuple[int, int, int, int]]:
        """基于几何规律生成格栅口候选区域"""
        h, w = image_shape[:2]
        h_lines = grid_lines['horizontal']
        v_lines = grid_lines['vertical']

        candidates = []

        # 如果线条太少，使用间距补充
        spacing_h = grid_lines['spacing_h']
        spacing_v = grid_lines['spacing_v']

        # 补充可能缺失的线条
        if len(h_lines) >= 2 and spacing_h > 0:
            h_lines = self._fill_missing_lines(h_lines, spacing_h, 0, h)

        if len(v_lines) >= 2 and spacing_v > 0:
            v_lines = self._fill_missing_lines(v_lines, spacing_v, 0, w)

        print(f"[GEOMETRY] 补充后: {len(h_lines)} 条水平线, {len(v_lines)} 条垂直线")

        # 生成格栅口区域
        for i in range(len(h_lines) - 1):
            for j in range(len(v_lines) - 1):
                x1, x2 = v_lines[j], v_lines[j + 1]
                y1, y2 = h_lines[i], h_lines[i + 1]

                # 添加边距，避免包含网格线
                margin_x = max(2, int((x2 - x1) * 0.1))
                margin_y = max(2, int((y2 - y1) * 0.1))

                x = x1 + margin_x
                y = y1 + margin_y
                roi_w = x2 - x1 - 2 * margin_x
                roi_h = y2 - y1 - 2 * margin_y

                # 基本尺寸检查
                if roi_w > 10 and roi_h > 10 and roi_w < w//3 and roi_h < h//3:
                    candidates.append((x, y, roi_w, roi_h))

        print(f"[TARGET] 生成 {len(candidates)} 个候选区域")
        return candidates

    def _fill_missing_lines(self, lines: List[int], spacing: int, min_coord: int, max_coord: int) -> List[int]:
        """填充可能缺失的线条"""
        filled_lines = lines.copy()

        # 向前填充
        while filled_lines[0] - spacing > min_coord + spacing//2:
            filled_lines.insert(0, filled_lines[0] - spacing)

        # 向后填充
        while filled_lines[-1] + spacing < max_coord - spacing//2:
            filled_lines.append(filled_lines[-1] + spacing)

        # 填充中间的缺失
        i = 0
        while i < len(filled_lines) - 1:
            gap = filled_lines[i + 1] - filled_lines[i]
            if gap > spacing * 1.5:  # 发现较大间隙
                insert_pos = filled_lines[i] + spacing
                filled_lines.insert(i + 1, insert_pos)
            i += 1

        return filled_lines

    def _verify_with_contours(self, binary: np.ndarray, candidates: List, image_shape: Tuple) -> List[Tuple[int, int, int, int]]:
        """通过轮廓验证候选区域"""
        verified = []

        # 找到所有轮廓
        contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        for x, y, w, h in candidates:
            roi_area = w * h

            # 在ROI区域内查找轮廓
            roi_binary = binary[y:y+h, x:x+w]
            roi_contours, _ = cv2.findContours(roi_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not roi_contours:
                continue

            # 找到最大轮廓
            max_contour = max(roi_contours, key=cv2.contourArea)
            contour_area = cv2.contourArea(max_contour)

            # 轮廓面积应该占ROI的合理比例
            area_ratio = contour_area / roi_area

            if 0.2 < area_ratio < 0.8:  # 格栅口应该是空洞，不是实心
                # 检查形状特征
                if self._is_valid_grid_shape(max_contour, w, h):
                    verified.append((x, y, w, h))

        print(f"[OK] 轮廓验证通过 {len(verified)} 个区域")
        return verified

    def _is_valid_grid_shape(self, contour, roi_w: int, roi_h: int) -> bool:
        """验证是否为有效的格栅口形状"""
        # 计算矩形度
        contour_area = cv2.contourArea(contour)
        if contour_area < 100:  # 太小的区域
            return False

        # 外接矩形
        x, y, w, h = cv2.boundingRect(contour)
        rect_area = w * h

        if rect_area == 0:
            return False

        rectangularity = contour_area / rect_area

        # 长宽比检查
        aspect_ratio = w / h if h > 0 else 0

        # 格栅口应该比较规整
        return (rectangularity > 0.6 and 0.3 < aspect_ratio < 3.0)

    def _regularize_grid_layout(self, rois: List[Tuple[int, int, int, int]]) -> List[Tuple[int, int, int, int]]:
        """规整化格栅布局"""
        if len(rois) < 4:  # 太少的ROI无法规整化
            return rois

        # 按位置排序和分组
        rois_by_row = defaultdict(list)
        rois_by_col = defaultdict(list)

        # 计算平均格栅尺寸
        avg_w = int(np.mean([w for _, _, w, _ in rois]))
        avg_h = int(np.mean([h for _, _, _, h in rois]))

        # 按行分组（相近的y坐标）
        tolerance_y = avg_h // 2
        for roi in rois:
            x, y, w, h = roi

            # 找到最近的行
            best_row_y = None
            min_dist = float('inf')

            for row_y in rois_by_row.keys():
                dist = abs(y - row_y)
                if dist < min_dist:
                    min_dist = dist
                    best_row_y = row_y

            if best_row_y is None or min_dist > tolerance_y:
                best_row_y = y

            rois_by_row[best_row_y].append(roi)

        # 规整化每行的格栅口
        regularized = []
        for row_y in sorted(rois_by_row.keys()):
            row_rois = sorted(rois_by_row[row_y], key=lambda x: x[0])  # 按x排序

            # 统一这一行的y坐标和高度
            unified_y = int(np.mean([y for _, y, _, _ in row_rois]))
            unified_h = avg_h

            for x, _, w, _ in row_rois:
                regularized.append((x, unified_y, avg_w, unified_h))

        print(f"[REGULARIZE] 规整化后 {len(regularized)} 个格栅口")
        return regularized

    def _show_debug_result(self, image: np.ndarray, rois: List[Tuple[int, int, int, int]]):
        """显示调试结果"""
        for i, (x, y, w, h) in enumerate(rois):
            # 绘制矩形框
            cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # 绘制编号
            center_x = x + w // 2
            center_y = y + h // 2
            cv2.putText(image, f"{i+1}", (center_x - 10, center_y + 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            cv2.putText(image, f"{i+1}", (center_x - 10, center_y + 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        cv2.imshow("Smart Grid Detection Result", image)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    def save_grid_config(self, rois: List[Tuple[int, int, int, int]],
                        source_image: str,
                        output_path: str = "config/grid_smart.yaml"):
        """保存智能检测的格栅配置"""
        config_data = {
            'source_image': source_image,
            'detection_method': 'smart_algorithm_v2',
            'grid_rois': [
                {'id': i + 1, 'x': x, 'y': y, 'w': w, 'h': h}
                for i, (x, y, w, h) in enumerate(rois)
            ],
            'total_grids': len(rois)
        }

        Path(output_path).parent.mkdir(exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, default_flow_style=False,
                     allow_unicode=True, sort_keys=False)

        print(f"[SAVE] 智能检测配置已保存到: {output_path}")
        return output_path

    def create_annotated_image(self, image_path: str, rois: List[Tuple[int, int, int, int]],
                              output_path: str = "logs/smart_detection_result.jpg"):
        """创建带标注的结果图片"""
        image = cv2.imread(image_path)
        if image is None:
            return None

        # 绘制格栅口标注
        for i, (x, y, w, h) in enumerate(rois):
            # 绘制矩形框
            cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # 绘制编号
            center_x = x + w // 2
            center_y = y + h // 2
            cv2.putText(image, f"{i+1}", (center_x - 10, center_y + 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(image, f"{i+1}", (center_x - 10, center_y + 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)

        # 添加统计信息
        info_text = f"Smart Detection: {len(rois)} grids found"
        cv2.putText(image, info_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(image, info_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 1)

        # 保存结果图片
        Path(output_path).parent.mkdir(exist_ok=True)
        cv2.imwrite(output_path, image)
        print(f"[IMAGE] 标注结果图片已保存到: {output_path}")
        return output_path


def main():
    parser = argparse.ArgumentParser(description="智能格栅口检测工具 V2.0")
    parser.add_argument("image_path", help="格栅图片路径")
    parser.add_argument("--debug", action="store_true", help="显示调试信息")
    parser.add_argument("--output", default="config/grid_smart.yaml", help="输出配置文件路径")

    args = parser.parse_args()

    try:
        detector = SmartGridDetector()
        print("[START] 启动智能格栅检测...")

        rois = detector.detect_grids(args.image_path, debug=args.debug)

        if rois:
            # 保存配置
            config_path = detector.save_grid_config(rois, args.image_path, args.output)

            # 创建标注图片
            result_image = detector.create_annotated_image(args.image_path, rois)

            print(f"\n[OK] 智能检测完成！")
            print(f"   检测到 {len(rois)} 个格栅口")
            print(f"   配置文件: {config_path}")
            print(f"   结果图片: {result_image}")
        else:
            print("\n[ERROR] 未检测到格栅口")

    except Exception as e:
        print(f"[ERROR] 错误: {e}")


if __name__ == "__main__":
    main()