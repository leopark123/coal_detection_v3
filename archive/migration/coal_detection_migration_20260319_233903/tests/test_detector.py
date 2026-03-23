"""
测试检测算法核心功能

涵盖：
1. CoalDetector 主检测器
2. 格栅计数算法
3. 积煤面积检测
4. 三级置信度判定
5. 边界情况处理
"""

import pytest
import numpy as np
import cv2
from pathlib import Path
import tempfile
import os

from algo.detector import CoalDetector
from algo.grid_counter import GridCounter
from algo.coal_detector import CoalAreaDetector
from algo.judge import CoalJudge
from config.config import Config


class TestCoalDetector:
    """CoalDetector 主检测器测试"""

    @pytest.fixture
    def config(self):
        """测试配置"""
        config = Config()
        config.DEV_MODE = True
        return config

    @pytest.fixture
    def detector(self, config):
        """检测器实例"""
        return CoalDetector(config)

    @pytest.fixture
    def test_image(self):
        """生成测试图像"""
        # 创建 1024x768 的测试图像
        img = np.zeros((768, 1024, 3), dtype=np.uint8)
        img.fill(128)  # 灰色背景

        # 添加一些模拟格栅孔
        for row in range(4):
            for col in range(6):
                x = 100 + col * 140
                y = 150 + row * 120
                cv2.rectangle(img, (x-30, y-20), (x+30, y+20), (50, 50, 50), -1)

        return img

    def test_detector_initialization(self, config):
        """测试检测器初始化"""
        detector = CoalDetector(config)

        assert detector.config == config
        assert hasattr(detector, 'grid_counter')
        assert hasattr(detector, 'coal_area_detector')
        assert hasattr(detector, 'judge')

    def test_detect_clean_image(self, detector, test_image):
        """测试干净图像检测"""
        result = detector.detect(test_image)

        assert isinstance(result, dict)
        assert "coal_present" in result
        assert "confidence" in result
        assert "grid_ratio" in result
        assert "coverage_ratio" in result
        assert "processing_time" in result

        # 返回结果应是可判定布尔或待确认状态
        assert result["coal_present"] in [True, False, None]
        assert result["confidence"] in ["HIGH", "MEDIUM", "LOW", "NORMAL"]

    def test_detect_with_coal(self, detector, test_image):
        """测试有积煤的图像检测"""
        # 在图像上添加模拟积煤（黑色区域）
        coal_image = test_image.copy()
        cv2.rectangle(coal_image, (200, 200), (800, 500), (30, 30, 30), -1)

        result = detector.detect(coal_image)

        # 有积煤的图像应该被检测出来
        assert result["coverage_ratio"] > 0.1
        # 注意：grid_ratio 可能不会明显变化，因为我们只是添加了黑色区域

    def test_detect_performance(self, detector, test_image):
        """测试检测性能"""
        # 运行多次检测
        times = []
        for _ in range(10):
            result = detector.detect(test_image)
            times.append(result["processing_time"])

        avg_time = np.mean(times)
        max_time = np.max(times)

        # 检查性能要求（DEV 模式下相对宽松）
        assert avg_time < 0.2, f"平均检测时间过长: {avg_time:.3f}s"
        assert max_time < 0.5, f"最大检测时间过长: {max_time:.3f}s"

    def test_detect_edge_cases(self, detector):
        """测试边界情况"""
        # 测试 None 输入
        with pytest.raises(ValueError):
            detector.detect(None)

        # 测试错误尺寸
        wrong_size_img = np.zeros((100, 100, 3), dtype=np.uint8)
        with pytest.raises(ValueError):
            detector.detect(wrong_size_img)

        # 测试错误类型
        wrong_dtype_img = np.zeros((768, 1024, 3), dtype=np.float32)
        # 应该自动转换，不抛异常
        result = detector.detect(wrong_dtype_img)
        assert isinstance(result, dict)

    def test_multiple_frames(self, detector, test_image):
        """测试多帧处理"""
        results = []
        for i in range(5):
            result = detector.detect(test_image, frame_id=i)
            results.append(result)

        # 检查帧ID是否正确记录
        for i, result in enumerate(results):
            if "frame_id" in result:
                assert result["frame_id"] == i


class TestGridCounter:
    """格栅计数器测试"""

    @pytest.fixture
    def config(self):
        config = Config()
        config.DEV_MODE = True
        return config

    @pytest.fixture
    def grid_counter(self, config):
        return GridCounter(config)

    @pytest.fixture
    def grid_image(self):
        """生成格栅图像"""
        img = np.full((768, 1024, 3), 160, dtype=np.uint8)

        # 绘制规则格栅孔
        for row in range(4):
            for col in range(6):
                x = 100 + col * 140
                y = 150 + row * 120
                cv2.rectangle(img, (x-40, y-30), (x+40, y+30), (40, 40, 40), -1)

        return img

    def test_count_clean_grid(self, grid_counter, grid_image):
        """测试干净格栅计数"""
        ratio = grid_counter.count_visible_holes(grid_image)

        assert isinstance(ratio, float)
        assert 0.0 <= ratio <= 1.0
        # 干净格栅应有基本可见率
        assert ratio > 0.2

    def test_count_blocked_grid(self, grid_counter, grid_image):
        """测试部分阻塞的格栅"""
        blocked_image = grid_image.copy()
        # 阻塞一些格栅孔
        cv2.rectangle(blocked_image, (200, 200), (600, 400), (120, 120, 120), -1)

        ratio = grid_counter.count_visible_holes(blocked_image)

        # 阻塞后的可见率应该降低
        clean_ratio = grid_counter.count_visible_holes(grid_image)
        assert ratio <= clean_ratio

    def test_invalid_input(self, grid_counter):
        """测试无效输入"""
        with pytest.raises((ValueError, AttributeError)):
            grid_counter.count_visible_holes(None)


