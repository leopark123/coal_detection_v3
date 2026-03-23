# -*- coding: utf-8 -*-
"""
翻车机积煤检测系统 V3.0 - 项目迁移工具
"""

import os
import shutil
import json
import time
from pathlib import Path

def migrate_project():
    """迁移项目到新电脑"""
    source_dir = Path.cwd()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    migration_dir = source_dir / f"coal_detection_migration_{timestamp}"

    print("="*50)
    print("翻车机积煤检测系统 V3.0 - 项目迁移")
    print("="*50)
    print(f"源目录: {source_dir}")
    print(f"目标包: {migration_dir.name}")
    print()

    # 创建迁移目录
    migration_dir.mkdir(exist_ok=True)

    # 需要迁移的目录
    dirs_to_copy = ["algo", "config", "core", "drivers", "plc", "web", "tools", "tests", "docs"]

    # 需要迁移的文件
    files_to_copy = [
        "main.py", "requirements.txt", "pytest.ini",
        "CLAUDE.md", "README.md", "start_dev.bat",
        "start_prod.bat", "start_web.bat", "start_web_local.bat"
    ]

    copied_count = 0

    # 复制目录
    for dir_name in dirs_to_copy:
        src_dir = source_dir / dir_name
        if src_dir.exists():
            dst_dir = migration_dir / dir_name
            print(f"复制目录: {dir_name}")
            try:
                shutil.copytree(src_dir, dst_dir, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache'))
                copied_count += 1
            except Exception as e:
                print(f"错误: {e}")

    # 复制文件
    for file_name in files_to_copy:
        src_file = source_dir / file_name
        if src_file.exists():
            dst_file = migration_dir / file_name
            print(f"复制文件: {file_name}")
            try:
                shutil.copy2(src_file, dst_file)
                copied_count += 1
            except Exception as e:
                print(f"错误: {e}")

    # 创建logs目录结构（但不复制大文件）
    logs_dir = migration_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    (logs_dir / "images").mkdir(exist_ok=True)

    # 创建logs说明文件
    with open(logs_dir / "images" / "README.txt", "w", encoding="utf-8") as f:
        f.write("报警图像目录\n原系统约有21GB历史数据，迁移时已排除\n新系统会自动在此生成报警图像\n")

    # 创建安装脚本
    install_script = migration_dir / "install_target.bat"
    with open(install_script, "w", encoding="utf-8") as f:
        f.write('''@echo off
echo ==========================================
echo 翻车机积煤检测系统 V3.0 - 安装依赖
echo ==========================================
echo.

echo [1/4] 检查Python环境...
python --version
if errorlevel 1 (
    echo 错误: 未找到Python，请先安装Python 3.10+
    pause
    exit /b 1
)

echo [2/4] 升级pip...
python -m pip install --upgrade pip

echo [3/4] 安装依赖...
pip install -r requirements.txt

echo [4/4] 创建目录...
if not exist "logs" mkdir logs
if not exist "logs\\images" mkdir logs\\images

echo.
echo 安装完成！
echo 开发模式: python main.py --dev
echo 生产模式: python main.py
echo Web界面: http://localhost:8000
pause
''')

    # 创建部署说明
    guide_file = migration_dir / "部署说明.txt"
    with open(guide_file, "w", encoding="utf-8") as f:
        f.write(f'''翻车机积煤检测系统 V3.0 - 部署说明
==========================================

迁移包: {migration_dir.name}
创建时间: {timestamp}

部署步骤:
1. 将整个文件夹复制到目标机器
2. 安装Python 3.10+ (勾选Add to PATH)
3. 运行 install_target.bat 安装依赖
4. 配置网络和硬件连接
5. 运行测试: python main.py --dev
6. 生产启动: python main.py

网络配置:
- 工控机IP: 192.168.1.10
- 相机IP: 192.168.1.100
- PLC IP: 192.168.1.200

生产环境额外依赖:
pip install pypylon pycomm3

Web监控界面:
http://localhost:8000

重要提醒:
- 本系统关联翻车机安全连锁
- 宁可漏报，不可误报
- 配置修改需谨慎测试

详细文档请查看docs目录
''')

    # 计算迁移包大小
    total_size = sum(f.stat().st_size for f in migration_dir.rglob('*') if f.is_file())
    size_mb = total_size / (1024 * 1024)

    print()
    print("="*50)
    print("迁移完成!")
    print("="*50)
    print(f"迁移包位置: {migration_dir}")
    print(f"迁移包大小: {size_mb:.1f} MB")
    print(f"复制项目数: {copied_count}")
    print()
    print("下一步:")
    print("1. 将整个迁移包复制到目标电脑")
    print("2. 按照'部署说明.txt'进行部署")
    print("="*50)

    return migration_dir

if __name__ == "__main__":
    migrate_project()
    input("按Enter键退出...")