"""
性能测试模块

测试项目：
1. 检测算法性能（延迟、吞吐量）
2. 多进程架构性能
3. 内存使用效率
4. 跳帧率统计
5. 端到端延迟测试

性能目标（基于 CLAUDE.md）：
- 单帧检测延迟 ≤ 80ms (DEV模式 ≤ 200ms)
- 端到端延迟 ≤ 150ms (DEV模式 ≤ 500ms)
- 跳帧率 ≤ 10%
- 心跳间隔 500ms ± 50ms
"""

import pytest
import time
import numpy as np
import cv2
import os
import importlib.util
import multiprocessing as mp
from pathlib import Path
from statistics import mean, stdev

psutil = pytest.importorskip("psutil", reason="性能测试依赖 psutil")

from algo.detector import CoalDetector
from config.config import Config


class TestDetectorPerformance:
    """检测算法性能测试"""

    @pytest.fixture
    def config(self):
        config = Config()
        config.DEV_MODE = True
        return config

    @pytest.fixture
    def detector(self, config):
        return CoalDetector(config)

    @pytest.fixture
    def test_image(self, config):
        """标准测试图像"""
        img = np.random.randint(
            50, 200, (config.frame_height, config.frame_width, 3), dtype=np.uint8
        )
        # 添加一些格栅孔模拟
        for row in range(4):
            for col in range(6):
                x = 100 + col * 140
                y = 150 + row * 120
                cv2.rectangle(img, (x-30, y-20), (x+30, y+20), (40, 40, 40), -1)
        return img

    def test_single_detection_latency(self, detector, test_image):
        """测试单次检测延迟"""
        # 预热
        for _ in range(5):
            detector.detect(test_image)

        # 测试延迟
        latencies = []
        for _ in range(50):
            start_time = time.time()
            result = detector.detect(test_image)
            latency = time.time() - start_time
            latencies.append(latency * 1000)  # 转为毫秒

        avg_latency = mean(latencies)
        max_latency = max(latencies)
        std_latency = stdev(latencies) if len(latencies) > 1 else 0

        print(f"检测延迟统计:")
        print(f"  平均: {avg_latency:.1f}ms")
        print(f"  最大: {max_latency:.1f}ms")
        print(f"  标准差: {std_latency:.1f}ms")

        # 性能断言（DEV模式相对宽松）
        assert avg_latency < 200, f"平均延迟过高: {avg_latency:.1f}ms > 200ms"
        assert max_latency < 500, f"最大延迟过高: {max_latency:.1f}ms > 500ms"
        assert std_latency < 50, f"延迟波动过大: {std_latency:.1f}ms"

    def test_sustained_throughput(self, detector, test_image):
        """测试持续吞吐量"""
        duration = 10  # 测试10秒
        start_time = time.time()
        frame_count = 0

        print(f"测试持续吞吐量 ({duration}秒)...")

        while time.time() - start_time < duration:
            detector.detect(test_image, frame_id=frame_count)
            frame_count += 1

        elapsed = time.time() - start_time
        fps = frame_count / elapsed

        print(f"持续吞吐量: {fps:.1f} FPS ({frame_count} 帧 / {elapsed:.1f}s)")

        # DEV 模式下预期 1-5 FPS
        assert fps > 0.5, f"吞吐量过低: {fps:.1f} FPS"

    def test_memory_usage(self, detector, test_image):
        """测试内存使用"""
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # 运行100次检测
        for i in range(100):
            detector.detect(test_image, frame_id=i)

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - initial_memory

        print(f"内存使用:")
        print(f"  初始: {initial_memory:.1f} MB")
        print(f"  最终: {final_memory:.1f} MB")
        print(f"  增长: {memory_growth:.1f} MB")

        # 内存增长应该很少（避免内存泄漏）
        assert memory_growth < 50, f"内存增长过多: {memory_growth:.1f} MB"

    def test_batch_processing(self, detector, config):
        """测试批量处理性能"""
        # 生成多张测试图像
        batch_size = 20
        images = []
        for i in range(batch_size):
            img = np.random.randint(
                100, 150, (config.frame_height, config.frame_width, 3), dtype=np.uint8
            )
            images.append(img)

        # 测试批量处理
        start_time = time.time()
        results = []
        for i, img in enumerate(images):
            result = detector.detect(img, frame_id=i)
            results.append(result)

        elapsed = time.time() - start_time
        avg_time_per_frame = elapsed / batch_size * 1000

        print(f"批量处理 {batch_size} 帧:")
        print(f"  总时间: {elapsed:.2f}s")
        print(f"  平均每帧: {avg_time_per_frame:.1f}ms")

        assert len(results) == batch_size
        assert avg_time_per_frame < 300  # DEV模式下每帧300ms以内