class TestCoalAreaDetector:
    """积煤面积检测器测试"""

    @pytest.fixture
    def config(self):
        config = Config()
        config.DEV_MODE = True
        return config

    @pytest.fixture
    def coal_detector(self, config):
        return CoalAreaDetector(config)

    @pytest.fixture
    def clean_image(self):
        """干净图像"""
        return np.full((768, 1024, 3), (160, 160, 160), dtype=np.uint8)

    @pytest.fixture
    def coal_image(self):
        """含积煤图像"""
        img = np.full((768, 1024, 3), (160, 160, 160), dtype=np.uint8)
        # 添加深色积煤区域
        cv2.rectangle(img, (200, 200), (600, 400), (30, 30, 30), -1)
        return img

    def test_detect_clean_area(self, coal_detector, clean_image):
        """测试干净区域检测"""
        coverage = coal_detector.detect_coal_coverage(clean_image)

        assert isinstance(coverage, float)
        assert 0.0 <= coverage <= 1.0
        # 干净图像的覆盖率应该很低
        assert coverage < 0.1

    def test_detect_coal_area(self, coal_detector, coal_image):
        """测试积煤区域检测"""
        coverage = coal_detector.detect_coal_coverage(coal_image)

        # 有积煤的图像覆盖率应该较高
        assert coverage > 0.05

    def test_coverage_range(self, coal_detector):
        """测试覆盖率范围"""
        # 全黑图像
        black_image = np.zeros((768, 1024, 3), dtype=np.uint8)
        coverage_black = coal_detector.detect_coal_coverage(black_image)

        # 全白图像
        white_image = np.full((768, 1024, 3), 255, dtype=np.uint8)
        coverage_white = coal_detector.detect_coal_coverage(white_image)

        # 黑色图像覆盖率应该比白色高
        assert coverage_black > coverage_white


class TestCoalJudge:
    """综合判定器测试"""

    @pytest.fixture
    def config(self):
        config = Config()
        config.DEV_MODE = True
        return config

    @pytest.fixture
    def judge(self, config):
        return CoalJudge(config)

    def test_high_confidence_coal(self, judge):
        """测试高置信度积煤判定"""
        # 格栅可见率低，覆盖率高
        result = judge.judge(grid_ratio=0.6, coverage=0.2)

        assert result["coal_present"] == True
        assert result["confidence"] == "HIGH"
        assert result["need_manual"] == False

    def test_high_confidence_clean(self, judge):
        """测试高置信度干净判定"""
        # 格栅可见率高，覆盖率低
        result = judge.judge(grid_ratio=0.98, coverage=0.01)

        assert result["coal_present"] == False
        assert result["confidence"] == "HIGH"
        assert result["need_manual"] == False

    def test_low_confidence_case(self, judge):
        """测试低置信度情况"""
        # 指标矛盾：格栅可见率低但覆盖率也低
        result = judge.judge(grid_ratio=0.75, coverage=0.02)

        assert result["confidence"] == "LOW"
        assert result["need_manual"] == True

    def test_medium_confidence_case(self, judge):
        """测试中等置信度情况"""
        # 单一指标异常
        result = judge.judge(grid_ratio=0.55, coverage=0.08)

        assert result["confidence"] in ["MEDIUM", "HIGH"]

    def test_boundary_values(self, judge):
        """测试边界值"""
        # 测试 0 和 1 的边界情况
        result_min = judge.judge(grid_ratio=0.0, coverage=0.0)
        result_max = judge.judge(grid_ratio=1.0, coverage=1.0)

        assert isinstance(result_min, dict)
        assert isinstance(result_max, dict)


@pytest.mark.integration
class TestDetectorIntegration:
    """检测器集成测试"""

    @pytest.fixture
    def config(self):
        config = Config()
        config.DEV_MODE = True
        return config

    @pytest.fixture
    def test_images_dir(self):
        """测试图像目录"""
        return Path("tests/mock_data")

    def test_real_images(self, config, test_images_dir):
        """测试真实图像"""
        detector = CoalDetector(config)

        # 测试不同类型的图像
        test_categories = ["clean", "coal_light", "coal_heavy", "edge_cases"]

        for category in test_categories:
            category_dir = test_images_dir / category
            if not category_dir.exists():
                continue

            image_files = list(category_dir.glob("*.jpg"))
            if not image_files:
                continue

            print(f"\n测试类别: {category}")

            for img_path in image_files[:3]:  # 每类测试3张
                img = cv2.imread(str(img_path))
                if img is None:
                    continue

                # 调整尺寸
                img = cv2.resize(img, (config.frame_width, config.frame_height))

                result = detector.detect(img)

                print(f"  {img_path.name}: coal={result['coal_present']}, "
                      f"confidence={result['confidence']}, "
                      f"time={result['processing_time']:.3f}s")

                # 基本有效性检查
                assert isinstance(result, dict)
                assert 0.0 <= result["grid_ratio"] <= 1.0
                assert 0.0 <= result["coverage_ratio"] <= 1.0


if __name__ == "__main__":
    # 运行特定测试
    pytest.main([__file__, "-v"])
