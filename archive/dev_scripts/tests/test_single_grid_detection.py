#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
单格栅检测功能测试

验证单格栅检测器的功能和性能
"""

import os
import sys
import time
import cv2
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config.config import Config
from drivers.factory import create_camera
from algo.single_grid_detector import SingleGridDetector


def _run_single_grid_detection_test() -> bool:
    """执行单格栅检测功能测试并返回是否通过。"""
    print("=" * 60)
    print("  单格栅检测功能测试")
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

    print(f"[INFO] 配置完成: {config.frame_width} x {config.frame_height}")

    # 创建相机
    try:
        camera = create_camera(config)
        print(f"[INFO] 相机初始化成功: {type(camera).__name__}")
    except Exception as e:
        print(f"[ERROR] 相机初始化失败: {e}")
        return False

    # 测试不同格栅ID
    test_grid_ids = [0, 5, 10, 20, 50]  # 测试几个不同的格栅

    for grid_id in test_grid_ids:
        print(f"\n{'='*20} 测试格栅 {grid_id} {'='*20}")

        try:
            # 创建单格栅检测器
            detector = SingleGridDetector(config, grid_id)
            print(f"[SUCCESS] 格栅 {grid_id} 检测器创建成功")

            # 获取格栅ROI信息
            roi = detector.grid_rois[0]
            print(f"[INFO] 格栅ROI: x={roi[0]}, y={roi[1]}, w={roi[2]}, h={roi[3]}")

            # 进行多次检测测试
            detection_results = []
            detection_times = []

            for i in range(10):  # 检测10帧
                frame = camera.grab()

                start_time = time.perf_counter()
                result = detector.detect_single_grid(frame, i)
                end_time = time.perf_counter()

                process_time = (end_time - start_time) * 1000
                detection_times.append(process_time)
                detection_results.append(result.has_coal)

                print(f"  帧{i+1}: {'积煤' if result.has_coal else '正常'} | "
                      f"{result.confidence} | {result.process_time_ms:.1f}ms")

            # 统计结果
            avg_time = sum(detection_times) / len(detection_times)
            coal_count = sum(detection_results)
            coal_rate = coal_count / len(detection_results)

            print(f"[STATS] 格栅 {grid_id} 测试结果:")
            print(f"  - 平均处理时间: {avg_time:.1f}ms")
            print(f"  - 积煤检测次数: {coal_count}/{len(detection_results)}")
            print(f"  - 积煤检测率: {coal_rate:.1%}")

            # 保存可视化结果
            if i >= 0:  # 保存最后一帧的可视化结果
                vis_frame = detector.visualize_single_grid(frame, result)
                output_path = f"logs/single_grid_test_grid_{grid_id}.jpg"
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                cv2.imwrite(output_path, vis_frame)
                print(f"[INFO] 可视化结果已保存: {output_path}")

            # 获取检测器统计
            stats = detector.get_statistics()
            print(f"[DETECTOR_STATS] {stats}")

        except Exception as e:
            print(f"[ERROR] 格栅 {grid_id} 测试失败: {e}")

    print(f"\n{'='*60}")
    print("测试完成")
    print("="*60)

    return True


def test_single_grid_detection():
    """pytest 入口。"""
    assert _run_single_grid_detection_test()

def benchmark_performance():
    """性能基准测试"""
    print("\n" + "="*60)
    print("  性能基准测试")
    print("="*60)

    # 设置环境
    os.environ['COAL_ENV'] = 'DEV'
    os.environ['USE_REAL_GRID_IN_DEV'] = 'True'
    os.environ['MOCK_SOURCE_DIR'] = 'tests/sample_only'

    config = Config()
    config.USE_REAL_GRID_IN_DEV = True
    config.MOCK_SOURCE_DIR = 'tests/sample_only'

    camera = create_camera(config)
    detector = SingleGridDetector(config, 0)  # 使用格栅0进行基准测试

    # 预热
    for i in range(5):
        frame = camera.grab()
        detector.detect_single_grid(frame, i)

    print("[INFO] 预热完成，开始基准测试...")

    # 基准测试
    test_frames = 100
    start_time = time.perf_counter()

    detection_times = []
    for i in range(test_frames):
        frame = camera.grab()

        frame_start = time.perf_counter()
        result = detector.detect_single_grid(frame, i)
        frame_end = time.perf_counter()

        detection_times.append((frame_end - frame_start) * 1000)

    total_time = time.perf_counter() - start_time

    # 统计结果
    avg_time = sum(detection_times) / len(detection_times)
    min_time = min(detection_times)
    max_time = max(detection_times)
    fps = test_frames / total_time

    print(f"[BENCHMARK] 性能测试结果 ({test_frames} 帧):")
    print(f"  - 总耗时: {total_time:.2f}s")
    print(f"  - 平均处理时间: {avg_time:.1f}ms")
    print(f"  - 最短处理时间: {min_time:.1f}ms")
    print(f"  - 最长处理时间: {max_time:.1f}ms")
    print(f"  - 处理帧率: {fps:.1f} FPS")

    # 性能评估
    target_time = 50  # 目标处理时间50ms
    if avg_time <= target_time:
        print(f"[PASS] 平均处理时间达标 ({avg_time:.1f}ms <= {target_time}ms)")
    else:
        print(f"❌ [FAIL] 平均处理时间超标 ({avg_time:.1f}ms > {target_time}ms)")

    return avg_time <= target_time

if __name__ == "__main__":
    print("单格栅检测系统测试")
    print("阶段1: 功能验证与性能测试")

    # 功能测试
    success = _run_single_grid_detection_test()

    if success:
        # 性能测试
        performance_ok = benchmark_performance()

        print(f"\n🎉 测试总结:")
        print(f"✅ 功能测试: {'通过' if success else '失败'}")
        print(f"✅ 性能测试: {'通过' if performance_ok else '失败'}")

        if success and performance_ok:
            print(f"\n🚀 单格栅检测系统就绪！")
            print(f"现在可以启动Web界面进行验证:")
            print(f"python start_single_grid_test.py [grid_id]")
        else:
            print(f"\n⚠️ 需要进一步调优参数")
    else:
        print(f"\n❌ 基础功能测试失败，请检查配置")
