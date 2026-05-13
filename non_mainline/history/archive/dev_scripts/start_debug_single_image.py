#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
调试版本：启动Web界面专门检测标注图片
"""

import os
import uvicorn
from pathlib import Path

if __name__ == "__main__":
    print("=" * 60)
    print("  调试启动：专门检测GridEditorToolKit标注图片")
    print("=" * 60)

    # 设置环境变量
    os.environ['COAL_ENV'] = 'DEV'
    os.environ['USE_REAL_GRID_IN_DEV'] = 'True'
    os.environ['MOCK_SOURCE_DIR'] = 'tests/sample_only'

    print(f"[DEBUG] 设置COAL_ENV = {os.environ.get('COAL_ENV')}")
    print(f"[DEBUG] 设置USE_REAL_GRID_IN_DEV = {os.environ.get('USE_REAL_GRID_IN_DEV')}")
    print(f"[DEBUG] 设置MOCK_SOURCE_DIR = {os.environ.get('MOCK_SOURCE_DIR')}")

    # 验证目标目录和图片
    target_dir = Path("tests/sample_only")
    if target_dir.exists():
        images = list(target_dir.glob("*.png"))
        print(f"[DEBUG] 目标目录存在: {target_dir}")
        print(f"[DEBUG] 找到图片: {len(images)} 张")
        for img in images:
            print(f"  - {img}")
    else:
        print(f"[ERROR] 目标目录不存在: {target_dir}")

    print("\n[INFO] 启动Web服务...")
    print("[INFO] 访问地址: http://localhost:8000")
    print("[INFO] 如果界面还显示其他图片，请清除浏览器缓存!")
    print("=" * 60)

    # 启动Web服务
    uvicorn.run(
        "web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )