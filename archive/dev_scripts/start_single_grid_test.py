#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
启动单格栅检测测试

阶段1：验证单个格栅的检测准确率
"""

import os
import sys
import uvicorn
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from config.config import Config
from algo.single_grid_detector import create_single_grid_config

def setup_single_grid_environment(target_grid_id: int = 0):
    """设置单格栅检测环境"""
    print("=" * 60)
    print(f"  单格栅检测模式 - 格栅ID: {target_grid_id}")
    print("=" * 60)

    # 设置环境变量
    os.environ['COAL_ENV'] = 'DEV'
    os.environ['USE_REAL_GRID_IN_DEV'] = 'True'
    os.environ['MOCK_SOURCE_DIR'] = 'tests/sample_only'
    os.environ['SINGLE_GRID_MODE'] = 'True'
    os.environ['TARGET_GRID_ID'] = str(target_grid_id)

    # 创建单格栅配置
    create_single_grid_config(target_grid_id)

    print(f"[INFO] 环境变量配置完成:")
    print(f"  - COAL_ENV: {os.environ.get('COAL_ENV')}")
    print(f"  - SINGLE_GRID_MODE: {os.environ.get('SINGLE_GRID_MODE')}")
    print(f"  - TARGET_GRID_ID: {os.environ.get('TARGET_GRID_ID')}")
    print(f"  - MOCK_SOURCE_DIR: {os.environ.get('MOCK_SOURCE_DIR')}")

    # 验证格栅数量
    config = Config()
    config.USE_REAL_GRID_IN_DEV = True

    print(f"\n[INFO] 格栅配置验证:")
    try:
        from algo.single_grid_detector import SingleGridDetector
        detector = SingleGridDetector(config, target_grid_id)
        print(f"  - 总格栅数量: {detector.original_grid_count}")
        print(f"  - 目标格栅ID: {detector.target_grid_id}")
        print(f"  - 目标格栅ROI: {detector.grid_rois[0]}")
        print(f"  ✅ 单格栅检测器初始化成功")
    except Exception as e:
        print(f"  ❌ 初始化失败: {e}")
        return False

    return True

if __name__ == "__main__":
    # 解析命令行参数
    target_grid_id = 0
    if len(sys.argv) > 1:
        try:
            target_grid_id = int(sys.argv[1])
        except ValueError:
            print(f"[ERROR] 无效的格栅ID: {sys.argv[1]}")
            print("用法: python start_single_grid_test.py [grid_id]")
            print("例如: python start_single_grid_test.py 5")
            sys.exit(1)

    # 设置环境
    if not setup_single_grid_environment(target_grid_id):
        print(f"[ERROR] 环境设置失败")
        sys.exit(1)

    print(f"\n[INFO] 启动单格栅检测Web界面...")
    print(f"[INFO] 访问地址: http://localhost:8000")
    print(f"[INFO] 检测模式: 单格栅验证 (格栅ID: {target_grid_id})")
    print(f"[INFO] 按 Ctrl+C 停止服务")
    print("=" * 60)

    # 启动Web服务
    try:
        uvicorn.run(
            "web.single_grid_app:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print(f"\n[INFO] 单格栅检测服务已停止")
    except Exception as e:
        print(f"[ERROR] 启动失败: {e}")