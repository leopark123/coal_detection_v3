"""
简化的网格编辑器启动脚本
包含错误检查和诊断
"""

import sys
import os
from pathlib import Path

def check_dependencies():
    """检查依赖"""
    print("=== 检查依赖项 ===")

    try:
        import cv2
        print(f"[OK] OpenCV版本: {cv2.__version__}")
    except ImportError:
        print("[ERROR] OpenCV未安装")
        return False

    try:
        import numpy as np
        print(f"[OK] NumPy版本: {np.__version__}")
    except ImportError:
        print("[ERROR] NumPy未安装")
        return False

    return True

def check_files():
    """检查文件"""
    print("\n=== 检查文件 ===")

    image_path = "tests/mock_data/clean/2.png"
    if Path(image_path).exists():
        print(f"[OK] 图片文件存在: {image_path}")
    else:
        print(f"[ERROR] 图片文件不存在: {image_path}")
        return False

    tool_path = "tools/ultimate_grid_editor.py"
    if Path(tool_path).exists():
        print(f"[OK] 编辑器存在: {tool_path}")
    else:
        print(f"[ERROR] 编辑器不存在: {tool_path}")
        return False

    return True

def start_editor():
    """启动编辑器"""
    print("\n=== 启动网格编辑器 ===")

    try:
        from tools.ultimate_grid_editor import UltimateGridEditor

        print("创建编辑器实例...")
        editor = UltimateGridEditor("tests/mock_data/clean/2.png", 13, 10)

        print("启动编辑器界面...")
        editor.run_editor("config/grid_baseline.json")

    except Exception as e:
        print(f"[ERROR] 启动失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

def main():
    print("=== 终极网格精修工具 启动器 ===")
    print("目标: 13行 x 10列格栅标定")
    print()

    # 检查依赖
    if not check_dependencies():
        print("\n[ERROR] 依赖检查失败，请安装必要的包")
        input("按Enter键退出...")
        return

    # 检查文件
    if not check_files():
        print("\n[ERROR] 文件检查失败，请检查项目文件")
        input("按Enter键退出...")
        return

    # 启动编辑器
    if start_editor():
        print("\n[OK] 编辑器已正常退出")
    else:
        print("\n[ERROR] 编辑器运行出现错误")

    input("按Enter键退出...")

if __name__ == "__main__":
    main()