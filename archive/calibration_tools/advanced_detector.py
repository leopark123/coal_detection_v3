"""
高级柔性网格检测器
配套高级标定工具，支持：
1. 不规则四边形ROI
2. 掩码区域过滤
3. 结构可见性检测
"""

import cv2
import numpy as np
import json
from pathlib import Path
import argparse
from typing import List, Dict, Tuple


class AdvancedGridDetector:
    """高级柔性网格检测器"""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = self._load_config()
        self.global_mask = None

    def _load_config(self) -> dict:
        """加载高级标定配置"""
        if not Path(self.config_path).exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        print(f"[CONFIG] 已加载高级标定配置: {self.config_path}")
        print(f"         标定方法: {config['calibration_method']}")
        print(f"         理论网格: {config['logic_shape'][0]}行 x {config['logic_shape'][1]}列")
        print(f"         有效格子: {config['valid_count']}/{config['total_theoretical']}")
        print(f"         覆盖率: {config['valid_count']/config['total_theoretical']*100:.1f}%")

        return config

    def _create_global_mask(self, image_shape: Tuple[int, int]) -> np.ndarray:
        """创建全局ROI掩码"""
        mask = np.zeros(image_shape[:2], dtype=np.uint8)

        # 根据掩码多边形创建掩码
        if 'mask_polygon' in self.config and self.config['mask_polygon']:
            polygon_pts = np.array(self.config['mask_polygon'], dtype=np.int32)
            cv2.fillPoly(mask, [polygon_pts], 255)

        return mask

    def _create_cell_mask(self, cell_points: List[List[float]], image_shape: Tuple[int, int]) -> np.ndarray:
        """为单个格子创建掩码"""
        mask = np.zeros(image_shape[:2], dtype=np.uint8)

        # 转换为整数坐标
        pts = np.array(cell_points, dtype=np.int32)
        pts = pts.reshape((-1, 1, 2))

        # 填充四边形
        cv2.fillPoly(mask, [pts], 255)

        return mask

    def _analyze_cell_structure(self, image: np.ndarray, cell_mask: np.ndarray,
                               global_mask: np.ndarray, cell_id: int) -> Dict:
        """分析单个格子的结构可见性"""
        # 转换为灰度图
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # 应用全局掩码和格子掩码
        combined_mask = cv2.bitwise_and(cell_mask, global_mask)
        cell_gray = cv2.bitwise_and(gray, gray, mask=combined_mask)

        # 只分析掩码区域内的像素
        cell_pixels = cell_gray[combined_mask > 0]

        if len(cell_pixels) == 0:
            return {
                'cell_id': cell_id,
                'mean_brightness': 0,
                'texture_variance': 0,
                'edge_density': 0,
                'avg_gradient': 0,
                'structure_score': 0,
                'grid_visible': False,
                'status': 'INVALID',
                'pixel_count': 0
            }

        total_pixels = np.sum(combined_mask > 0)

        # 1. 亮度特征
        mean_brightness = np.mean(cell_pixels)

        # 2. 纹理特征（方差）
        texture_variance = np.var(cell_pixels)

        # 3. 边缘特征
        cell_edges = cv2.Canny(cell_gray, 50, 150)
        cell_edges = cv2.bitwise_and(cell_edges, cell_edges, mask=combined_mask)
        edge_pixels = np.sum(cell_edges > 0)
        edge_density = edge_pixels / total_pixels if total_pixels > 0 else 0

        # 4. 梯度特征
        sobelx = cv2.Sobel(cell_gray, cv2.CV_64F, 1, 0, ksize=3)
        sobely = cv2.Sobel(cell_gray, cv2.CV_64F, 0, 1, ksize=3)
        gradient_magnitude = np.sqrt(sobelx**2 + sobely**2)
        gradient_masked = cv2.bitwise_and(gradient_magnitude.astype(np.uint8),
                                        gradient_magnitude.astype(np.uint8), mask=combined_mask)
        avg_gradient = np.mean(gradient_magnitude[combined_mask > 0]) if total_pixels > 0 else 0

        # 5. 综合结构评分
        # 结构可见性 = 纹理丰富 + 边缘清晰 + 梯度强烈
        structure_score = (texture_variance / 100) + (edge_density * 100) + (avg_gradient / 10)

        # 6. 判断网格可见性
        # 结构评分高说明格栅结构可见，评分低说明被积煤覆盖
        threshold = 5.0  # 可配置
        grid_visible = structure_score >= threshold

        status = "GRID_VISIBLE" if grid_visible else "COAL_DETECTED"

        return {
            'cell_id': cell_id,
            'mean_brightness': float(mean_brightness),
            'texture_variance': float(texture_variance),
            'edge_density': float(edge_density),
            'avg_gradient': float(avg_gradient),
            'structure_score': float(structure_score),
            'grid_visible': grid_visible,
            'status': status,
            'pixel_count': int(total_pixels)
        }

    def _draw_cell_result(self, image: np.ndarray, cell_points: List[List[float]],
                         result: Dict, draw_details: bool = True) -> np.ndarray:
        """在图像上绘制格子检测结果"""
        canvas = image.copy()

        # 转换坐标
        pts = np.array(cell_points, dtype=np.int32)

        # 根据检测结果选择颜色
        color = (0, 255, 0) if result['grid_visible'] else (0, 0, 255)

        # 绘制四边形边框
        cv2.polylines(canvas, [pts], True, color, 2)

        if draw_details:
            # 计算中心点
            center = np.mean(pts, axis=0).astype(int)

            # 绘制格子ID
            cv2.putText(canvas, f"#{result['cell_id']+1}", tuple(center - [15, 15]),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            cv2.putText(canvas, f"#{result['cell_id']+1}", tuple(center - [15, 15]),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

            # 绘制结构评分
            cv2.putText(canvas, f"{result['structure_score']:.1f}",
                       tuple(center + [0, 15]), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)

            # 绘制状态标记
            if not result['grid_visible']:
                cv2.putText(canvas, "COAL", tuple(center + [0, -5]),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

        return canvas

    def _draw_roi_mask(self, image: np.ndarray) -> np.ndarray:
        """绘制ROI掩码边界"""
        canvas = image.copy()

        if 'mask_polygon' in self.config and self.config['mask_polygon']:
            polygon_pts = np.array(self.config['mask_polygon'], dtype=np.int32)
            cv2.polylines(canvas, [polygon_pts], True, (255, 0, 255), 2)

            # 添加掩码区域半透明覆盖
            overlay = canvas.copy()
            cv2.fillPoly(overlay, [polygon_pts], (255, 0, 255))
            cv2.addWeighted(canvas, 0.95, overlay, 0.05, 0, canvas)

        return canvas

    def detect_grid_accumulation(self, image_path: str) -> Dict:
        """执行格栅积煤检测"""
        print(f"\n{'='*60}")
        print(f"开始高级网格积煤检测: {Path(image_path).name}")
        print(f"{'='*60}")

        # 1. 加载图片
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"无法加载图片: {image_path}")

        print(f"图片尺寸: {image.shape[1]} x {image.shape[0]}")

        # 2. 创建全局掩码
        self.global_mask = self._create_global_mask(image.shape)

        # 3. 图像预处理
        enhanced = self._preprocess_image(image)

        # 4. 逐个分析有效格子
        results = []
        coal_detected_count = 0
        structure_scores = []

        result_image = enhanced.copy()

        # 绘制ROI掩码
        result_image = self._draw_roi_mask(result_image)

        for cell_data in self.config['valid_cells']:
            cell_id = cell_data['id']
            cell_points = cell_data['points']

            # 创建格子掩码
            cell_mask = self._create_cell_mask(cell_points, image.shape)

            # 分析结构特征
            cell_result = self._analyze_cell_structure(enhanced, cell_mask, self.global_mask, cell_id)

            # 记录结果
            results.append(cell_result)
            structure_scores.append(cell_result['structure_score'])

            if not cell_result['grid_visible']:
                coal_detected_count += 1

            # 绘制结果
            result_image = self._draw_cell_result(result_image, cell_points, cell_result)

        # 5. 统计分析
        total_valid = len(results)
        grid_visible_count = total_valid - coal_detected_count
        no_coal_ratio = grid_visible_count / total_valid if total_valid > 0 else 0

        stats = {
            'total_theoretical': self.config['total_theoretical'],
            'total_valid': total_valid,
            'coal_detected_count': coal_detected_count,
            'grid_visible_count': grid_visible_count,
            'no_coal_ratio': no_coal_ratio,
            'coverage_ratio': total_valid / self.config['total_theoretical'],
            'avg_structure_score': np.mean(structure_scores) if structure_scores else 0,
            'min_structure_score': np.min(structure_scores) if structure_scores else 0,
            'max_structure_score': np.max(structure_scores) if structure_scores else 0
        }

        print(f"\n检测统计:")
        print(f"  理论格子: {self.config['total_theoretical']}")
        print(f"  有效格子: {total_valid}")
        print(f"  检测到积煤: {coal_detected_count}")
        print(f"  格栅可见: {grid_visible_count}")
        print(f"  无积煤比例: {no_coal_ratio:.1%}")
        print(f"  结构评分范围: {stats['min_structure_score']:.1f} - {stats['max_structure_score']:.1f}")
        print(f"  平均结构评分: {stats['avg_structure_score']:.1f}")

        # 6. 添加统计信息到图像
        info_text1 = f"Coal: {coal_detected_count}/{total_valid} ({(1-no_coal_ratio):.1%})"
        cv2.putText(result_image, info_text1, (30, 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 3)
        cv2.putText(result_image, info_text1, (30, 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 1)

        info_text2 = f"Grid Visible: {grid_visible_count}/{total_valid} ({no_coal_ratio:.1%})"
        cv2.putText(result_image, info_text2, (30, 90),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 3)
        cv2.putText(result_image, info_text2, (30, 90),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 1)

        info_text3 = f"Coverage: {total_valid}/{self.config['total_theoretical']} ({stats['coverage_ratio']:.1%})"
        cv2.putText(result_image, info_text3, (30, 130),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 3)
        cv2.putText(result_image, info_text3, (30, 130),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 1)

        print(f"\n{'='*60}")
        print(f"高级网格积煤检测完成！")
        print(f"{'='*60}")

        return {
            'results': results,
            'stats': stats,
            'result_image': result_image,
            'config': self.config
        }

    def _preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """图像预处理"""
        # CLAHE对比度增强
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l_enhanced = clahe.apply(l)
        enhanced = cv2.merge((l_enhanced, a, b))
        return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)


def main():
    parser = argparse.ArgumentParser(description="高级柔性网格积煤检测器")
    parser.add_argument("image_path", help="格栅图片路径")
    parser.add_argument("--config", required=True, help="高级标定配置文件路径")
    parser.add_argument("--save-result", help="保存结果图片路径")

    args = parser.parse_args()

    try:
        # 创建检测器
        detector = AdvancedGridDetector(args.config)

        # 运行检测
        result = detector.detect_grid_accumulation(args.image_path)

        # 显示结果
        cv2.imshow("Advanced Grid Detection Result", result['result_image'])

        # 保存结果
        if args.save_result:
            cv2.imwrite(args.save_result, result['result_image'])
            print(f"\n结果已保存: {args.save_result}")

        print(f"\n按任意键关闭窗口...")
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    except Exception as e:
        print(f"检测失败: {e}")


if __name__ == "__main__":
    main()