#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
启动Web界面 - 展示125个精确格栅检测
"""

import os
import uvicorn

if __name__ == "__main__":
    # 设置环境变量
    os.environ['COAL_ENV'] = 'DEV'
    os.environ['USE_REAL_GRID_IN_DEV'] = 'True'

    print("=" * 60)
    print("  翻车机积煤检测系统 - 125个精确格栅")
    print("=" * 60)
    print("[INFO] 格栅配置: 精确标注的125个不规则四边形")
    print("[INFO] 访问地址: http://localhost:8000")
    print("[INFO] 图片尺寸: 462×603 (匹配样本图片)")
    print("[INFO] 标注工具: GridEditorToolKit")
    print("=" * 60)

    # 启动Web服务
    uvicorn.run(
        "web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )