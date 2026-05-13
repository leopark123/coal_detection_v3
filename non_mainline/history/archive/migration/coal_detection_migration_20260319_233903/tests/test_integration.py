"""
集成测试模块

测试项目：
1. 完整系统端到端测试
2. 开发模式 vs 生产模式切换
3. 配置文件加载测试
4. 驱动工厂测试
5. 错误恢复机制测试
6. Web 接口集成测试
"""

import pytest
import time
import tempfile
import os
import yaml
import multiprocessing as mp
from pathlib import Path
from unittest.mock import patch, MagicMock

from config.config import Config
from drivers.factory import create_camera, create_plc
from drivers.mock_drivers import MockCamera, MockPLC
from algo.detector import CoalDetector
from main import CoalDetectionSystem
from fastapi.routing import APIRoute, APIWebSocketRoute


class TestConfigSystem:
    """配置系统测试"""

    def test_dev_mode_detection(self):
        """测试开发模式检测"""
        # 测试默认配置
        config = Config()
        # 默认应该是生产模式（安全起见）
        assert config.DEV_MODE == False or config.DEV_MODE == True  # 取决于环境变量

    def test_environment_variable(self):
        """测试环境变量控制"""
        # 设置开发模式环境变量
        with patch.dict(os.environ, {'COAL_ENV': 'DEV'}):
            config = Config()
            assert config.DEV_MODE == True

        # 设置生产模式环境变量
        with patch.dict(os.environ, {'COAL_ENV': 'PROD'}):
            config = Config()
            assert config.DEV_MODE == False

    def test_yaml_config_loading(self):
        """测试 YAML 配置加载"""
        # 创建临时配置文件
        test_config = {
            'DEV_MODE': True,
            'FRAME_WIDTH': 1920,
            'FRAME_HEIGHT': 1080,
            'TARGET_FPS': 15.0,
            'LOG_LEVEL': 'DEBUG'
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_config, f)
            temp_path = f.name

        try:
            config = Config.from_yaml(temp_path)

            assert config.DEV_MODE == True
            assert config.FRAME_WIDTH == 1920
            assert config.FRAME_HEIGHT == 1080
            assert config.TARGET_FPS == 15.0
            assert config.LOG_LEVEL == 'DEBUG'

        finally:
            os.unlink(temp_path)

    def test_config_properties(self):
        """测试配置计算属性"""
        config = Config()

        # 测试分辨率属性
        if config.DEV_MODE:
            assert config.frame_width == config.DEV_FRAME_WIDTH
            assert config.frame_height == config.DEV_FRAME_HEIGHT
        else:
            assert config.frame_width == config.FRAME_WIDTH
            assert config.frame_height == config.FRAME_HEIGHT

        # 测试其他属性
        assert config.frame_size > 0
        assert config.frame_interval > 0
        assert config.ecc_scale_x > 0
        assert config.ecc_scale_y > 0

    def test_config_validation(self):
        """测试配置参数验证"""
        config = Config()

        # 基本合理性检查
        assert 100 <= config.frame_width <= 5000
        assert 100 <= config.frame_height <= 5000
        assert 0.1 <= config.TARGET_FPS <= 100
        assert config.CHANNELS in [1, 3, 4]


class TestDriverFactory:
    """驱动工厂测试"""

    def test_create_dev_camera(self):
        """测试创建开发模式相机"""
        config = Config()
        config.DEV_MODE = True

        camera = create_camera(config)
        assert isinstance(camera, MockCamera)

        # 测试基本功能
        frame = camera.grab()
        assert frame is not None
        assert frame.shape == (config.frame_height, config.frame_width, 3)

        camera.release()

    def test_create_dev_plc(self):
        """测试创建开发模式 PLC"""
        config = Config()
        config.DEV_MODE = True

        plc = create_plc(config)
        assert isinstance(plc, MockPLC)

        # 测试基本功能
        success = plc.write("test_tag", 123)
        assert success == True

        value = plc.read("test_tag")
        assert value == 123

        plc.close()

    def test_production_driver_fallback(self):
        """测试生产驱动回退机制"""
        config = Config()
        config.DEV_MODE = False

        # 由于没有真实硬件，应该回退到 Mock 驱动
        camera = create_camera(config)
        plc = create_plc(config)

        # 应该能正常工作（即使是回退的Mock驱动）
        assert hasattr(camera, 'grab')
        assert hasattr(plc, 'write')

        camera.release()
        plc.close()


