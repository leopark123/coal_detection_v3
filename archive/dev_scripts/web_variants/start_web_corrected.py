#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
启动修正后的Web界面
使用108个格栅配置
"""

import os
import uvicorn

if __name__ == "__main__":
    # 设置环境变量
    os.environ['COAL_ENV'] = 'DEV'
    os.environ['USE_REAL_GRID_IN_DEV'] = 'True'

    print("=" * 60)
    print("  翻车机积煤检测系统 - Web界面（修正后）")
    print("=" * 60)
    print("📊 格栅配置: 12列 × 9行 = 108个")
    print("🌐 访问地址: http://localhost:8000")
    print("🔧 开发模式: 启用真实格栅配置")
    print("=" * 60)

    # 启动Web服务
    uvicorn.run(
        "web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )