#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查Web应用当前使用的相机配置
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# 模拟Web应用的启动过程
os.environ['COAL_ENV'] = 'DEV'
os.environ['USE_REAL_GRID_IN_DEV'] = 'True'
os.environ['MOCK_SOURCE_DIR'] = 'tests/sample_only'

from config.config import Config
from drivers.factory import create_camera

def check_web_camera_config():
    """检查Web应用相机配置"""
    print("=" * 60)
    print("  检查Web应用相机配置")
    print("=" * 60)

    # 模拟web/app.py中的startup函数
    config = Config()
    config.USE_REAL_GRID_IN_DEV = True

    # 检查环境变量MOCK_SOURCE_DIR (模拟web/app.py的逻辑)
    mock_source = os.getenv('MOCK_SOURCE_DIR')
    if mock_source:
        config.MOCK_SOURCE_DIR = mock_source
        print(f"[INFO] 使用环境变量指定的图片目录: {mock_source}")
        print(f"[INFO] 配置已更新，当前MOCK_SOURCE_DIR: {config.MOCK_SOURCE_DIR}")
    else:
        print(f"[WARNING] 未找到MOCK_SOURCE_DIR环境变量，使用默认: {config.MOCK_SOURCE_DIR}")

    # 设置为样本图片尺寸
    config.DEV_FRAME_WIDTH = 462
    config.DEV_FRAME_HEIGHT = 603

    print(f"[INFO] 帧尺寸配置: {config.frame_width} x {config.frame_height}")

    # 创建相机（模拟web/app.py）
    camera = create_camera(config)

    print(f"\n[DEBUG] 相机类型: {type(camera).__name__}")
    print(f"[DEBUG] 源目录: {camera.source_dir}")
    print(f"[DEBUG] 文件数量: {len(camera.files)}")
    print(f"[DEBUG] 文件列表:")
    for i, file in enumerate(camera.files):
        print(f"  {i}: {file}")
    print(f"[DEBUG] 当前索引: {camera.idx}")

    # 测试抓取几帧
    print(f"\n[TEST] 测试连续抓取3帧:")
    for i in range(3):
        frame = camera.grab()
        print(f"  帧{i+1}: 尺寸={frame.shape}, 当前索引={camera.idx}")

    return camera

if __name__ == "__main__":
    camera = check_web_camera_config()
    print("\n" + "=" * 60)
    print("检查完成")
    print("=" * 60)