#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config.config import Config
from drivers.factory import create_camera

# 设置环境变量
os.environ['COAL_ENV'] = 'DEV'
os.environ['MOCK_SOURCE_DIR'] = 'tests/sample_only'

config = Config()
config.MOCK_SOURCE_DIR = 'tests/sample_only'

camera = create_camera(config)

print("="*50)
print("检测图片验证结果:")
print(f"源目录: {camera.source_dir}")
print(f"图片数量: {len(camera.files)}")

if len(camera.files) == 1:
    print(f"图片路径: {camera.files[0]}")
    print("SUCCESS: 系统只检测一张标注图片!")
else:
    print("ERROR: 还有多张图片")

# 测试抓取
frame = camera.grab()
print(f"图片尺寸: {frame.shape}")
print("="*50)