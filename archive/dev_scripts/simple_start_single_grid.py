#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简化版单格栅检测启动脚本
"""

import os
import sys
import uvicorn
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

def setup_environment(grid_id=0):
    """设置环境"""
    print("=" * 50)
    print(f"单格栅检测Web界面启动 - 格栅ID: {grid_id}")
    print("=" * 50)

    # 设置环境变量
    os.environ['COAL_ENV'] = 'DEV'
    os.environ['USE_REAL_GRID_IN_DEV'] = 'True'
    os.environ['MOCK_SOURCE_DIR'] = 'tests/sample_only'
    os.environ['SINGLE_GRID_MODE'] = 'True'
    os.environ['TARGET_GRID_ID'] = str(grid_id)

    print(f"[INFO] 环境配置完成")
    print(f"[INFO] 目标格栅: {grid_id}")
    print(f"[INFO] 图片目录: tests/sample_only")

    return True

if __name__ == "__main__":
    # 获取格栅ID
    grid_id = 0
    if len(sys.argv) > 1:
        try:
            grid_id = int(sys.argv[1])
        except ValueError:
            print(f"[ERROR] 无效格栅ID: {sys.argv[1]}")
            sys.exit(1)

    # 设置环境
    if not setup_environment(grid_id):
        sys.exit(1)

    print(f"\n[INFO] 启动Web服务...")
    print(f"[INFO] 访问地址: http://localhost:8001")
    print(f"[INFO] 按 Ctrl+C 停止")
    print("=" * 50)

    # 启动Web服务
    try:
        uvicorn.run(
            "web.single_grid_app:app",
            host="0.0.0.0",
            port=8001,
            reload=False,  # 禁用reload避免问题
            log_level="info"
        )
    except KeyboardInterrupt:
        print(f"\n[INFO] 服务已停止")
    except Exception as e:
        print(f"[ERROR] 启动失败: {e}")