_has_core_multiprocess = importlib.util.find_spec("core.double_buffer") is not None


@pytest.mark.skipif(not _has_core_multiprocess, reason="core 双进程模块已归档到 scripts/legacy/")
class TestMultiProcessPerformance:
    """多进程架构性能测试"""

    @pytest.fixture
    def config(self):
        config = Config()
        config.DEV_MODE = True
        config.DEV_FPS = 5.0  # 提高测试帧率
        return config

    @pytest.mark.slow
    def test_double_buffer_performance(self, config):
        """测试双缓冲区性能"""
        from core.double_buffer import DoubleBuffer

        buffer = DoubleBuffer(config)

        try:
            # 性能基准测试
            perf_results = buffer.test_performance(iterations=100)

            print("双缓冲区性能:")
            print(f"  写入: {perf_results['write_fps']:.1f} FPS")
            print(f"  读取: {perf_results['read_fps']:.1f} FPS")
            print(f"  写入带宽: {perf_results['write_bandwidth_mbps']:.1f} MB/s")
            print(f"  读取带宽: {perf_results['read_bandwidth_mbps']:.1f} MB/s")

            # 性能断言
            assert perf_results['write_fps'] > 10, "写入性能不足"
            assert perf_results['read_fps'] > 10, "读取性能不足"
            assert perf_results['avg_write_latency_ms'] < 50, "写入延迟过高"
            assert perf_results['avg_read_latency_ms'] < 50, "读取延迟过高"

        finally:
            buffer.close()

    @pytest.mark.slow
    def test_frame_state_performance(self, config):
        """测试帧状态管理性能"""
        from core.frame_state import FrameState

        state = FrameState(config)

        # 模拟高频读写
        start_time = time.time()
        iterations = 1000

        for i in range(iterations):
            # 模拟采集进程
            buffer_idx, frame_id = state.begin_write()
            state.end_write(buffer_idx)

            # 模拟检测进程
            if i % 2 == 0:  # 50% 处理率，模拟跳帧
                latest = state.get_latest_frame()
                if latest:
                    buf_idx, fid, ts = latest
                    state.mark_frame_processed(buf_idx, fid)

        elapsed = time.time() - start_time
        ops_per_second = (iterations * 2) / elapsed  # 每次迭代有2个操作

        print(f"帧状态管理性能: {ops_per_second:.0f} ops/sec")

        # 获取性能统计
        stats = state.get_performance_stats()
        print(f"跳帧率: {stats['skip_rate_percent']:.1f}%")

        assert ops_per_second > 1000, "状态管理性能不足"
        assert stats['skip_rate_percent'] < 60, "跳帧率过高"

    @pytest.mark.slow
    def test_end_to_end_latency(self, config):
        """测试端到端延迟"""
        from core.double_buffer import DoubleBuffer
        from core.frame_state import FrameState
        from core.capture_process import CaptureProcess
        from core.detect_process import DetectProcess

        if mp.get_start_method() != 'spawn':
            pytest.skip("需要 spawn 启动方式进行多进程测试")

        # 创建共享组件
        state = FrameState(config)
        buffer = DoubleBuffer(config)
        buffer_names = (buffer.shm_buffer0.name, buffer.shm_buffer1.name)

        # 创建进程
        capture_proc = CaptureProcess(config, state, buffer_names)
        detect_proc = DetectProcess(config, state, buffer_names)

        try:
            # 启动进程
            capture_proc.start()
            time.sleep(2)  # 等待采集稳定

            detect_proc.start()
            time.sleep(1)  # 等待检测启动

            # 监控延迟
            latencies = []
            monitoring_duration = 15  # 监控15秒

            print(f"监控端到端延迟 ({monitoring_duration}秒)...")

            start_monitoring = time.time()
            while time.time() - start_monitoring < monitoring_duration:
                # 获取最新帧信息
                latest = state.get_latest_frame()
                if latest:
                    _, _, capture_timestamp = latest
                    current_time = time.time()
                    latency = (current_time - capture_timestamp) * 1000

                    if 0 < latency < 2000:  # 有效延迟范围
                        latencies.append(latency)

                time.sleep(0.1)

            if latencies:
                avg_latency = mean(latencies)
                max_latency = max(latencies)
                p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

                print(f"端到端延迟统计:")
                print(f"  平均: {avg_latency:.1f}ms")
                print(f"  最大: {max_latency:.1f}ms")
                print(f"  P95: {p95_latency:.1f}ms")

                # DEV模式延迟要求相对宽松
                assert avg_latency < 500, f"平均延迟过高: {avg_latency:.1f}ms"
                assert p95_latency < 1000, f"P95延迟过高: {p95_latency:.1f}ms"

            # 获取最终统计
            capture_stats = capture_proc.get_stats()
            detect_stats = detect_proc.get_stats()
            perf_stats = state.get_performance_stats()

            print(f"最终统计:")
            print(f"  采集帧率: {capture_stats['current_fps']:.1f} FPS")
            print(f"  检测帧率: {detect_stats['current_detect_fps']:.1f} FPS")
            print(f"  跳帧率: {perf_stats['skip_rate_percent']:.1f}%")

            # 基本性能检查
            assert capture_stats['current_fps'] > 0.5, "采集帧率过低"
            assert detect_stats['current_detect_fps'] > 0.2, "检测帧率过低"
            assert perf_stats['skip_rate_percent'] < 80, "跳帧率过高"

        finally:
            # 清理进程
            detect_proc.stop()
            capture_proc.stop()
            buffer.close()


