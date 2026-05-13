#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试设备1检测功能

验证125个格栅口的完整检测
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config.config import Config
from drivers.factory import create_camera
from algo.device_detector import DeviceDetector


def _run_device1_detection_test() -> bool:
    """执行设备1的125个格栅口检测测试并返回是否通过。"""
    print("=" * 60)
    print("  设备1检测功能测试")
    print("=" * 60)

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

    # 创建设备1检测器
    try:
        detector = DeviceDetector(config, device_id="device-1", grid_count=125)
        print(f"[SUCCESS] 设备1检测器创建成功")
        print(f"[INFO] 设备ID: {detector.device_id}")
        print(f"[INFO] 格栅口数量: {len(detector.device_grids)}")

    except Exception as e:
        print(f"[ERROR] 检测器创建失败: {e}")
        return False

    # 进行设备级检测测试
    print(f"\n{'='*20} 设备级检测测试 {'='*20}")

    detection_results = []
    detection_times = []

    for i in range(5):  # 检测5帧
        frame = camera.grab()

        start_time = time.perf_counter()
        result = detector.detect_device(frame, i)
        end_time = time.perf_counter()

        process_time = (end_time - start_time) * 1000
        detection_times.append(process_time)
        detection_results.append({
            'has_coal': result.device_has_coal,
            'alert_level': result.device_alert_level,
            'coal_grids': result.coal_grids,
            'visible_grids': result.visible_grids
        })

        print(f"  帧{i+1}: 积煤={result.coal_grids}/125格栅 | "
              f"可见={result.visible_grids}/125格栅 | "
              f"{result.device_alert_level} | {result.process_time_ms:.1f}ms")

    # 统计结果
    avg_time = sum(detection_times) / len(detection_times)
    coal_detections = sum(1 for r in detection_results if r['has_coal'])

    print(f"\n[STATS] 设备1检测结果:")
    print(f"  - 平均处理时间: {avg_time:.1f}ms")
    print(f"  - 目标时间: < 500ms (125个格栅)")
    print(f"  - 设备积煤检测: {coal_detections}/{len(detection_results)}次")

    # 性能评估
    target_time = 500  # 目标处理时间500ms
    if avg_time <= target_time:
        print(f"[PASS] 处理时间达标 ({avg_time:.1f}ms <= {target_time}ms)")
        performance_ok = True
    else:
        print(f"[FAIL] 处理时间超标 ({avg_time:.1f}ms > {target_time}ms)")
        performance_ok = False

    # 获取设备统计
    stats = detector.get_device_statistics()
    print(f"\n[DEVICE_STATS]:")
    print(f"  - 设备ID: {stats['device_id']}")
    print(f"  - 格栅数量: {stats['grid_count']}")
    print(f"  - 格栅范围: {stats['device_grid_range']}")
    print(f"  - 性能目标: {stats['performance_target']}")

    return performance_ok


def test_device1_detection():
    """pytest 入口。"""
    assert _run_device1_detection_test()

if __name__ == "__main__":
    print("设备1检测系统测试")
    print("125个格栅口完整检测验证")

    success = _run_device1_detection_test()

    print(f"\n" + "="*60)
    if success:
        print("[SUCCESS] 设备1检测系统测试通过!")
        print("可以启动Web界面进行实时检测:")
        print("python start_device1_detection.py")
        print("")
        print("特性:")
        print("- 检测125个格栅口状态")
        print("- 设备级积煤判断")
        print("- 实时状态监控")
        print("- 性能达标 (< 500ms)")
    else:
        print("[FAIL] 设备1检测系统需要优化")
        print("请检查配置和性能参数")

    print("="*60)
