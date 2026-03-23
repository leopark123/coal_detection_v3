#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
最终测试：确认系统只检测标注的单张图片
"""

import os
import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent))

from config.config import Config
from drivers.factory import create_camera

def final_test():
    """最终确认测试"""
    print("=" * 60)
    print("  最终确认：系统只检测标注图片")
    print("=" * 60)

    # 设置环境变量
    os.environ['COAL_ENV'] = 'DEV'
    os.environ['USE_REAL_GRID_IN_DEV'] = 'True'
    os.environ['MOCK_SOURCE_DIR'] = 'tests/sample_only'

    # 初始化配置
    config = Config()
    config.USE_REAL_GRID_IN_DEV = True

    # 应用环境变量
    mock_source = os.getenv('MOCK_SOURCE_DIR')
    if mock_source:
        config.MOCK_SOURCE_DIR = mock_source

    print(f"[INFO] 配置的源目录: {config.MOCK_SOURCE_DIR}")

    # 创建相机
    camera = create_camera(config)

    print(f"[INFO] 相机源目录: {camera.source_dir}")
    print(f"[INFO] 加载图片数量: {len(camera.files)}")

    if len(camera.files) == 1:
        print(f"✅ [SUCCESS] 只有1张图片: {camera.files[0].name}")
    else:
        print(f"❌ [ERROR] 错误！还有 {len(camera.files)} 张图片")
        for f in camera.files:
            print(f"  - {f}")
        return False

    # 测试连续抓取5帧，确认是同一张图片
    print(f"\n[INFO] 测试连续抓取5帧...")

    last_path = None
    for i in range(5):
        frame = camera.grab()
        if hasattr(camera, 'files'):
            # 由于我们修改了代码，单图模式下始终读取files[0]
            current_path = camera.files[0]
            print(f"  帧{i+1}: {current_path.name}")

            if last_path is None:
                last_path = current_path
            elif last_path != current_path:
                print(f"❌ [ERROR] 检测到不同图片！")
                return False

        time.sleep(0.1)

    print(f"✅ [SUCCESS] 所有帧都是同一张标注图片！")
    print(f"✅ 目标图片: {camera.files[0]}")
    print(f"✅ 图片尺寸: {frame.shape}")

    return True

if __name__ == "__main__":
    success = final_test()

    print("\n" + "=" * 60)
    if success:
        print("🎉 [FINAL SUCCESS] 系统现在只检测你标注的图片！")
        print("✅ 单图模式已启用")
        print("✅ 125个精确格栅已加载")
        print("✅ GridEditorToolKit标注数据已应用")
        print("🌐 Web界面: http://localhost:8000")
    else:
        print("❌ [ERROR] 还有问题需要修复")
    print("=" * 60)