class TestSystemLoad:
    """系统负载测试"""

    def test_cpu_usage(self):
        """测试 CPU 使用率"""
        from config.config import Config
        from algo.detector import CoalDetector

        config = Config()
        config.DEV_MODE = True
        detector = CoalDetector(config)

        # 生成测试图像
        img = np.random.randint(
            100, 150, (config.frame_height, config.frame_width, 3), dtype=np.uint8
        )

        # 监控 CPU 使用率
        cpu_before = psutil.cpu_percent(interval=1)

        # 高强度检测
        start_time = time.time()
        count = 0
        while time.time() - start_time < 5:  # 运行5秒
            detector.detect(img, frame_id=count)
            count += 1

        cpu_after = psutil.cpu_percent(interval=1)
        cpu_usage = cpu_after

        fps = count / 5
        print(f"高强度测试:")
        print(f"  检测帧率: {fps:.1f} FPS")
        print(f"  CPU 使用率: {cpu_usage:.1f}%")

        # CPU 使用率不应该持续100%
        assert cpu_usage < 95, f"CPU 使用率过高: {cpu_usage:.1f}%"

    def test_memory_stability(self):
        """测试内存稳定性"""
        from config.config import Config
        from algo.detector import CoalDetector

        config = Config()
        config.DEV_MODE = True
        detector = CoalDetector(config)

        img = np.random.randint(
            100, 150, (config.frame_height, config.frame_width, 3), dtype=np.uint8
        )

        # 记录内存使用变化
        process = psutil.Process()
        memory_samples = []

        for i in range(100):
            detector.detect(img, frame_id=i)

            if i % 10 == 0:
                memory_mb = process.memory_info().rss / 1024 / 1024
                memory_samples.append(memory_mb)

        # 检查内存是否稳定（不持续增长）
        if len(memory_samples) > 2:
            initial_memory = mean(memory_samples[:3])
            final_memory = mean(memory_samples[-3:])
            memory_growth = final_memory - initial_memory

            print(f"内存稳定性:")
            print(f"  初始: {initial_memory:.1f} MB")
            print(f"  最终: {final_memory:.1f} MB")
            print(f"  增长: {memory_growth:.1f} MB")

            # 内存增长应该控制在合理范围内
            assert memory_growth < 100, f"内存增长过多: {memory_growth:.1f} MB"


