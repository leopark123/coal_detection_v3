#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Grid Editor Toolkit 打包脚本
自动化创建可分发的工具包
"""

import os
import shutil
import zipfile
from pathlib import Path
import datetime

def create_package():
    """创建工具包压缩包"""

    print("=" * 50)
    print("  Grid Editor Toolkit Packager")
    print("=" * 50)

    # 获取当前目录
    current_dir = Path(__file__).parent

    # 检查必要文件
    required_files = [
        "src/grid_editor.py",
        "requirements.txt",
        "README.md",
        "run_grid_editor.bat",
        "run_grid_editor.sh"
    ]

    missing_files = []
    for file_path in required_files:
        if not (current_dir / file_path).exists():
            missing_files.append(file_path)

    if missing_files:
        print("[ERROR] Missing required files:")
        for file in missing_files:
            print(f"  - {file}")
        return False

    # 创建打包目录
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    package_name = f"GridEditorToolKit_v1.0.0_{timestamp}"
    package_dir = current_dir.parent / package_name

    if package_dir.exists():
        shutil.rmtree(package_dir)

    package_dir.mkdir(parents=True)

    print(f"Creating package: {package_name}")

    # 复制文件结构
    dirs_to_copy = ["src", "samples", "docs"]
    files_to_copy = [
        "requirements.txt",
        "README.md",
        "run_grid_editor.bat",
        "run_grid_editor.sh"
    ]

    # 复制目录
    for dir_name in dirs_to_copy:
        src_dir = current_dir / dir_name
        if src_dir.exists():
            dst_dir = package_dir / dir_name
            shutil.copytree(src_dir, dst_dir)
            print(f"  [OK] Copied directory: {dir_name}")

    # 复制文件
    for file_name in files_to_copy:
        src_file = current_dir / file_name
        if src_file.exists():
            dst_file = package_dir / file_name
            shutil.copy2(src_file, dst_file)
            print(f"  [OK] Copied file: {file_name}")

    # 创建config目录
    config_dir = package_dir / "config"
    config_dir.mkdir(exist_ok=True)
    print(f"  [OK] Created config directory")

    # 添加配置文件模板
    config_template = {
        "version": "1.0.0",
        "template": True,
        "description": "This file will be generated when you save configurations"
    }

    import json
    with open(config_dir / "config_template.json", "w") as f:
        json.dump(config_template, f, indent=2)
    print(f"  [OK] Created config template")

    # 设置shell脚本执行权限 (Linux/macOS)
    shell_script = package_dir / "run_grid_editor.sh"
    if shell_script.exists():
        try:
            shell_script.chmod(0o755)
            print(f"  [OK] Set execute permission for shell script")
        except:
            print(f"  [WARN] Could not set execute permission (Windows?)")

    # 创建ZIP压缩包
    zip_path = current_dir.parent / f"{package_name}.zip"

    print(f"\nCreating ZIP archive: {zip_path.name}")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(package_dir):
            for file in files:
                file_path = Path(root) / file
                arc_path = file_path.relative_to(package_dir.parent)
                zipf.write(file_path, arc_path)

    zip_size = zip_path.stat().st_size / 1024 / 1024  # MB
    print(f"  [OK] ZIP created: {zip_size:.1f} MB")

    print("\n" + "=" * 50)
    print("  Package Creation Summary")
    print("=" * 50)
    print(f"Package Name: {package_name}")
    print(f"Package Directory: {package_dir}")
    print(f"ZIP Archive: {zip_path}")
    print(f"Total Size: {zip_size:.1f} MB")
    print()
    print("Contents:")
    for item in sorted(package_dir.rglob("*")):
        if item.is_file():
            rel_path = item.relative_to(package_dir)
            size_kb = item.stat().st_size / 1024
            print(f"  {rel_path} ({size_kb:.1f} KB)")

    print("\n[SUCCESS] Package created successfully!")
    print(f"Ready to distribute: {zip_path.name}")
    print(f"Extract and run: run_grid_editor.bat (Windows) or ./run_grid_editor.sh (Linux/macOS)")

    return True

if __name__ == "__main__":
    try:
        success = create_package()
        if not success:
            exit(1)
    except Exception as e:
        print(f"[ERROR] Package creation failed: {e}")
        exit(1)