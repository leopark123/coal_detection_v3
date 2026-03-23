#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简化版单格栅检测测试
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config.config import Config
from drivers.factory import create_camera
from algo.single_grid_detector import SingleGridDetector

def simple_test():
    """简单的功能测试"""
    print("=" * 50)
    print("单格栅检测功能测试")
    print("=" * 50)

    # 设置环境
    os.environ['COAL_ENV'] = 'DEV'
    os.environ['USE_REAL_GRID_IN_DEV'] = 'True'
    os.environ['MOCK_SOURCE_DIR'] = 'tests/sample_only'

    # 初始化配置
    config = Config()
    config.USE_REAL_GRID_IN_DEV = True
    config.MOCK_SOURCE_DIR = 'tests/sample_only'
    config.DEV_FRAME_WIDTH = 462
    config.DEV_FRAME_HEIGHT = 603

    print(f"[INFO] 配置: {config.frame_width} x {config.frame_height}")

    # 创建相机
    try:
        camera = create_camera(config)
        print(f"[INFO] 相机初始化成功: {type(camera).__name__}")
    except Exception as e:
        print(f"[ERROR] 相机初始化失败: {e}")
        return False

    # 测试格栅0
    try:
        detector = SingleGridDetector(config, 0)
        print(f"[SUCCESS] 格栅0检测器创建成功")
        print(f"[INFO] 总格栅数: {detector.original_grid_count}")
        print(f"[INFO] 目标格栅ROI: {detector.grid_rois[0]}")

        # 进行5次检测
        for i in range(5):
            frame = camera.grab()
            result = detector.detect_single_grid(frame, i)

            status = "积煤" if result.has_coal else "正常"
            print(f"  帧{i+1}: {status} | {result.confidence} | {result.process_time_ms:.1f}ms")

        stats = detector.get_statistics()
        print(f"[STATS] 检测统计: {stats}")

        return True

    except Exception as e:
        print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("开始单格栅检测测试...")
    success = simple_test()

    if success:
        print("\n[SUCCESS] 测试成功! 可以启动Web界面")
        print("运行: python start_single_grid_test.py")
    else:
        print("\n[ERROR] 测试失败，请检查配置")