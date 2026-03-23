#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试图片管理工具

帮助用户添加和管理不同形态的测试图片
"""

import os
import shutil
from pathlib import Path

def setup_test_directories():
    """设置测试图片目录结构"""

    directories = {
        "tests/test_images": "多种测试图片（推荐添加新图片到这里）",
        "tests/test_images/normal": "正常状态图片（无积煤或轻微积煤）",
        "tests/test_images/coal_light": "轻度积煤图片",
        "tests/test_images/coal_heavy": "重度积煤图片",
        "tests/test_images/edge_cases": "边缘情况（阴影、锈斑、异物等）",
        "tests/test_images/lighting": "不同光照条件"
    }

    print("=" * 60)
    print("  创建测试图片目录结构")
    print("=" * 60)

    for dir_path, description in directories.items():
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        print(f"[INFO] 创建目录: {dir_path}")
        print(f"       用途: {description}")

    # 复制现有的标注图片作为基准
    base_image = Path("tests/sample_only/sample_image.png")
    if base_image.exists():
        target = Path("tests/test_images/sample_image.png")
        shutil.copy(base_image, target)
        print(f"[INFO] 复制基准图片: {target}")

    return directories

def list_test_images():
    """列出所有测试图片"""

    test_dirs = [
        "tests/sample_only",
        "tests/test_images",
        "tests/test_images/normal",
        "tests/test_images/coal_light",
        "tests/test_images/coal_heavy",
        "tests/test_images/edge_cases",
        "tests/test_images/lighting"
    ]

    print("=" * 60)
    print("  当前测试图片统计")
    print("=" * 60)

    total_images = 0

    for test_dir in test_dirs:
        dir_path = Path(test_dir)
        if not dir_path.exists():
            continue

        images = []
        for ext in ["*.png", "*.jpg", "*.jpeg", "*.bmp"]:
            images.extend(dir_path.glob(ext))

        if images:
            print(f"\n[{test_dir}] - {len(images)} 张图片:")
            for img in sorted(images):
                size_mb = img.stat().st_size / (1024 * 1024)
                print(f"  - {img.name} ({size_mb:.2f}MB)")
                total_images += 1
        else:
            print(f"\n[{test_dir}] - 空目录")

    print(f"\n[TOTAL] 总计: {total_images} 张测试图片")
    return total_images

def create_image_config():
    """创建图片配置文件"""

    config_content = """# 测试图片配置说明

## 添加新测试图片的步骤：

### 1. 将图片复制到对应目录：
- tests/test_images/              # 通用测试图片
- tests/test_images/normal/       # 正常状态（无积煤）
- tests/test_images/coal_light/   # 轻度积煤
- tests/test_images/coal_heavy/   # 重度积煤
- tests/test_images/edge_cases/   # 边缘情况
- tests/test_images/lighting/     # 不同光照

### 2. 支持的图片格式：
- .png (推荐)
- .jpg/.jpeg
- .bmp

### 3. 图片要求：
- 分辨率: 建议与标注图片一致 (462x603)
- 包含: 125个格栅口的完整图像
- 质量: 清晰，对比度适中

### 4. 启动检测：
```bash
# 使用多图片模式（循环检测所有图片）
python start_device1_detection.py --images tests/test_images

# 使用单图片模式（只检测标注图片）
python start_device1_detection.py --images tests/sample_only
```

### 5. 图片分类建议：

#### normal/ (正常状态)
- 无积煤或极少积煤
- 格栅清洁可见
- 光照良好

#### coal_light/ (轻度积煤)
- 少量格栅有积煤 (< 5%)
- 积煤厚度较薄
- 大部分格栅仍可见

#### coal_heavy/ (重度积煤)
- 大量格栅有积煤 (> 10%)
- 积煤厚度较厚
- 部分格栅完全被遮挡

#### edge_cases/ (边缘情况)
- 阴影干扰
- 锈斑、污渍
- 异物遮挡
- 部分设备故障

#### lighting/ (不同光照)
- 强光照射
- 光照不足
- 不均匀照明
- 阴天/晴天差异

### 6. 测试流程：
1. 添加新图片到对应目录
2. 运行: python manage_test_images.py --list
3. 启动检测: python start_device1_detection.py --images tests/test_images
4. 观察检测效果，记录准确率
5. 根据结果调整检测参数
"""

    config_file = Path("tests/TEST_IMAGES_GUIDE.md")
    with open(config_file, 'w', encoding='utf-8') as f:
        f.write(config_content)

    print(f"[INFO] 创建图片配置指南: {config_file}")

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="测试图片管理工具")
    parser.add_argument("--setup", action="store_true", help="创建测试目录结构")
    parser.add_argument("--list", action="store_true", help="列出所有测试图片")
    parser.add_argument("--guide", action="store_true", help="创建使用指南")

    args = parser.parse_args()

    if args.setup:
        setup_test_directories()
        create_image_config()
    elif args.list:
        list_test_images()
    elif args.guide:
        create_image_config()
    else:
        # 默认执行所有操作
        setup_test_directories()
        list_test_images()
        create_image_config()

        print("\n" + "=" * 60)
        print("测试图片管理完成！")
        print("=" * 60)
        print()
        print("📁 添加新图片到：tests/test_images/")
        print("📖 查看完整指南：tests/TEST_IMAGES_GUIDE.md")
        print("🔍 列出图片：python manage_test_images.py --list")
        print("🚀 启动检测：python start_device1_detection.py --images tests/test_images")

if __name__ == "__main__":
    main()