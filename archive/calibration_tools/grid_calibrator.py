"""
交互式格栅标定工具
精确标定格栅区域的四个角点
"""

import cv2
import numpy as np
import json
import yaml
from pathlib import Path
import argparse

class GridCalibrator:
    """交互式格栅标定工具"""

    def __init__(self):
        self.points = []
        self.img_display = None
        self.original_img = None

    def _mouse_callback(self, event, x, y, flags, param):
        """鼠标点击回调函数"""
        if event == cv2.EVENT_LBUTTONDOWN:
            if len(self.points) < 4:
                self.points.append([x, y])

                # 画点和序号
                cv2.circle(self.img_display, (x, y), 8, (0, 0, 255), -1)
                cv2.putText(self.img_display, f"{len(self.points)}",
                           (x+15, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                # 画已经连接的线段
                if len(self.points) > 1:
                    cv2.line(self.img_display,
                            tuple(self.points[-2]), tuple(self.points[-1]),
                            (255, 0, 0), 2)

                # 如果4个点都点完了，闭合多边形
                if len(self.points) == 4:
                    cv2.line(self.img_display,
                            tuple(self.points[-1]), tuple(self.points[0]),
                            (255, 0, 0), 2)

                    # 填充半透明区域显示标定范围
                    overlay = self.img_display.copy()
                    pts = np.array(self.points, dtype=np.int32)
                    cv2.fillPoly(overlay, [pts], (0, 255, 0))
                    cv2.addWeighted(self.img_display, 0.7, overlay, 0.3, 0, self.img_display)

                cv2.imshow("Grid Calibration", self.img_display)

                print(f"已标记点 {len(self.points)}: ({x}, {y})")

    def calibrate(self, image_path: str, rows: int = 8, cols: int = 8):
        """执行标定流程"""
        print(f"\n{'='*60}")
        print(f"格栅标定工具")
        print(f"{'='*60}")

        # 加载图片
        self.original_img = cv2.imread(image_path)
        if self.original_img is None:
            raise ValueError(f"无法加载图片: {image_path}")

        h, w = self.original_img.shape[:2]
        print(f"图片尺寸: {w} x {h}")

        # 调整显示尺寸
        max_width, max_height = 1200, 800
        if w > max_width or h > max_height:
            scale = min(max_width/w, max_height/h)
            display_w, display_h = int(w*scale), int(h*scale)
            self.img_display = cv2.resize(self.original_img, (display_w, display_h))
            self.scale_factor = scale
            print(f"显示尺寸: {display_w} x {display_h} (缩放比例: {scale:.2f})")
        else:
            self.img_display = self.original_img.copy()
            self.scale_factor = 1.0
            print("显示原始尺寸")

        self.points = []

        print(f"\n=== 标定说明 ===")
        print(f"请按顺序点击格栅区域的4个内角点:")
        print(f"1. 左上角 (Top-Left)")
        print(f"2. 右上角 (Top-Right)")
        print(f"3. 右下角 (Bottom-Right)")
        print(f"4. 左下角 (Bottom-Left)")
        print(f"")
        print(f"操作提示:")
        print(f"- 点击: 标记角点")
        print(f"- 按 'r': 重置重新标记")
        print(f"- 按任意键: 完成标定")
        print(f"{'='*60}")

        # 设置窗口和回调
        cv2.namedWindow("Grid Calibration", cv2.WINDOW_NORMAL)
        cv2.setMouseCallback("Grid Calibration", self._mouse_callback)
        cv2.imshow("Grid Calibration", self.img_display)

        # 交互循环
        while True:
            key = cv2.waitKey(1) & 0xFF

            if key == ord('r'):  # 重置
                print("\n重置标定点...")
                self.points = []
                if self.scale_factor != 1.0:
                    self.img_display = cv2.resize(self.original_img,
                                                (self.img_display.shape[1], self.img_display.shape[0]))
                else:
                    self.img_display = self.original_img.copy()
                cv2.imshow("Grid Calibration", self.img_display)

            elif len(self.points) == 4 and key != 255:  # 4个点标记完成且按了任意键
                break

        cv2.destroyAllWindows()

        if len(self.points) != 4:
            raise ValueError("标定未完成，需要4个角点")

        # 如果图片被缩放了，需要将坐标还原到原始尺寸
        if self.scale_factor != 1.0:
            self.points = [[int(x/self.scale_factor), int(y/self.scale_factor)]
                          for x, y in self.points]
            print(f"\n坐标已还原到原图尺寸: {self.points}")

        # 保存标定结果
        config_data = {
            'source_image': image_path,
            'calibration_method': 'interactive',
            'calibration_points': self.points,
            'grid_shape': [rows, cols],
            'image_size': [w, h],
            'target_size': [640, 640],  # 矫正后的标准尺寸
            'structure_threshold': 5.0,
            'roi_padding_ratio': 0.15  # ROI内缩比例
        }

        return config_data

    def save_config(self, config_data: dict, output_path: str):
        """保存配置文件"""
        Path(output_path).parent.mkdir(exist_ok=True)

        # 保存YAML格式
        if output_path.endswith('.yaml') or output_path.endswith('.yml'):
            with open(output_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, default_flow_style=False,
                         allow_unicode=True, sort_keys=False)
        else:
            # 保存JSON格式
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 标定配置已保存: {output_path}")
        print(f"   格栅形状: {config_data['grid_shape'][0]}行 x {config_data['grid_shape'][1]}列")
        print(f"   角点坐标: {config_data['calibration_points']}")


def main():
    parser = argparse.ArgumentParser(description="交互式格栅标定工具")
    parser.add_argument("image_path", help="格栅图片路径")
    parser.add_argument("--rows", type=int, default=8, help="格栅行数")
    parser.add_argument("--cols", type=int, default=8, help="格栅列数")
    parser.add_argument("--output", default="config/grid_calibrated.yaml",
                       help="输出配置文件路径")

    args = parser.parse_args()

    try:
        calibrator = GridCalibrator()
        config = calibrator.calibrate(args.image_path, args.rows, args.cols)
        calibrator.save_config(config, args.output)

        print(f"\n🎉 标定完成！")
        print(f"现在可以运行检测器: python tools/visual_grid_detector.py {args.image_path} --config {args.output}")

    except Exception as e:
        print(f"❌ 标定失败: {e}")


if __name__ == "__main__":
    main()