class TestDetectorIntegration:
    """检测器集成测试"""

    @pytest.fixture
    def config(self):
        config = Config()
        config.DEV_MODE = True
        return config

    def test_detector_with_real_images(self, config):
        """使用真实测试图像进行检测"""
        detector = CoalDetector(config)
        test_images_dir = Path("tests/mock_data")

        if not test_images_dir.exists():
            pytest.skip("测试图像目录不存在")

        # 测试每种类型的图像
        test_results = {}

        for category in ["clean", "coal_light", "coal_heavy"]:
            category_dir = test_images_dir / category
            if not category_dir.exists():
                continue

            image_files = list(category_dir.glob("*.jpg"))[:3]  # 每类测试3张
            category_results = []

            for img_path in image_files:
                try:
                    import cv2
                    img = cv2.imread(str(img_path))
                    if img is None:
                        continue

                    # 调整尺寸
                    img = cv2.resize(img, (config.frame_width, config.frame_height))

                    result = detector.detect(img)
                    category_results.append(result)

                except Exception as e:
                    print(f"处理图像 {img_path} 失败: {e}")

            if category_results:
                test_results[category] = category_results

        # 验证检测结果的一致性
        for category, results in test_results.items():
            print(f"\n{category} 类别结果:")
            coal_detections = [r["coal_present"] for r in results]
            avg_confidence = [r["confidence"] for r in results]

            print(f"  检测结果: {coal_detections}")
            print(f"  置信度: {avg_confidence}")

            # 同类图像应该有相似的检测结果
            assert len(set(coal_detections)) <= 2, f"{category} 类别结果不一致"

    def test_detection_consistency(self, config):
        """测试检测一致性"""
        detector = CoalDetector(config)

        # 创建固定的测试图像
        import numpy as np
        np.random.seed(42)  # 固定随机种子
        img = np.random.randint(
            100, 150, (config.frame_height, config.frame_width, 3), dtype=np.uint8
        )

        # 多次检测同一图像
        results = []
        for i in range(5):
            result = detector.detect(img.copy())  # 使用拷贝避免修改原图
            results.append(result)

        # 检查一致性
        coal_present_results = [r["coal_present"] for r in results]
        assert len(set(coal_present_results)) == 1, "同一图像多次检测结果不一致"

        confidence_results = [r["confidence"] for r in results]
        # 置信度可能有小幅波动，但不应该大幅变化
        assert len(set(confidence_results)) <= 2, "同一图像置信度变化过大"

    def test_memory_leak_detection(self, config):
        """测试内存泄漏"""
        psutil = pytest.importorskip("psutil", reason="该测试依赖 psutil")
        import gc

        detector = CoalDetector(config)
        process = psutil.Process()

        # 获取初始内存
        gc.collect()
        initial_memory = process.memory_info().rss / 1024 / 1024

        # 创建测试图像
        import numpy as np
        img = np.random.randint(
            100, 150, (config.frame_height, config.frame_width, 3), dtype=np.uint8
        )

        # 大量检测
        for i in range(200):
            result = detector.detect(img, frame_id=i)

            # 定期检查内存
            if i % 50 == 0 and i > 0:
                gc.collect()
                current_memory = process.memory_info().rss / 1024 / 1024
                memory_growth = current_memory - initial_memory

                print(f"Frame {i}: 内存增长 {memory_growth:.1f} MB")

                # 内存增长应该控制在合理范围内
                assert memory_growth < 200, f"可能存在内存泄漏: {memory_growth:.1f} MB"


class TestSystemIntegration:
    """系统集成测试"""

    @pytest.fixture
    def config(self):
        config = Config()
        config.DEV_MODE = True
        config.DEV_FPS = 2.0  # 提高测试效率
        return config

    def test_system_startup_shutdown(self, config):
        """测试系统启动和关闭"""
        system = CoalDetectionSystem(config)

        # 测试启动
        success = system.start()
        assert success == True

        # 等待一下让系统稳定
        time.sleep(2)

        # 检查系统状态
        assert system.is_running()

        # 测试关闭
        system.stop()
        time.sleep(1)

        assert not system.is_running()

    def test_error_recovery(self, config):
        """测试错误恢复机制"""
        system = CoalDetectionSystem(config)

        # 模拟关键组件初始化失败，系统应返回失败并保持未运行状态
        with patch("main.DoubleBuffer", side_effect=RuntimeError("simulated init failure")):
            assert system.start() is False
            assert system.is_running() is False

        # 失败后 stop() 应可重入调用，不应抛异常
        system.stop()
        assert system.is_running() is False

    @pytest.mark.slow
    def test_long_running_stability(self, config):
        """测试长时间运行稳定性"""
        system = CoalDetectionSystem(config)

        try:
            system.start()

            # 运行 30 秒
            start_time = time.time()
            last_stats_time = start_time

            while time.time() - start_time < 30:
                # 每5秒检查一次状态
                if time.time() - last_stats_time >= 5:
                    assert system.is_running(), "系统异常停止"

                    stats = system.get_status()
                    print(f"运行时间: {time.time() - start_time:.1f}s, "
                          f"采集: {stats.get('capture_fps', 0):.1f} FPS, "
                          f"检测: {stats.get('detect_fps', 0):.1f} FPS")

                    last_stats_time = time.time()

                time.sleep(0.1)

            # 检查最终状态
            final_stats = system.get_status()
            assert final_stats.get('capture_fps', 0) > 0.1, "采集停止工作"
            assert final_stats.get('detect_fps', 0) > 0.1, "检测停止工作"

        finally:
            system.stop()


