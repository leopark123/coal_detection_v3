#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
网格编辑器直接启动器 - 无需用户交互
直接启动14行x10列的网格编辑器
"""

import subprocess
import sys
import os

def main():
    print("=" * 50)
    print("    网格编辑器直接启动 V3.0")
    print("=" * 50)
    print("模式: 14行 x 10列网格编辑器")
    print("图片: tests/mock_data/clean/2.png")
    print("=" * 50)

    try:
        # 直接启动自动模式
        cmd = [sys.executable, "tools/stable_grid_editor.py", "--auto"]

        print("正在启动网格编辑器...")
        result = subprocess.run(cmd, cwd=os.getcwd())

        print(f"编辑器已退出 (返回码: {result.returncode})")

    except Exception as e:
        print(f"启动失败: {e}")

if __name__ == "__main__":
    main()