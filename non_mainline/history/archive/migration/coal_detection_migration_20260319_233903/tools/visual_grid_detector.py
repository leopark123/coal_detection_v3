"""
可视化增强版格栅检测器
实现"所见即所得"的逆向映射显示
"""

import cv2
import numpy as np
import yaml
import json
from pathlib import Path
import argparse
from typing import List, Tuple, Dict


class VisualGridDetector:
    """可视化格栅检测器 - 支持逆向映射显示"""

    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.debug_counter = 0

    def _load_config(self, config_path: str) -> dict:
        """加载标定配置"""
        if not Path(config_path).exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        if config_path.endswith('.yaml') or config_path.endswith('.yml'):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
        else:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

        print(f"[CONFIG] 已加载配置: {config_path}")
        print(f"         格栅形状: {config['grid_shape'][0]}行 x {config['grid_shape'][1]}列")
        print(f"         角点坐标: {config['calibration_points']}")

        return config

    def _preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """图像预处理 - CLAHE增强"""
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l_enhanced = clahe.apply(l)
        enhanced = cv2.merge((l_enhanced, a, b))
        return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    def _calculate_transforms(self) -> Tuple[np.ndarray, np.ndarray]:
        """计算透视变换矩阵和逆矩阵"""
        src_pts = np.float32(self.config['calibration_points'])
        target_w, target_h = self.config['target_size']

        dst_pts = np.float32([
            [0, 0],
            [target_w, 0],
            [target_w, target_h],
            [0, target_h]
        ])

        # 正向变换：原图 → 矫正图
        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        # 逆向变换：矫正图 → 原图 (关键！)
        M_inv = cv2.getPerspectiveTransform(dst_pts, src_pts)

        return M, M_inv

    def _detect_grid_structure(self, roi: np.ndarray) -> Tuple[float, bool]:
        """检测格栅口结构可见性"""
        if roi.size == 0:
            return 0.0, True

        # 计算纹理特征
        texture_variance = np.var(roi)

        # 计算边缘密度
        edges = cv2.Canny(roi, 50, 150)
        edge_density = np.sum(edges > 0) / edges.size

        # 计算梯度强度
        sobelx = cv2.Sobel(roi, cv2.CV_64F, 1, 0, ksize=3)
        sobely = cv2.Sobel(roi, cv2.CV_64F, 0, 1, ksize=3)
        gradient_magnitude = np.sqrt(sobelx**2 + sobely**2)
        avg_gradient = np.mean(gradient_magnitude)

        # 综合评分：纹理方差 + 边缘密度 + 梯度强度
        structure_score = (texture_variance / 100) + (edge_density * 100) + (avg_gradient / 10)

        # 判断: 结构评分低 → 被积煤覆盖
        coal_detected = structure_score < self.config['structure_threshold']

        return structure_score, coal_detected

    def _create_grid_box(self, row: int, col: int, cell_w: float, cell_h: float,
                        padding_ratio: float) -> np.ndarray:
        """创建单个格子的四角坐标（在矫正图坐标系中）"""
        x1 = col * cell_w
        y1 = row * cell_h
        x2 = (col + 1) * cell_w
        y2 = (row + 1) * cell_h

        # 内缩，避免检测到格栅条
        pad_x = cell_w * padding_ratio
        pad_y = cell_h * padding_ratio

        # 返回四个角点
        return np.float32([
            [x1 + pad_x, y1 + pad_y],  # 左上
            [x2 - pad_x, y1 + pad_y],  # 右上
            [x2 - pad_x, y2 - pad_y],  # 右下
            [x1 + pad_x, y2 - pad_y]   # 左下
        ]).reshape(-1, 1, 2)

    def detect_and_visualize(self, image_path: str) -> Dict:
        """完整的检测和可视化流程"""
        print(f"\n{'='*60}")
        print(f"开始可视化格栅检测: {Path(image_path).name}")
        print(f"{'='*60}")

        # 1. 加载和预处理图片
        original = cv2.imread(image_path)
        if original is None:
            raise ValueError(f"无法加载图片: {image_path}")

        print(f"原图尺寸: {original.shape[1]} x {original.shape[0]}")

        enhanced = self._preprocess_image(original)

        # 2. 计算变换矩阵
        M, M_inv = self._calculate_transforms()

        # 3. 透视变换到标准平面
        target_w, target_h = self.config['target_size']
        warped = cv2.warpPerspective(enhanced, M, (target_w, target_h))
        warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

        print(f"矫正图尺寸: {target_w} x {target_h}")

        # 4. 网格分析
        rows, cols = self.config['grid_shape']
        cell_w = target_w / cols
        cell_h = target_h / rows
        padding_ratio = self.config.get('roi_padding_ratio', 0.15)

        print(f"网格配置: {rows}行 x {cols}列")
        print(f"单元格尺寸: {cell_w:.1f} x {cell_h:.1f}")
        print(f"内缩比例: {padding_ratio:.1%}")

        # 结果存储
        results = []
        coal_detected_count = 0
        structure_scores = []

        # 创建结果可视化图像
        result_view = original.copy()
        computer_view = warped.copy()

        # 遍历每个格子
        for r in range(rows):
            for c in range(cols):
                # A. 在矫正图上定义ROI
                x1 = int(c * cell_w)
                y1 = int(r * cell_h)
                x2 = int((c + 1) * cell_w)
                y2 = int((r + 1) * cell_h)

                # 内缩ROI
                pad_x = int(cell_w * padding_ratio)
                pad_y = int(cell_h * padding_ratio)

                roi = warped_gray[y1+pad_y:y2-pad_y, x1+pad_x:x2-pad_x]

                # B. 结构检测
                structure_score, coal_detected = self._detect_grid_structure(roi)
                structure_scores.append(structure_score)

                if coal_detected:
                    coal_detected_count += 1
                    color = (0, 0, 255)  # 红色：检测到积煤
                    status = "COAL"
                else:
                    color = (0, 255, 0)  # 绿色：格栅口可见
                    status = "CLEAR"

                # 记录结果
                results.append({
                    'row': r,
                    'col': c,
                    'structure_score': structure_score,
                    'coal_detected': coal_detected,
                    'status': status
                })

                # C. 在矫正图上画矩形框（给算法看）
                cv2.rectangle(computer_view, (x1+pad_x, y1+pad_y), (x2-pad_x, y2-pad_y), color, 2)
                cv2.putText(computer_view, f"{structure_score:.1f}",
                           (x1+pad_x+5, y1+pad_y+20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)

                # D. ★ 关键：逆向映射到原图（给人看）
                # 创建格子的四角坐标
                box_warped = self._create_grid_box(r, c, cell_w, cell_h, padding_ratio)

                # 用逆矩阵变换回原图坐标
                box_original = cv2.perspectiveTransform(box_warped, M_inv)
                box_original = box_original.astype(int)

                # 画透视正确的多边形框
                cv2.polylines(result_view, [box_original], True, color, 2)

                # 在框中心写状态
                center = np.mean(box_original, axis=0).astype(int)[0]
                if status == "COAL":
                    cv2.putText(result_view, "X", tuple(center-10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                # 显示结构评分（可选）
                cv2.putText(result_view, f"{structure_score:.1f}",
                           tuple(center+[0, 20]), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 0), 1)

        # 5. 统计信息
        total_cells = rows * cols
        grid_visible_count = total_cells - coal_detected_count
        no_coal_ratio = grid_visible_count / total_cells

        stats = {
            'total_cells': total_cells,
            'coal_detected_count': coal_detected_count,
            'grid_visible_count': grid_visible_count,
            'no_coal_ratio': no_coal_ratio,
            'structure_scores': structure_scores
        }

        print(f"\n检测统计:")
        print(f"  总格栅区域: {total_cells}")
        print(f"  检测到积煤: {coal_detected_count}")
        print(f"  格栅口可见: {grid_visible_count}")
        print(f"  无积煤比例: {no_coal_ratio:.1%}")

        if structure_scores:
            print(f"  结构评分范围: {min(structure_scores):.1f} - {max(structure_scores):.1f}")
            print(f"  平均结构评分: {np.mean(structure_scores):.1f}")

        # 6. 添加统计信息到图像
        info_text = f"Coal Detected: {coal_detected_count}/{total_cells} ({(1-no_coal_ratio):.1%})"
        cv2.putText(result_view, info_text, (30, 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 3)
        cv2.putText(result_view, info_text, (30, 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 1)

        info_text2 = f"Grid Visible: {grid_visible_count}/{total_cells} ({no_coal_ratio:.1%})"
        cv2.putText(result_view, info_text2, (30, 90),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 3)
        cv2.putText(result_view, info_text2, (30, 90),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 1)

        # 在computer_view上也添加统计
        cv2.putText(computer_view, info_text, (20, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        print(f"\n{'='*60}")
        print(f"可视化格栅检测完成！")
        print(f"{'='*60}")

        return {
            'results': results,
            'stats': stats,
            'computer_view': computer_view,  # 矫正后的平面图（算法视角）
            'result_view': result_view,      # 逆向映射的原图（人眼视角）
            'config': self.config
        }


def main():
    parser = argparse.ArgumentParser(description="可视化格栅检测器")
    parser.add_argument("image_path", help="格栅图片路径")
    parser.add_argument("--config", required=True, help="标定配置文件路径")
    parser.add_argument("--save-result", help="保存结果图片路径")

    args = parser.parse_args()

    try:
        # 创建检测器
        detector = VisualGridDetector(args.config)

        # 运行检测
        result = detector.detect_and_visualize(args.image_path)

        # 显示结果
        print(f"\n=== 显示窗口 ===")
        print(f"Computer View: 矫正后的平面图 (算法视角)")
        print(f"Human View: 逆向映射的原图 (操作员视角)")
        print(f"按任意键关闭窗口")

        cv2.imshow("Computer View (Algorithm)", result['computer_view'])
        cv2.imshow("Human View (Operator)", result['result_view'])

        # 保存结果
        if args.save_result:
            base_path = Path(args.save_result)
            cv2.imwrite(str(base_path.with_suffix('.computer.jpg')), result['computer_view'])
            cv2.imwrite(str(base_path.with_suffix('.human.jpg')), result['result_view'])
            print(f"\n结果已保存:")
            print(f"  算法视角: {base_path.with_suffix('.computer.jpg')}")
            print(f"  操作员视角: {base_path.with_suffix('.human.jpg')}")

        cv2.waitKey(0)
        cv2.destroyAllWindows()

    except Exception as e:
        print(f"❌ 检测失败: {e}")


if __name__ == "__main__":
    main()