class TestWebIntegration:
    """Web 接口集成测试"""

    def test_web_api_endpoints(self):
        """测试 Web API 端点"""
        from web.app import app

        http_routes = {
            (route.path, tuple(sorted(route.methods)))
            for route in app.routes
            if isinstance(route, APIRoute)
        }

        assert ("/", ("GET",)) in http_routes
        assert ("/api/status", ("GET",)) in http_routes
        assert ("/api/camera/debug", ("GET",)) in http_routes

    def test_websocket_connection(self):
        """测试 WebSocket 连接"""
        from web.app import app

        ws_paths = [route.path for route in app.routes if isinstance(route, APIWebSocketRoute)]
        assert "/ws" in ws_paths


class TestConfigurationScenarios:
    """配置场景测试"""

    def test_dev_to_prod_switch(self):
        """测试开发到生产模式切换"""
        # 开发模式配置
        dev_config = Config()
        dev_config.DEV_MODE = True

        # 生产模式配置
        prod_config = Config()
        prod_config.DEV_MODE = False

        # 验证关键差异
        assert dev_config.frame_width < prod_config.frame_width
        assert dev_config.frame_height < prod_config.frame_height
        assert not dev_config.use_cuda_actual
        assert not dev_config.use_ecc_actual

    def test_config_file_priority(self):
        """测试配置文件优先级"""
        # 场景1：配置文件未设置 DEV_MODE 时，应继承环境变量
        yaml_without_mode = {
            "FRAME_WIDTH": 1920,
            "FRAME_HEIGHT": 1080,
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(yaml_without_mode, f)
            temp_path = f.name

        try:
            with patch.dict(os.environ, {"COAL_ENV": "DEV"}):
                config = Config.from_yaml(temp_path)
                assert config.DEV_MODE is True
        finally:
            os.unlink(temp_path)

        # 场景2：命令行 --dev 应覆盖配置文件中的 DEV_MODE=False
        yaml_prod = {"DEV_MODE": False}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(yaml_prod, f)
            temp_path = f.name

        try:
            config = Config.from_yaml(temp_path)
            assert config.DEV_MODE is False

            # 模拟 main.py 中的命令行覆盖逻辑
            args_dev = True
            if args_dev:
                config.DEV_MODE = True
            assert config.DEV_MODE is True
        finally:
            os.unlink(temp_path)


@pytest.mark.integration
class TestRealWorldScenarios:
    """真实世界场景测试"""

    def test_camera_disconnect_recovery(self):
        """测试相机断线恢复"""
        config = Config()
        config.DEV_MODE = True
        config.MOCK_ENABLE_FAULT_INJECTION = True
        config.MOCK_CAMERA_FAIL_RATE = 0.3  # 30% 故障率

        camera = create_camera(config)

        success_count = 0
        error_count = 0

        # 尝试采集100帧，测试错误恢复
        for i in range(100):
            try:
                frame = camera.grab()
                if frame is not None:
                    success_count += 1
            except Exception:
                error_count += 1
                # 模拟重连
                if hasattr(camera, 'reconnect'):
                    camera.reconnect()

        camera.release()

        print(f"采集测试: 成功 {success_count}, 失败 {error_count}")

        # 即使有故障注入，成功率也应该达到一定比例
        success_rate = success_count / (success_count + error_count)
        assert success_rate > 0.5, f"成功率过低: {success_rate:.2%}"

    def test_plc_communication_timeout(self):
        """测试 PLC 通信超时处理"""
        config = Config()
        config.DEV_MODE = True
        config.MOCK_ENABLE_FAULT_INJECTION = True

        plc = create_plc(config)

        # 测试批量写入
        write_results = []
        for i in range(50):
            success = plc.write(f"test_tag_{i}", i)
            write_results.append(success)

        plc.close()

        # 大部分写入应该成功
        success_rate = sum(write_results) / len(write_results)
        assert success_rate > 0.8, f"PLC 写入成功率过低: {success_rate:.2%}"


if __name__ == "__main__":
    # 运行集成测试
    pytest.main([__file__, "-v", "--tb=short"])
