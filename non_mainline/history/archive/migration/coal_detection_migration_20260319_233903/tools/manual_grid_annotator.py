"""
格栅口手动标注工具
交互式标记格栅口的正确位置
"""

import cv2
import numpy as np
import yaml
import json
from pathlib import Path
from typing import List, Tuple
import argparse


class GridAnnotator:
    """格栅口手动标注工具"""

    def __init__(self, image_path: str, grid_size: int = 30):
        """
        初始化标注工具

        Args:
            image_path: 图片路径
            grid_size: 格栅口标记大小
        """
        self.image_path = image_path
        self.original_image = cv2.imread(image_path)

        if self.original_image is None:
            raise ValueError(f"无法加载图片: {image_path}")

        self.display_image = self.original_image.copy()
        self.grid_size = grid_size
        self.grids = []  # 格栅口列表: [(x, y, w, h), ...]

        # 显示参数
        self.window_name = "格栅口标注工具 - 点击标记格栅口位置"
        self.scale_factor = 1.0

        # 调整显示尺寸
        self._adjust_display_size()

        print("\n=== 格栅口标注工具 ===")
        print(f"图片路径: {image_path}")
        print(f"图片尺寸: {self.original_image.shape[1]} x {self.original_image.shape[0]}")
        print("\n操作说明:")
        print("- 左键点击: 标记格栅口位置")
        print("- 右键点击: 删除最近的格栅口标记")
        print("- 按键 's': 保存标注结果")
        print("- 按键 'r': 重置所有标注")
        print("- 按键 'q': 退出工具")
        print("- 按键 '+'/'-': 调整格栅口大小")
        print("="*50)

    def _adjust_display_size(self):
        """调整显示尺寸以适应屏幕"""
        h, w = self.original_image.shape[:2]

        # 最大显示尺寸
        max_width = 1200
        max_height = 800

        if w > max_width or h > max_height:
            scale_w = max_width / w
            scale_h = max_height / h
            self.scale_factor = min(scale_w, scale_h)

            new_w = int(w * self.scale_factor)
            new_h = int(h * self.scale_factor)

            self.display_image = cv2.resize(self.original_image, (new_w, new_h))
            print(f"显示尺寸已缩放到: {new_w} x {new_h} (缩放比例: {self.scale_factor:.2f})")

    def _screen_to_image_coords(self, x: int, y: int) -> Tuple[int, int]:
        """将屏幕坐标转换为原图坐标"""
        orig_x = int(x / self.scale_factor)
        orig_y = int(y / self.scale_factor)
        return orig_x, orig_y

    def _image_to_screen_coords(self, x: int, y: int) -> Tuple[int, int]:
        """将原图坐标转换为屏幕坐标"""
        screen_x = int(x * self.scale_factor)
        screen_y = int(y * self.scale_factor)
        return screen_x, screen_y

    def _mouse_callback(self, event, x, y, flags, param):
        """鼠标回调函数"""
        if event == cv2.EVENT_LBUTTONDOWN:
            # 左键点击 - 添加格栅口
            self._add_grid(x, y)

        elif event == cv2.EVENT_RBUTTONDOWN:
            # 右键点击 - 删除最近的格栅口
            self._remove_nearest_grid(x, y)

        self._update_display()

    def _add_grid(self, screen_x: int, screen_y: int):
        """添加格栅口标记"""
        # 转换为原图坐标
        orig_x, orig_y = self._screen_to_image_coords(screen_x, screen_y)

        # 计算格栅口区域
        grid_w = int(self.grid_size / self.scale_factor)
        grid_h = int(self.grid_size / self.scale_factor)

        x = orig_x - grid_w // 2
        y = orig_y - grid_h // 2

        # 确保坐标在图像范围内
        h, w = self.original_image.shape[:2]
        x = max(0, min(x, w - grid_w))
        y = max(0, min(y, h - grid_h))

        self.grids.append((x, y, grid_w, grid_h))
        print(f"添加格栅口 #{len(self.grids)}: ({x}, {y}, {grid_w}, {grid_h})")

    def _remove_nearest_grid(self, screen_x: int, screen_y: int):
        """删除最近的格栅口标记"""
        if not self.grids:
            return

        orig_x, orig_y = self._screen_to_image_coords(screen_x, screen_y)

        # 找到最近的格栅口
        min_dist = float('inf')
        nearest_idx = -1

        for i, (gx, gy, gw, gh) in enumerate(self.grids):
            center_x = gx + gw // 2
            center_y = gy + gh // 2
            dist = ((orig_x - center_x) ** 2 + (orig_y - center_y) ** 2) ** 0.5

            if dist < min_dist:
                min_dist = dist
                nearest_idx = i

        if nearest_idx >= 0:
            removed = self.grids.pop(nearest_idx)
            print(f"删除格栅口 #{nearest_idx + 1}: {removed}")

    def _update_display(self):
        """更新显示图像"""
        # 重置显示图像
        self.display_image = cv2.resize(self.original_image,
                                      (self.display_image.shape[1], self.display_image.shape[0]))

        # 绘制格栅口标记
        for i, (x, y, w, h) in enumerate(self.grids):
            # 转换为显示坐标
            screen_x, screen_y = self._image_to_screen_coords(x, y)
            screen_w = int(w * self.scale_factor)
            screen_h = int(h * self.scale_factor)

            # 绘制矩形框
            cv2.rectangle(self.display_image,
                         (screen_x, screen_y),
                         (screen_x + screen_w, screen_y + screen_h),
                         (0, 255, 0), 2)

            # 绘制编号
            center_x = screen_x + screen_w // 2
            center_y = screen_y + screen_h // 2

            cv2.putText(self.display_image,
                       str(i + 1),
                       (center_x - 10, center_y + 5),
                       cv2.FONT_HERSHEY_SIMPLEX,
                       0.6, (255, 255, 255), 2)

            cv2.putText(self.display_image,
                       str(i + 1),
                       (center_x - 10, center_y + 5),
                       cv2.FONT_HERSHEY_SIMPLEX,
                       0.6, (0, 0, 255), 1)

        # 显示统计信息
        info_text = f"格栅口数量: {len(self.grids)} | 格栅口大小: {self.grid_size}px | 按 's' 保存"
        cv2.putText(self.display_image, info_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(self.display_image, info_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 1)

        cv2.imshow(self.window_name, self.display_image)

    def _save_config(self, output_path: str = "config/grid_manual.yaml"):
        """保存标注配置"""
        if not self.grids:
            print("没有标注数据可保存")
            return

        config_data = {
            'source_image': self.image_path,
            'annotation_method': 'manual',
            'grid_rois': [
                {'id': i + 1, 'x': x, 'y': y, 'w': w, 'h': h}
                for i, (x, y, w, h) in enumerate(self.grids)
            ],
            'total_grids': len(self.grids)
        }

        # 确保目录存在
        Path(output_path).parent.mkdir(exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, default_flow_style=False,
                     allow_unicode=True, sort_keys=False)

        print(f"✅ 标注配置已保存到: {output_path}")
        print(f"   共保存 {len(self.grids)} 个格栅口")

        # 也保存一份 JSON 格式
        json_path = output_path.replace('.yaml', '.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        print(f"   同时保存 JSON 格式到: {json_path}")

    def _reset_annotations(self):
        """重置所有标注"""
        self.grids.clear()
        print("🔄 已重置所有标注")
        self._update_display()

    def _adjust_grid_size(self, delta: int):
        """调整格栅口大小"""
        self.grid_size = max(10, min(100, self.grid_size + delta))
        print(f"📏 格栅口大小调整为: {self.grid_size}px")
        self._update_display()

    def run(self):
        """运行标注工具"""
        cv2.namedWindow(self.window_name, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)

        # 显示初始图像
        self._update_display()

        while True:
            key = cv2.waitKey(1) & 0xFF

            if key == ord('q'):  # 退出
                break
            elif key == ord('s'):  # 保存
                self._save_config()
            elif key == ord('r'):  # 重置
                self._reset_annotations()
            elif key == ord('+') or key == ord('='):  # 增大格栅口
                self._adjust_grid_size(5)
            elif key == ord('-'):  # 减小格栅口
                self._adjust_grid_size(-5)

        cv2.destroyAllWindows()
        return len(self.grids) > 0


def main():
    parser = argparse.ArgumentParser(description="格栅口手动标注工具")
    parser.add_argument("image_path", help="格栅图片路径")
    parser.add_argument("--grid-size", type=int, default=30, help="格栅口标记大小 (默认: 30)")
    parser.add_argument("--output", default="config/grid_manual.yaml", help="输出配置文件路径")

    args = parser.parse_args()

    try:
        annotator = GridAnnotator(args.image_path, args.grid_size)
        success = annotator.run()

        if success:
            print("\n✅ 标注完成！")
            print("现在可以使用新的格栅配置重启检测系统")
        else:
            print("\n❌ 未保存任何标注")

    except Exception as e:
        print(f"❌ 错误: {e}")


if __name__ == "__main__":
    main()