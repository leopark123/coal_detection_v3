#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
性能测试和分析工具
按照CLAUDE.md规范测试检测系统性能
"""

import time
import cProfile
import pstats
import numpy as np
import cv2
from pathlib import Path
import sys
import os

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from algo.detector import CoalDetector
from config.config import Config

class PerformanceProfiler:
    """性能测试器"""

    def __init__(self):
        self.config = Config()

    def measure_detector_performance(self, iterations=50):
        """测量检测器性能"""
        print("=" * 60)
        print("    检测系统性能基线测量")
        print("=" * 60)

        try:
            # 初始化检测器
            print("正在初始化检测器...")
            detector = CoalDetector(self.config)

            # 生成测试图像
            print("生成测试图像...")
            test_image = self._generate_test_image()

            # 预热
            print("预热中...")
            for _ in range(5):
                detector.detect(test_image)

            # 性能测试
            print(f"开始性能测试 ({iterations}次迭代)...")
            times = []

            for i in range(iterations):
                t0 = time.perf_counter()
                result = detector.detect(test_image)
                elapsed = (time.perf_counter() - t0) * 1000  # ms
                times.append(elapsed)

                if i % 10 == 0:
                    print(f"  进度: {i}/{iterations}, 当前: {elapsed:.1f}ms")

            # 统计分析
            avg_time = sum(times) / len(times)
            max_time = max(times)
            min_time = min(times)
            p95_time = np.percentile(times, 95)

            print("=" * 60)
            print("    性能测试结果")
            print("=" * 60)
            print(f"平均延迟: {avg_time:.1f}ms")
            print(f"最小延迟: {min_time:.1f}ms")
            print(f"最大延迟: {max_time:.1f}ms")
            print(f"P95延迟:  {p95_time:.1f}ms")
            print()

            # 性能达标分析
            target_latency = 80  # ms (CLAUDE.md要求)
            if avg_time <= target_latency:
                print(f"[OK] 平均延迟达标 ({avg_time:.1f}ms <= {target_latency}ms)")
            else:
                print(f"[WARN] 平均延迟超标 ({avg_time:.1f}ms > {target_latency}ms)")
                print(f"       需要优化 {avg_time - target_latency:.1f}ms")

            if p95_time <= target_latency * 1.2:  # 允许P95有20%宽容度
                print(f"[OK] P95延迟可接受 ({p95_time:.1f}ms)")
            else:
                print(f"[WARN] P95延迟过高 ({p95_time:.1f}ms)")

            print("=" * 60)

            return {
                'avg': avg_time,
                'min': min_time,
                'max': max_time,
                'p95': p95_time,
                'times': times
            }

        except Exception as e:
            print(f"性能测试失败: {e}")
            return None

    def profile_detector_detailed(self):
        """详细性能分析"""
        print("=" * 60)
        print("    详细性能分析 (cProfile)")
        print("=" * 60)

        try:
            detector = CoalDetector(self.config)
            test_image = self._generate_test_image()

            # 使用cProfile分析
            pr = cProfile.Profile()
            pr.enable()

            # 运行检测
            for _ in range(10):
                detector.detect(test_image)

            pr.disable()

            # 分析结果
            stats = pstats.Stats(pr)
            stats.sort_stats('cumulative')

            print("最耗时的20个函数:")
            print("-" * 60)
            stats.print_stats(20)

            # 保存详细报告
            with open('logs/performance_profile.txt', 'w') as f:
                stats.print_stats(file=f)
            print(f"\n详细报告已保存: logs/performance_profile.txt")

        except Exception as e:
            print(f"详细分析失败: {e}")

    def benchmark_components(self):
        """组件级性能基准测试"""
        print("=" * 60)
        print("    组件性能基准测试")
        print("=" * 60)

        try:
            detector = CoalDetector(self.config)
            test_image = self._generate_test_image()

            # 测试各组件耗时
            components = {}

            # 1. ECC对齐
            if hasattr(detector, 'ecc_aligner') and detector.ecc_aligner:
                t0 = time.perf_counter()
                for _ in range(20):
                    detector.ecc_aligner.align(test_image)
                components['ECC对齐'] = (time.perf_counter() - t0) * 1000 / 20

            # 2. CLAHE增强
            if hasattr(detector, 'clahe'):
                gray = cv2.cvtColor(test_image, cv2.COLOR_BGR2GRAY)
                t0 = time.perf_counter()
                for _ in range(20):
                    detector.clahe.apply(gray)
                components['CLAHE增强'] = (time.perf_counter() - t0) * 1000 / 20

            # 3. 格栅计数
            if hasattr(detector, 'grid_counter'):
                t0 = time.perf_counter()
                for _ in range(20):
                    detector.grid_counter.count_grids(test_image)
                components['格栅计数'] = (time.perf_counter() - t0) * 1000 / 20

            # 4. 积煤检测
            if hasattr(detector, 'coal_detector'):
                t0 = time.perf_counter()
                for _ in range(20):
                    detector.coal_detector.detect_coal(test_image)
                components['积煤检测'] = (time.perf_counter() - t0) * 1000 / 20

            # 显示结果
            total_estimated = 0
            for name, avg_time in components.items():
                print(f"{name:12}: {avg_time:.1f}ms")
                total_estimated += avg_time

            print(f"{'预估总计':12}: {total_estimated:.1f}ms")
            print()

            return components

        except Exception as e:
            print(f"组件测试失败: {e}")
            return {}

    def _generate_test_image(self):
        """生成测试图像"""
        # 使用开发模式的分辨率
        height = self.config.frame_height
        width = self.config.frame_width

        # 加载真实测试图像，如果存在的话
        test_paths = [
            "tests/mock_data/clean/2.png",
            "tests/mock_data/clean/3.png",
            "tests/mock_data/clean/4.png"
        ]

        for path in test_paths:
            if os.path.exists(path):
                img = cv2.imread(path)
                if img is not None:
                    return cv2.resize(img, (width, height))

        # 如果没有测试图像，生成模拟图像
        print("警告: 使用模拟测试图像，结果可能不准确")

        # 生成带有格栅样式的测试图像
        img = np.random.randint(80, 120, (height, width, 3), dtype=np.uint8)

        # 添加格栅线条模拟
        grid_h = height // 14
        grid_w = width // 10

        for i in range(1, 14):
            y = i * grid_h
            cv2.line(img, (0, y), (width, y), (60, 60, 60), 2)

        for j in range(1, 10):
            x = j * grid_w
            cv2.line(img, (x, 0), (x, height), (60, 60, 60), 2)

        return img


def main():
    """主测试函数"""
    profiler = PerformanceProfiler()

    print("开始性能优化分析...")
    print(f"目标: 单帧处理 <= 80ms")
    print()

    # 1. 基线性能测量
    perf_results = profiler.measure_detector_performance(50)

    if perf_results:
        # 2. 组件级测试
        component_results = profiler.benchmark_components()

        # 3. 详细分析 (如果性能不达标)
        if perf_results['avg'] > 80:
            print("性能未达标，进行详细分析...")
            profiler.profile_detector_detailed()

        print("\n性能优化分析完成!")

        # 生成优化建议
        print("\n优化建议:")
        if perf_results['avg'] > 80:
            print("- 当前延迟超标，需要优化")
            print("- 检查详细性能分析报告: logs/performance_profile.txt")
            print("- 重点关注耗时最多的函数")
        else:
            print("- 当前性能达标，无需优化")

    else:
        print("性能测试失败，请检查系统状态")


if __name__ == "__main__":
    # 确保日志目录存在
    os.makedirs("logs", exist_ok=True)
    main()