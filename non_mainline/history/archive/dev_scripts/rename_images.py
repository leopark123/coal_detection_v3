#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
图片重命名工具 - 解决中文文件名问题
"""

import os
import shutil
from pathlib import Path
import time

def rename_chinese_files():
    """重命名中文文件名为英文"""

    test_dirs = [
        "tests/test_images",
        "tests/test_images/normal",
        "tests/test_images/coal_light",
        "tests/test_images/coal_heavy",
        "tests/test_images/edge_cases",
        "tests/test_images/lighting"
    ]

    print("=" * 50)
    print("  重命名中文文件名")
    print("=" * 50)

    renamed_count = 0

    for test_dir in test_dirs:
        dir_path = Path(test_dir)
        if not dir_path.exists():
            continue

        # 查找所有图片文件
        for pattern in ["*.png", "*.jpg", "*.jpeg", "*.bmp"]:
            for img_file in dir_path.glob(pattern):
                file_name = img_file.name

                # 检查是否包含中文字符
                if any('\u4e00' <= char <= '\u9fff' for char in file_name):
                    # 生成新的英文文件名
                    timestamp = int(time.time())
                    extension = img_file.suffix

                    # 根据目录确定前缀
                    dir_name = img_file.parent.name
                    if dir_name == "normal":
                        prefix = "normal_"
                    elif dir_name == "coal_light":
                        prefix = "coal_light_"
                    elif dir_name == "coal_heavy":
                        prefix = "coal_heavy_"
                    elif dir_name == "edge_cases":
                        prefix = "edge_case_"
                    elif dir_name == "lighting":
                        prefix = "lighting_"
                    else:
                        prefix = "image_"

                    new_name = f"{prefix}{timestamp}{extension}"
                    new_path = img_file.parent / new_name

                    try:
                        img_file.rename(new_path)
                        print(f"[RENAMED] {file_name} -> {new_name}")
                        renamed_count += 1
                    except Exception as e:
                        print(f"[ERROR] 重命名失败 {file_name}: {e}")

    print(f"\n[TOTAL] 重命名了 {renamed_count} 个文件")
    return renamed_count

def organize_images():
    """整理图片到正确目录"""

    print("\n" + "=" * 50)
    print("  整理图片到正确目录")
    print("=" * 50)

    # 检查是否有图片放错了位置
    base_dir = Path("tests/test_images")

    # 扫描根目录下的图片，询问用户分类
    root_images = []
    for pattern in ["*.png", "*.jpg", "*.jpeg", "*.bmp"]:
        root_images.extend(base_dir.glob(pattern))

    if root_images:
        print(f"[INFO] 在根目录发现 {len(root_images)} 张图片:")
        for img in root_images:
            if img.name != "sample_image.png":  # 跳过基准图片
                print(f"  - {img.name}")

def main():
    """主函数"""

    # 重命名中文文件
    renamed_count = rename_chinese_files()

    # 整理图片位置
    organize_images()

    if renamed_count > 0:
        print(f"\n" + "=" * 50)
        print("重命名完成！请重启检测服务:")
        print("python start_device1_detection.py --images tests/test_images")
        print("=" * 50)

if __name__ == "__main__":
    main()