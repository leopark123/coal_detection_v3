"""
支持柔性网格的格栅检测器
处理不规则四边形ROI，适应现场格栅变形情况
"""

import cv2
import numpy as np
import yaml
import json
from pathlib import Path
import argparse
from typing import List, Dict, Tuple


class FlexibleGridDetector:
    """支持柔性网格的检测器"""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """加载柔性网格配置"""
        if not Path(self.config_path).exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

        if self.config_path.endswith('.yaml') or self.config_path.endswith('.yml'):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
        else:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

        print(f"[CONFIG] 已加载柔性网格配置: {self.config_path}")
        print(f"         网格形状: {config['grid_shape'][0]}行 x {config['grid_shape'][1]}列")
        print(f"         ROI数量: {config['total_rois']}")
        print(f"         标定方法: {config['calibration_method']}")

        return config

    def _create_roi_mask(self, roi_points: List[List[float]], image_shape: Tuple[int, int]) -> np.ndarray:
        """为单个ROI创建掩码"""
        mask = np.zeros(image_shape[:2], dtype=np.uint8)

        # 转换为整数坐标
        pts = np.array(roi_points, dtype=np.int32)
        pts = pts.reshape((-1, 1, 2))

        # 填充多边形
        cv2.fillPoly(mask, [pts], 255)

        return mask

    def _analyze_roi_structure(self, image: np.ndarray, roi_mask: np.ndarray, roi_id: int) -> Dict:
        """分析单个ROI的结构特征"""
        # 转换为灰度图
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # 应用ROI掩码
        roi_gray = cv2.bitwise_and(gray, gray, mask=roi_mask)

        # 只分析掩码区域内的像素
        roi_pixels = roi_gray[roi_mask > 0]

        if len(roi_pixels) == 0:
            return {
                'roi_id': roi_id,
                'mean_brightness': 0,
                'texture_variance': 0,
                'edge_density': 0,
                'structure_score': 0,
                'coal_detected': True,
                'status': 'INVALID'
            }

        # 1. 亮度特征
        mean_brightness = np.mean(roi_pixels)

        # 2. 纹理特征（方差）
        texture_variance = np.var(roi_pixels)

        # 3. 边缘特征
        # 在掩码区域内进行边缘检测
        roi_edges = cv2.Canny(roi_gray, 50, 150)
        roi_edges = cv2.bitwise_and(roi_edges, roi_edges, mask=roi_mask)
        edge_pixels = np.sum(roi_edges > 0)
        total_pixels = np.sum(roi_mask > 0)
        edge_density = edge_pixels / total_pixels if total_pixels > 0 else 0

        # 4. 梯度特征
        sobelx = cv2.Sobel(roi_gray, cv2.CV_64F, 1, 0, ksize=3)
        sobely = cv2.Sobel(roi_gray, cv2.CV_64F, 0, 1, ksize=3)
        gradient_magnitude = np.sqrt(sobelx**2 + sobely**2)
        gradient_masked = cv2.bitwise_and(gradient_magnitude.astype(np.uint8),
                                        gradient_magnitude.astype(np.uint8), mask=roi_mask)
        avg_gradient = np.mean(gradient_magnitude[roi_mask > 0]) if total_pixels > 0 else 0

        # 5. 综合评分
        # 格栅口结构可见性评分：纹理丰富 + 边缘清晰 + 梯度强烈
        structure_score = (texture_variance / 100) + (edge_density * 100) + (avg_gradient / 10)

        # 6. 判断积煤
        # 结构评分低说明格栅口被覆盖（纹理平坦、边缘模糊）
        threshold = 5.0  # 可配置
        coal_detected = structure_score < threshold

        status = "COAL_DETECTED" if coal_detected else "GRID_VISIBLE"

        return {
            'roi_id': roi_id,
            'mean_brightness': float(mean_brightness),
            'texture_variance': float(texture_variance),
            'edge_density': float(edge_density),
            'avg_gradient': float(avg_gradient),
            'structure_score': float(structure_score),
            'coal_detected': coal_detected,
            'status': status,
            'pixel_count': int(total_pixels)
        }

    def _draw_roi_result(self, image: np.ndarray, roi_points: List[List[float]],
                        result: Dict, draw_details: bool = True) -> np.ndarray:
        """在图像上绘制ROI检测结果"""
        canvas = image.copy()

        # 转换坐标
        pts = np.array(roi_points, dtype=np.int32)

        # 根据检测结果选择颜色
        color = (0, 0, 255) if result['coal_detected'] else (0, 255, 0)

        # 绘制多边形边框
        cv2.polylines(canvas, [pts], True, color, 2)

        if draw_details:
            # 计算中心点
            center = np.mean(pts, axis=0).astype(int)

            # 绘制ROI ID
            cv2.putText(canvas, f"#{result['roi_id']+1}", tuple(center - [15, 15]),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            cv2.putText(canvas, f"#{result['roi_id']+1}", tuple(center - [15, 15]),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

            # 绘制结构评分
            cv2.putText(canvas, f"{result['structure_score']:.1f}",
                       tuple(center + [0, 15]), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)

            # 绘制状态标记
            if result['coal_detected']:
                cv2.putText(canvas, "X", tuple(center), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        return canvas

    def detect_coal_accumulation(self, image_path: str) -> Dict:
        """执行积煤检测"""
        print(f"\n{'='*60}")
        print(f"开始柔性网格积煤检测: {Path(image_path).name}")
        print(f"{'='*60}")

        # 1. 加载图片
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"无法加载图片: {image_path}")

        print(f"图片尺寸: {image.shape[1]} x {image.shape[0]}")

        # 2. 图像预处理
        enhanced = self._preprocess_image(image)

        # 3. 逐个分析ROI
        results = []
        coal_detected_count = 0
        structure_scores = []

        result_image = enhanced.copy()

        for roi_data in self.config['rois']:
            roi_id = roi_data['id']
            roi_points = roi_data['points']

            # 创建ROI掩码
            roi_mask = self._create_roi_mask(roi_points, image.shape)

            # 分析结构特征
            roi_result = self._analyze_roi_structure(enhanced, roi_mask, roi_id)

            # 记录结果
            results.append(roi_result)
            structure_scores.append(roi_result['structure_score'])

            if roi_result['coal_detected']:
                coal_detected_count += 1

            # 绘制结果
            result_image = self._draw_roi_result(result_image, roi_points, roi_result)

        # 4. 统计分析
        total_rois = len(results)
        grid_visible_count = total_rois - coal_detected_count
        no_coal_ratio = grid_visible_count / total_rois if total_rois > 0 else 0

        stats = {
            'total_rois': total_rois,
            'coal_detected_count': coal_detected_count,
            'grid_visible_count': grid_visible_count,
            'no_coal_ratio': no_coal_ratio,
            'avg_structure_score': np.mean(structure_scores) if structure_scores else 0,
            'min_structure_score': np.min(structure_scores) if structure_scores else 0,
            'max_structure_score': np.max(structure_scores) if structure_scores else 0
        }

        print(f"\n检测统计:")
        print(f"  总ROI数量: {total_rois}")
        print(f"  检测到积煤: {coal_detected_count}")
        print(f"  格栅口可见: {grid_visible_count}")
        print(f"  无积煤比例: {no_coal_ratio:.1%}")
        print(f"  结构评分范围: {stats['min_structure_score']:.1f} - {stats['max_structure_score']:.1f}")
        print(f"  平均结构评分: {stats['avg_structure_score']:.1f}")

        # 5. 添加统计信息到图像
        info_text1 = f"Coal Detected: {coal_detected_count}/{total_rois} ({(1-no_coal_ratio):.1%})"
        cv2.putText(result_image, info_text1, (30, 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 3)
        cv2.putText(result_image, info_text1, (30, 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 1)

        info_text2 = f"Grid Visible: {grid_visible_count}/{total_rois} ({no_coal_ratio:.1%})"
        cv2.putText(result_image, info_text2, (30, 90),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 3)
        cv2.putText(result_image, info_text2, (30, 90),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 1)

        print(f"\n{'='*60}")
        print(f"柔性网格积煤检测完成！")
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
    parser = argparse.ArgumentParser(description="柔性网格积煤检测器")
    parser.add_argument("image_path", help="格栅图片路径")
    parser.add_argument("--config", required=True, help="柔性网格配置文件路径")
    parser.add_argument("--save-result", help="保存结果图片路径")

    args = parser.parse_args()

    try:
        # 创建检测器
        detector = FlexibleGridDetector(args.config)

        # 运行检测
        result = detector.detect_coal_accumulation(args.image_path)

        # 显示结果
        cv2.imshow("Flexible Grid Detection Result", result['result_image'])

        # 保存结果
        if args.save_result:
            cv2.imwrite(args.save_result, result['result_image'])
            print(f"\n结果已保存: {args.save_result}")

        print(f"\n按任意键关闭窗口...")
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    except Exception as e:
        print(f"❌ 检测失败: {e}")


if __name__ == "__main__":
    main()