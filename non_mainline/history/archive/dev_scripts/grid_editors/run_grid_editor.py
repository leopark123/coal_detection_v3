#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
网格编辑器Python启动器
避免批处理文件编码问题
"""

import subprocess
import sys
import os

def main():
    print("=" * 50)
    print("    稳定网格编辑器 V3.0")
    print("=" * 50)
    print("启动模式:")
    print("  [1] GUI图形界面模式")
    print("  [2] 快速模式 (14行x10列)")
    print("  [3] 直接启动")
    print()

    try:
        choice = input("请选择模式 [1-3], 回车使用快速模式: ").strip()

        if choice == "1":
            print("启动GUI模式...")
            cmd = [sys.executable, "tools/stable_grid_editor.py", "--gui"]
        elif choice == "2" or choice == "3" or choice == "":
            print("启动快速模式...")
            cmd = [sys.executable, "tools/stable_grid_editor.py", "--auto"]
        else:
            print("启动默认模式...")
            cmd = [sys.executable, "tools/stable_grid_editor.py", "--auto"]

        # 启动工具
        result = subprocess.run(cmd, cwd=os.getcwd())

        if result.returncode == 0:
            print("工具正常退出")
        else:
            print(f"工具退出，返回码: {result.returncode}")

    except KeyboardInterrupt:
        print("\n用户取消")
    except Exception as e:
        print(f"启动失败: {e}")

    input("按Enter键退出...")

if __name__ == "__main__":
    main()