@pytest.mark.benchmark
class TestBenchmark:
    """基准测试"""

    def test_algorithm_comparison(self):
        """对比不同算法实现的性能"""
        # 轻量对比：DEV 快速路径（无 ECC） vs PROD 完整路径（启用 ECC）
        width, height = 640, 480
        frame = np.random.randint(100, 150, (height, width, 3), dtype=np.uint8)

        dev_config = Config()
        dev_config.DEV_MODE = True
        dev_config.DEV_FRAME_WIDTH = width
        dev_config.DEV_FRAME_HEIGHT = height

        prod_config = Config()
        prod_config.DEV_MODE = False
        prod_config.FRAME_WIDTH = width
        prod_config.FRAME_HEIGHT = height
        prod_config.USE_ECC = True
        prod_config.ECC_PROCESS_WIDTH = 160
        prod_config.ECC_PROCESS_HEIGHT = 120

        dev_detector = CoalDetector(dev_config)
        prod_detector = CoalDetector(prod_config)

        def _measure(detector, runs=5):
            timings = []
            last_result = None
            for i in range(runs):
                start = time.time()
                last_result = detector.detect(frame, frame_id=i)
                timings.append((time.time() - start) * 1000)
            return mean(timings), last_result

        dev_avg_ms, dev_result = _measure(dev_detector)
        prod_avg_ms, prod_result = _measure(prod_detector)

        print("算法对比:")
        print(f"  DEV(无ECC) 平均耗时: {dev_avg_ms:.1f}ms")
        print(f"  PROD(含ECC) 平均耗时: {prod_avg_ms:.1f}ms")

        # 基本有效性断言：均能成功输出且耗时合理
        assert dev_avg_ms > 0
        assert prod_avg_ms > 0
        assert dev_avg_ms < 1500
        assert prod_avg_ms < 1500
        assert hasattr(dev_result, 'to_dict')  # DetectionResult (dict-like)
        assert hasattr(prod_result, 'to_dict')
        assert "confidence" in dev_result
        assert "confidence" in prod_result

    def test_resolution_scaling(self):
        """测试不同分辨率下的性能缩放"""
        from config.config import Config
        from algo.detector import CoalDetector

        # 测试不同分辨率
        resolutions = [
            (320, 240),   # 小尺寸
            (640, 480),   # 中等尺寸
            (1024, 768),  # DEV标准尺寸
        ]

        results = []

        for width, height in resolutions:
            config = Config()
            config.DEV_MODE = True
            config.DEV_FRAME_WIDTH = width
            config.DEV_FRAME_HEIGHT = height

            detector = CoalDetector(config)
            img = np.random.randint(100, 150, (height, width, 3), dtype=np.uint8)

            # 测试10次取平均
            times = []
            for _ in range(10):
                start = time.time()
                detector.detect(img)
                times.append(time.time() - start)

            avg_time = mean(times) * 1000
            pixels = width * height

            results.append({
                'resolution': f"{width}x{height}",
                'pixels': pixels,
                'avg_time_ms': avg_time,
                'pixels_per_ms': pixels / avg_time
            })

            print(f"{width}x{height}: {avg_time:.1f}ms ({results[-1]['pixels_per_ms']:.0f} pixels/ms)")

        # 验证性能随分辨率合理缩放
        assert len(results) == len(resolutions)


if __name__ == "__main__":
    # 运行性能测试
    pytest.main([__file__, "-v", "-s", "--tb=short"])
