#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置系统专门检测标注的sample_image.png
"""

import shutil
import os
from pathlib import Path


def setup_single_image_detection():
    """
    配置MockCamera专门检测标注的sample_image.png
    """
    print("=" * 60)
    print("  配置专门检测标注图片")
    print("=" * 60)

    # 源图片路径
    source_image = "GridEditorToolKit_v1.0.0_20260119_092150/samples/sample_image.png"

    # 目标目录（创建专门的目录）
    target_dir = Path("tests/sample_only")
    target_image = target_dir / "sample_image.png"

    # 创建专门的目录
    target_dir.mkdir(exist_ok=True)

    # 清空目录（只保留我们要的图片）
    for file in target_dir.glob("*"):
        if file.is_file():
            file.unlink()

    # 复制标注图片
    if Path(source_image).exists():
        shutil.copy(source_image, target_image)
        print(f"[SUCCESS] 已复制标注图片: {target_image}")
    else:
        print(f"[ERROR] 源图片不存在: {source_image}")
        return False

    # 验证图片
    import cv2
    image = cv2.imread(str(target_image))
    if image is not None:
        print(f"[SUCCESS] 图片验证成功: {image.shape}")
    else:
        print(f"[ERROR] 图片验证失败")
        return False

    print(f"[INFO] MockCamera现在将只读取这一张标注图片")
    print(f"[INFO] 图片路径: {target_image}")

    return str(target_dir)


def update_config_for_single_image():
    """
    更新配置文件指向新的图片目录
    """
    print("\n[INFO] 配置更新建议:")
    print("方案1: 修改MOCK_SOURCE_DIR为'tests/sample_only'")
    print("方案2: 重启Web服务时设置环境变量")

    return "tests/sample_only"


if __name__ == "__main__":
    target_dir = setup_single_image_detection()
    if target_dir:
        new_dir = update_config_for_single_image()
        print(f"\n[NEXT] 重启Web服务:")
        print(f"python start_web_sample_only.py")
        print("=" * 60)
    else:
        print("[ERROR] 配置失败")