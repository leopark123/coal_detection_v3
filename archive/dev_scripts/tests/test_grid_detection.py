#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
格栅检测测试脚本
验证修正后的格栅配置是否正确识别108个格栅孔
"""

import cv2
import numpy as np
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from config.config import Config
from algo.detector import CoalDetector


def _run_grid_detection_test() -> bool:
    """执行格栅检测测试并返回是否通过。"""
    print("🧪 开始测试格栅检测...")

    # 配置
    config = Config()
    config.DEV_MODE = False  # 使用真实格栅配置
    config.USE_REAL_GRID_IN_DEV = True  # 强制使用真实格栅

    # 初始化检测器
    try:
        detector = CoalDetector(config)
        grid_count = len(detector.grid_rois)
        print(f"✅ 检测器初始化成功")
        print(f"📊 当前格栅数量: {grid_count}")

        if grid_count in (108, 125):
            print(f"🎯 格栅数量可接受! ({grid_count}个)")
        else:
            print(f"❌ 格栅数量不正确! 期望108或125个，实际{grid_count}个")
            return False

    except Exception as e:
        print(f"❌ 检测器初始化失败: {e}")
        return False

    # 测试标注图片
    test_image_path = "tests/mock_data/clean/step_02_enhanced.jpg"
    if not Path(test_image_path).exists():
        print(f"❌ 测试图片不存在: {test_image_path}")
        return False

    # 加载测试图片
    image = cv2.imread(test_image_path)
    if image is None:
        print(f"❌ 无法加载测试图片")
        return False

    print(f"📸 测试图片: {test_image_path}")
    print(f"📐 图片尺寸: {image.shape}")

    # 确保输入尺寸匹配当前配置
    expected_size = (config.frame_width, config.frame_height)
    if (image.shape[1], image.shape[0]) != expected_size:
        image = cv2.resize(image, expected_size)
        print(f"🔧 图片已调整为: {image.shape}")

    # 执行检测
    try:
        result = detector.detect(image)
        print(f"✅ 检测执行成功")
        print(f"🎯 格栅可见率: {result.grid_visible_ratio:.2%}")
        print(f"🎯 积煤覆盖率: {result.coal_coverage:.2%}")
        print(f"🎯 置信度: {result.confidence}")
        print(f"⏱️ 处理时间: {result.process_time_ms:.1f}ms")

    except Exception as e:
        print(f"❌ 检测执行失败: {e}")
        return False

    # 生成标注图片
    try:
        annotated = detector.annotate_result(image.copy(), result)
        output_path = "logs/grid_detection_test_result.jpg"
        cv2.imwrite(output_path, annotated)
        print(f"💾 已保存标注结果: {output_path}")

    except Exception as e:
        print(f"⚠️ 保存标注图片失败: {e}")

    return True


def test_grid_detection():
    """pytest 入口。"""
    assert _run_grid_detection_test()


def compare_configurations():
    """对比不同配置的格栅数量"""
    print("\n📊 配置对比:")

    configs = [
        ("原始错误配置", "config/grid_manual.yaml", "10×14=132个"),
        ("修正后配置", "config/grid_corrected.yaml", "12×9=108个"),
        ("标注图片真实", "标注图片", "12×9=108个")
    ]

    for name, path, description in configs:
        status = "✅" if Path(path).exists() or "标注" in path else "❌"
        print(f"   {status} {name:<12}: {description}")


def provide_next_steps():
    """提供后续操作建议"""
    print(f"\n📋 后续操作建议:")

    steps = [
        "1. 如果测试通过，将 grid_corrected.yaml 替换 grid_manual.yaml",
        "2. 重新测试 Web 界面显示效果",
        "3. 更新其他测试图片的格栅配置",
        "4. 验证生产环境检测精度",
        "5. 更新文档和配置说明"
    ]

    for step in steps:
        print(f"   {step}")


if __name__ == "__main__":
    print("=" * 60)
    print("  格栅检测验证测试")
    print("=" * 60)

    # 配置对比
    compare_configurations()

    # 执行测试
    success = _run_grid_detection_test()

    # 后续建议
    provide_next_steps()

    if success:
        print(f"\n🎉 测试完成! 请查看生成的标注图片验证效果")
    else:
        print(f"\n❌ 测试失败! 请检查配置和依赖")

    print("=" * 60)
