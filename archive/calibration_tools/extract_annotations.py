"""
提取手动标注结果
从标注图片中提取蓝色标注框，生成检测配置
"""

import cv2
import numpy as np
import json
from pathlib import Path
import argparse
from typing import List, Dict, Tuple


class AnnotationExtractor:
    """标注提取器"""

    def __init__(self, annotated_image_path: str):
        self.image_path = annotated_image_path
        self.image = None
        self.boxes = []

    def extract_blue_boxes(self) -> List[Dict]:
        """提取蓝色标注框"""
        # 1. 加载图片
        self.image = cv2.imread(self.image_path)
        if self.image is None:
            raise ValueError(f"无法加载图片: {self.image_path}")

        print(f"分析标注图片: {Path(self.image_path).name}")
        print(f"图片尺寸: {self.image.shape[1]} x {self.image.shape[0]}")

        # 2. 转换为HSV色彩空间
        hsv = cv2.cvtColor(self.image, cv2.COLOR_BGR2HSV)

        # 3. 提取蓝色区域
        # 蓝色的HSV范围
        lower_blue = np.array([100, 50, 50])
        upper_blue = np.array([130, 255, 255])

        # 创建蓝色掩码
        blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)

        # 形态学操作，连接断开的线条
        kernel = np.ones((3, 3), np.uint8)
        blue_mask = cv2.morphologyEx(blue_mask, cv2.MORPH_CLOSE, kernel)

        # 4. 查找轮廓
        contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        print(f"找到 {len(contours)} 个蓝色轮廓")

        # 5. 分析轮廓，提取矩形框
        boxes = []
        for i, contour in enumerate(contours):
            # 计算轮廓面积
            area = cv2.contourArea(contour)

            # 过滤太小的轮廓（噪声）
            if area < 500:  # 调整阈值
                continue

            # 获取边界矩形
            x, y, w, h = cv2.boundingRect(contour)

            # 过滤明显不是格子的矩形（太细长或太小）
            aspect_ratio = w / h if h > 0 else 0
            if aspect_ratio < 0.3 or aspect_ratio > 3.0:
                continue

            if w < 10 or h < 10:
                continue

            boxes.append({
                'id': i,
                'x': x,
                'y': y,
                'width': w,
                'height': h,
                'center_x': x + w // 2,
                'center_y': y + h // 2,
                'area': area,
                'points': [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
            })

        print(f"提取到 {len(boxes)} 个有效矩形框")

        # 6. 按位置排序（从上到下，从左到右）
        boxes.sort(key=lambda b: (b['center_y'] // 30, b['center_x']))  # 30像素容差分行

        # 7. 重新分配ID
        for i, box in enumerate(boxes):
            box['id'] = i

        self.boxes = boxes
        return boxes

    def estimate_grid_shape(self) -> Tuple[int, int]:
        """估算网格行列数"""
        if not self.boxes:
            return 0, 0

        # 按Y坐标分组，确定行数
        y_centers = [box['center_y'] for box in self.boxes]
        y_unique = []

        for y in y_centers:
            # 查找相近的Y坐标（同一行）
            found = False
            for existing_y in y_unique:
                if abs(y - existing_y) < 30:  # 30像素容差
                    found = True
                    break
            if not found:
                y_unique.append(y)

        rows = len(y_unique)

        # 按X坐标分组，确定列数
        x_centers = [box['center_x'] for box in self.boxes]
        x_unique = []

        for x in x_centers:
            found = False
            for existing_x in x_unique:
                if abs(x - existing_x) < 30:  # 30像素容差
                    found = True
                    break
            if not found:
                x_unique.append(x)

        cols = len(x_unique)

        print(f"估算网格形状: {rows}行 x {cols}列")
        return rows, cols

    def generate_config(self, output_path: str):
        """生成检测配置"""
        if not self.boxes:
            raise ValueError("没有提取到标注框")

        rows, cols = self.estimate_grid_shape()

        # 转换为检测器需要的格式
        valid_cells = []
        for box in self.boxes:
            cell_data = {
                "id": box['id'],
                "row": box['id'] // cols if cols > 0 else 0,
                "col": box['id'] % cols if cols > 0 else 0,
                "points": box['points'],
                "area": float(box['area'])
            }
            valid_cells.append(cell_data)

        # 生成全图ROI掩码（整个图片都是有效区域）
        h, w = self.image.shape[:2]
        mask_polygon = [[0, 0], [w, 0], [w, h], [0, h]]

        config_data = {
            "source_image": self.image_path,
            "calibration_method": "manual_annotation_extracted",
            "mask_polygon": mask_polygon,
            "logic_shape": [rows, cols],
            "total_theoretical": rows * cols,
            "valid_cells": valid_cells,
            "valid_count": len(valid_cells),
            "extraction_info": {
                "total_boxes_found": len(self.boxes),
                "estimated_grid": f"{rows}x{cols}",
                "coverage_ratio": len(valid_cells) / (rows * cols) if rows * cols > 0 else 0
            }
        }

        # 保存配置
        Path(output_path).parent.mkdir(exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)

        print(f"\n[SAVED] 标注提取配置已保存: {output_path}")
        print(f"         总标注框: {len(self.boxes)}")
        print(f"         网格形状: {rows}行 x {cols}列")
        print(f"         有效格子: {len(valid_cells)}")
        print(f"         覆盖率: {len(valid_cells)/(rows*cols)*100:.1f}%" if rows*cols > 0 else "")

    def visualize_extraction(self, output_path: str = None):
        """可视化提取结果"""
        if not self.boxes:
            return None

        canvas = self.image.copy()

        # 绘制提取的矩形框
        for box in self.boxes:
            x, y, w, h = box['x'], box['y'], box['width'], box['height']

            # 绘制绿色边框（表示成功提取）
            cv2.rectangle(canvas, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # 绘制ID
            center = (box['center_x'], box['center_y'])
            cv2.putText(canvas, str(box['id'] + 1), center,
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(canvas, str(box['id'] + 1), center,
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)

        # 添加统计信息
        rows, cols = self.estimate_grid_shape()
        info_text = f"Extracted: {len(self.boxes)} boxes, Grid: {rows}x{cols}"
        cv2.putText(canvas, info_text, (20, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        if output_path:
            cv2.imwrite(output_path, canvas)
            print(f"可视化结果已保存: {output_path}")

        return canvas


def main():
    parser = argparse.ArgumentParser(description="提取手动标注结果")
    parser.add_argument("annotated_image", help="标注图片路径")
    parser.add_argument("--output", default="config/grid_manual_extracted.json", help="输出配置文件")
    parser.add_argument("--visualize", help="保存可视化结果图片路径")

    args = parser.parse_args()

    try:
        extractor = AnnotationExtractor(args.annotated_image)

        # 提取标注框
        boxes = extractor.extract_blue_boxes()

        # 生成配置
        extractor.generate_config(args.output)

        # 可视化结果
        if args.visualize:
            extractor.visualize_extraction(args.visualize)

        print(f"\n✅ 标注提取完成！")
        print(f"配置文件: {args.output}")
        print(f"现在可以用此配置进行检测")

    except Exception as e:
        print(f"❌ 提取失败: {e}")


if __name__ == "__main__":
    main()