"""
透视矫正+虚拟网格切片检测器
解决透视畸变、低对比度、纹理干扰问题的工业级方案
"""

import cv2
import numpy as np
import yaml
from pathlib import Path
import argparse
from typing import List, Tuple, Dict, Optional


class PerspectiveGridDetector:
    """透视矫正+虚拟网格切片检测器"""

    def __init__(self, config_path: str = None):
        self.debug_counter = 0
        self.debug_dir = Path("logs/perspective_debug")
        self.debug_dir.mkdir(exist_ok=True)

        # 默认配置
        self.config = {
            'calibration_points': None,  # 四个角点 [左上, 右上, 右下, 左下]
            'grid_shape': [8, 8],        # [行数, 列数]
            'target_size': [400, 400],   # 矫正后的图像尺寸
            'structure_threshold': 5.0,  # 结构评分阈值，低于此值认为有积煤覆盖
            'roi_padding': 8             # ROI内边距，避免边缘干扰
        }

        if config_path and Path(config_path).exists():
            self.load_config(config_path)

    def save_debug_image(self, image: np.ndarray, step_name: str, description: str = ""):
        """保存调试图片"""
        self.debug_counter += 1
        filename = f"step_{self.debug_counter:02d}_{step_name}.jpg"
        filepath = self.debug_dir / filename
        cv2.imwrite(str(filepath), image)
        print(f"[DEBUG {self.debug_counter}] {description}")
        print(f"    图片保存: {filepath}")
        return str(filepath)

    def load_config(self, config_path: str):
        """加载配置文件"""
        with open(config_path, 'r', encoding='utf-8') as f:
            loaded_config = yaml.safe_load(f)
            self.config.update(loaded_config)
        print(f"[CONFIG] 配置已加载: {config_path}")

    def save_config(self, config_path: str):
        """保存配置文件"""
        Path(config_path).parent.mkdir(exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
        print(f"[CONFIG] 配置已保存: {config_path}")

    def set_calibration_points(self, points: List[Tuple[int, int]], grid_shape: Tuple[int, int]):
        """设置标定点和网格形状"""
        self.config['calibration_points'] = points
        self.config['grid_shape'] = list(grid_shape)
        print(f"[CALIBRATION] 标定点: {points}")
        print(f"[CALIBRATION] 网格形状: {grid_shape[0]}行 x {grid_shape[1]}列")

    def step1_preprocess_image(self, image_path: str):
        """步骤1: 图像预处理"""
        print("\n=== 步骤1: 图像预处理 ===")

        original = cv2.imread(image_path)
        if original is None:
            raise ValueError(f"无法加载图片: {image_path}")

        print(f"原图尺寸: {original.shape[1]} x {original.shape[0]}")
        self.save_debug_image(original, "original", "原始图像")

        # CLAHE增强对比度
        lab = cv2.cvtColor(original, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        enhanced = cv2.merge((cl, a, b))
        enhanced_bgr = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

        self.save_debug_image(enhanced_bgr, "enhanced", "CLAHE对比度增强")

        return original, enhanced_bgr

    def step2_perspective_transform(self, enhanced_image: np.ndarray):
        """步骤2: 透视变换（拉直梯形）"""
        print("\n=== 步骤2: 透视变换 ===")

        if self.config['calibration_points'] is None:
            raise ValueError("未设置标定点，请先调用set_calibration_points()或使用标定工具")

        # 源点（梯形四个角点）
        src_pts = np.float32(self.config['calibration_points'])
        print(f"源点坐标: {src_pts}")

        # 目标点（正方形）
        W, H = self.config['target_size']
        dst_pts = np.float32([[0, 0], [W, 0], [W, H], [0, H]])

        # 计算透视变换矩阵
        M = cv2.getPerspectiveTransform(src_pts, dst_pts)

        # 应用透视变换
        warped = cv2.warpPerspective(enhanced_image, M, (W, H))
        warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

        print(f"透视变换完成，输出尺寸: {W} x {H}")
        self.save_debug_image(warped, "warped", f"透视变换后({W}x{H})")

        # 在原图上绘制标定区域
        original_with_roi = enhanced_image.copy()
        cv2.polylines(original_with_roi, [src_pts.astype(int)], True, (0, 255, 0), 3)
        for i, pt in enumerate(src_pts):
            cv2.circle(original_with_roi, tuple(pt.astype(int)), 8, (0, 0, 255), -1)
            cv2.putText(original_with_roi, f"{i+1}",
                       (int(pt[0])-10, int(pt[1])-10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        self.save_debug_image(original_with_roi, "calibration_roi", "标定区域标注")

        return warped, warped_gray, M

    def step3_virtual_grid_slicing(self, warped_color: np.ndarray, warped_gray: np.ndarray):
        """步骤3: 虚拟网格切片检测"""
        print("\n=== 步骤3: 虚拟网格切片检测 ===")

        rows, cols = self.config['grid_shape']
        H, W = warped_gray.shape
        padding = self.config['roi_padding']
        threshold = self.config['structure_threshold']

        print(f"网格配置: {rows}行 x {cols}列")
        print(f"单元格尺寸: {W//cols} x {H//rows}")
        print(f"ROI内边距: {padding}px")
        print(f"结构评分阈值: {threshold}")

        # 计算单元格尺寸
        cell_w = W // cols
        cell_h = H // rows

        # 结果统计
        results = []
        blocked_count = 0
        brightness_stats = []

        # 调试图像
        debug_view = warped_color.copy()

        for r in range(rows):
            for c in range(cols):
                # 计算当前格子的坐标
                x1 = c * cell_w
                y1 = r * cell_h
                x2 = x1 + cell_w
                y2 = y1 + cell_h

                # 提取ROI（向内缩进避免边缘干扰）
                roi_x1 = x1 + padding
                roi_y1 = y1 + padding
                roi_x2 = max(roi_x1 + 1, x2 - padding)
                roi_y2 = max(roi_y1 + 1, y2 - padding)

                roi = warped_gray[roi_y1:roi_y2, roi_x1:roi_x2]

                if roi.size == 0:
                    continue

                # 核心检测逻辑：检测格栅口结构的可见性
                mean_brightness = cv2.mean(roi)[0]
                std_brightness = np.std(roi)

                # 计算纹理特征 - 格栅口有立体结构，纹理丰富
                # 如果被积煤覆盖，表面会很平坦，纹理单一

                # 1. 灰度方差（纹理丰富度）
                texture_variance = np.var(roi)

                # 2. 边缘密度（结构复杂度）
                roi_edges = cv2.Canny(roi, 50, 150)
                edge_density = np.sum(roi_edges > 0) / roi_edges.size

                # 3. 局部二值模式（纹理模式）
                # 简化版LBP：计算8个方向的梯度变化
                sobelx = cv2.Sobel(roi, cv2.CV_64F, 1, 0, ksize=3)
                sobely = cv2.Sobel(roi, cv2.CV_64F, 0, 1, ksize=3)
                gradient_magnitude = np.sqrt(sobelx**2 + sobely**2)
                avg_gradient = np.mean(gradient_magnitude)

                brightness_stats.append(mean_brightness)

                # 判断格栅口状态的新逻辑：
                # 如果能检测到丰富的纹理和结构 → 格栅口可见 → 无积煤
                # 如果纹理平坦、结构模糊 → 格栅口被覆盖 → 有积煤

                # 综合评分：纹理方差 + 边缘密度 + 梯度强度
                structure_score = (texture_variance / 100) + (edge_density * 100) + (avg_gradient / 10)

                # 阈值判断：低结构分数表示被覆盖（积煤），高分数表示结构可见（无积煤）
                coal_detected = structure_score < threshold  # 注意这里逻辑反转了

                if coal_detected:
                    blocked_count += 1
                    color = (0, 0, 255)  # 红色：检测到积煤
                    status = "COAL_DETECTED"
                else:
                    color = (0, 255, 0)  # 绿色：格栅口可见，无积煤
                    status = "GRID_VISIBLE"

                # 记录结果
                results.append({
                    'row': r,
                    'col': c,
                    'x': x1, 'y': y1, 'w': cell_w, 'h': cell_h,
                    'roi_x': roi_x1, 'roi_y': roi_y1,
                    'roi_w': roi_x2 - roi_x1, 'roi_h': roi_y2 - roi_y1,
                    'mean_brightness': mean_brightness,
                    'std_brightness': std_brightness,
                    'texture_variance': texture_variance,
                    'edge_density': edge_density,
                    'avg_gradient': avg_gradient,
                    'structure_score': structure_score,
                    'coal_detected': coal_detected,
                    'status': status
                })

                # 绘制调试信息
                # 外框
                cv2.rectangle(debug_view, (x1, y1), (x2, y2), color, 2)
                # ROI区域
                cv2.rectangle(debug_view, (roi_x1, roi_y1), (roi_x2, roi_y2), color, 1)
                # 结构评分
                cv2.putText(debug_view, f"{structure_score:.1f}",
                           (x1 + 5, y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
                # 格子编号
                cv2.putText(debug_view, f"R{r}C{c}",
                           (x1 + 5, y2 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 255), 1)

        # 统计信息
        total_cells = rows * cols
        coal_detected_count = blocked_count
        grid_visible_count = total_cells - blocked_count
        no_coal_ratio = grid_visible_count / total_cells if total_cells > 0 else 0

        print(f"积煤检测统计:")
        print(f"  总格栅区域: {total_cells}")
        print(f"  检测到积煤: {coal_detected_count}")
        print(f"  格栅口可见: {grid_visible_count}")
        print(f"  无积煤比例: {no_coal_ratio:.1%}")

        if brightness_stats:
            print(f"亮度统计:")
            print(f"  平均亮度: {np.mean(brightness_stats):.1f}")
            print(f"  亮度范围: {min(brightness_stats):.1f} - {max(brightness_stats):.1f}")
            print(f"  标准差: {np.std(brightness_stats):.1f}")

        # 添加统计信息到图像
        info_text = f"Total:{total_cells} GridVisible:{grid_visible_count} CoalDetected:{coal_detected_count} NoCoalRatio:{no_coal_ratio:.1%}"
        cv2.putText(debug_view, info_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(debug_view, info_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)

        self.save_debug_image(debug_view, "coal_detection",
                            f"积煤检测结果({grid_visible_count}/{total_cells}无积煤)")

        return results, {
            'total_cells': total_cells,
            'coal_detected_count': coal_detected_count,
            'grid_visible_count': grid_visible_count,
            'no_coal_ratio': no_coal_ratio,
            'brightness_stats': brightness_stats
        }

    def detect_with_perspective_correction(self, image_path: str):
        """完整的透视矫正+虚拟网格检测流程"""
        print(f"\n{'='*60}")
        print(f"开始透视矫正网格检测: {Path(image_path).name}")
        print(f"{'='*60}")

        # 重置计数器
        self.debug_counter = 0

        try:
            # 步骤1: 图像预处理
            original, enhanced = self.step1_preprocess_image(image_path)

            # 步骤2: 透视变换
            warped, warped_gray, transform_matrix = self.step2_perspective_transform(enhanced)

            # 步骤3: 虚拟网格切片检测
            results, stats = self.step3_virtual_grid_slicing(warped, warped_gray)

            print(f"\n{'='*60}")
            print(f"透视矫正积煤检测完成！共 {self.debug_counter} 个步骤")
            print(f"最终结果: {stats['grid_visible_count']}/{stats['total_cells']} 区域无积煤")
            print(f"调试图片保存在: {self.debug_dir}")
            print(f"{'='*60}")

            return {
                'results': results,
                'stats': stats,
                'transform_matrix': transform_matrix,
                'debug_dir': str(self.debug_dir)
            }

        except Exception as e:
            print(f"[ERROR] 检测过程出错: {e}")
            return None

    def suggest_threshold(self, image_path: str, sample_points: List[Tuple[int, int, str]]):
        """辅助功能：建议亮度阈值"""
        """
        sample_points: [(row, col, "CLEAR"), (row, col, "BLOCKED"), ...]
        """
        print("\n=== 阈值建议分析 ===")

        result = self.detect_with_perspective_correction(image_path)
        if not result:
            return

        results = result['results']

        clear_brightness = []
        blocked_brightness = []

        for r, c, expected_status in sample_points:
            # 找到对应的检测结果
            cell_result = None
            for res in results:
                if res['row'] == r and res['col'] == c:
                    cell_result = res
                    break

            if cell_result:
                brightness = cell_result['mean_brightness']
                if expected_status == "CLEAR":
                    clear_brightness.append(brightness)
                elif expected_status == "BLOCKED":
                    blocked_brightness.append(brightness)
                print(f"  格子[{r},{c}] 期望:{expected_status} 亮度:{brightness:.1f}")

        if clear_brightness and blocked_brightness:
            clear_avg = np.mean(clear_brightness)
            blocked_avg = np.mean(blocked_brightness)
            suggested_threshold = (clear_avg + blocked_avg) / 2

            print(f"\n阈值分析:")
            print(f"  通畅格栅平均亮度: {clear_avg:.1f}")
            print(f"  堵塞区域平均亮度: {blocked_avg:.1f}")
            print(f"  建议阈值: {suggested_threshold:.1f}")

            return suggested_threshold
        else:
            print("需要提供通畅和堵塞的样本点进行分析")
            return None


def main():
    parser = argparse.ArgumentParser(description="透视矫正+虚拟网格检测器")
    parser.add_argument("image_path", help="格栅图片路径")
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument("--rows", type=int, default=8, help="网格行数")
    parser.add_argument("--cols", type=int, default=8, help="网格列数")
    parser.add_argument("--threshold", type=float, default=5.0, help="结构评分阈值（低于此值检测为积煤覆盖）")

    args = parser.parse_args()

    # 创建检测器
    detector = PerspectiveGridDetector(args.config)

    # 如果没有配置文件，需要手动设置标定点
    if not args.config:
        print("\n警告: 未提供配置文件，使用默认标定点（可能不准确）")
        print("建议使用标定工具获取准确的四个角点")

        # 默认标定点（基于图片大概估算）
        default_points = [
            [150, 80],   # 左上
            [480, 110],  # 右上
            [500, 450],  # 右下
            [60, 420]    # 左下
        ]

        detector.set_calibration_points(default_points, (args.rows, args.cols))
        detector.config['structure_threshold'] = args.threshold

    # 运行检测
    result = detector.detect_with_perspective_correction(args.image_path)

    if result:
        stats = result['stats']
        print(f"\n最终积煤检测结果:")
        print(f"  格栅口可见: {stats['grid_visible_count']}/{stats['total_cells']}")
        print(f"  无积煤比例: {stats['no_coal_ratio']:.1%}")


if __name__ == "__main__":
    main()