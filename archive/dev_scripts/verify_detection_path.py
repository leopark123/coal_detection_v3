#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
验证系统检测图片路径
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config.config import Config
from drivers.factory import create_camera

def verify_detection_path():
    """验证当前检测的图片路径"""
    print("=" * 60)
    print("  验证检测图片路径")
    print("=" * 60)

    # 设置环境变量（模拟 start_web_sample_only.py）
    os.environ['COAL_ENV'] = 'DEV'
    os.environ['USE_REAL_GRID_IN_DEV'] = 'True'
    os.environ['MOCK_SOURCE_DIR'] = 'tests/sample_only'

    # 初始化配置
    config = Config()
    config.USE_REAL_GRID_IN_DEV = True

    # 检查环境变量
    mock_source = os.getenv('MOCK_SOURCE_DIR')
    if mock_source:
        config.MOCK_SOURCE_DIR = mock_source
        print(f"[INFO] 环境变量MOCK_SOURCE_DIR: {mock_source}")
    else:
        print(f"[INFO] 默认MOCK_SOURCE_DIR: {config.MOCK_SOURCE_DIR}")

    # 创建相机并检查图片
    camera = create_camera(config)

    if hasattr(camera, 'source_dir'):
        print(f"[INFO] MockCamera源目录: {camera.source_dir}")

        # 列出所有图片文件
        if camera.source_dir.exists():
            images = list(camera.source_dir.glob("*.png")) + list(camera.source_dir.glob("*.jpg"))
            print(f"[INFO] 找到图片文件: {len(images)}个")
            for img in images:
                print(f"  - {img.name}")

            # 测试抓取一帧
            try:
                frame = camera.grab()
                if frame is not None:
                    print(f"[SUCCESS] 成功抓取图片: {frame.shape}")

                    # 检查当前读取的文件
                    if hasattr(camera, 'files') and hasattr(camera, 'idx'):
                        current_file = camera.files[camera.idx - 1] if camera.idx > 0 else camera.files[-1]
                        print(f"[INFO] 当前读取文件: {current_file}")
                else:
                    print("[ERROR] 抓取图片失败")
            except Exception as e:
                print(f"[ERROR] 抓取图片异常: {e}")
        else:
            print(f"[ERROR] 源目录不存在: {camera.source_dir}")
    else:
        print("[WARNING] 相机不是MockCamera类型")

    print("=" * 60)

if __name__ == "__main__":
    verify_detection_path()