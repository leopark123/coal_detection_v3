#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
翻车机积煤检测系统 V3.0 - 项目迁移工具
=========================================

功能：
1. 智能选择要迁移的文件（排除大型日志文件）
2. 创建目标环境安装脚本
3. 生成详细的迁移报告
4. 验证迁移完整性

作者：Claude Code Assistant
日期：2026-03-19
"""

import os
import shutil
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple
import hashlib

class ProjectMigrator:
    """项目迁移器"""

    def __init__(self, source_dir: str = None):
        self.source_dir = Path(source_dir) if source_dir else Path.cwd()
        self.timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.migration_dir = self.source_dir / f"coal_detection_migration_{self.timestamp}"

        # 需要迁移的核心目录
        self.core_dirs = [
            "algo", "config", "core", "drivers", "plc", "web", "tools",
            "tests", "docs", "GridEditorToolKit"
        ]

        # 需要迁移的根目录文件
        self.core_files = [
            "main.py", "requirements.txt", "pytest.ini", "CLAUDE.md", "README.md",
            "start_dev.bat", "start_prod.bat", "start_web.bat", "start_web_local.bat"
        ]

        # 排除的目录（大文件、临时文件）
        self.exclude_dirs = [
            "logs/images",  # 21GB的报警图像，按需选择性迁移
            "__pycache__",
            ".git",
            "*.pyc",
            ".pytest_cache"
        ]

        self.migration_report = {
            "timestamp": self.timestamp,
            "source_path": str(self.source_dir),
            "target_path": str(self.migration_dir),
            "migrated_files": [],
            "skipped_files": [],
            "errors": [],
            "size_stats": {}
        }

    def calculate_directory_size(self, directory: Path) -> int:
        """计算目录大小"""
        total_size = 0
        try:
            for path in directory.rglob('*'):
                if path.is_file():
                    total_size += path.stat().st_size
        except Exception as e:
            print(f"计算目录大小错误 {directory}: {e}")
        return total_size

    def should_exclude(self, path: Path) -> bool:
        """判断是否应该排除此文件/目录"""
        path_str = str(path.relative_to(self.source_dir))

        for exclude_pattern in self.exclude_dirs:
            if exclude_pattern in path_str:
                return True

        # 排除大型日志文件
        if path.suffix in ['.log'] and path.stat().st_size > 100 * 1024 * 1024:  # >100MB
            return True

        # 排除Python缓存文件
        if path.suffix in ['.pyc', '.pyo']:
            return True

        return False

    def copy_with_verification(self, src: Path, dst: Path) -> bool:
        """复制文件并验证"""
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

            # 验证文件大小
            if src.stat().st_size != dst.stat().st_size:
                raise ValueError(f"文件大小不匹配: {src}")

            return True
        except Exception as e:
            self.migration_report["errors"].append(f"复制失败 {src} -> {dst}: {e}")
            return False

    def migrate_core_files(self):
        """迁移核心文件和目录"""
        print("🚀 开始迁移核心文件...")

        # 创建迁移目录
        self.migration_dir.mkdir(exist_ok=True)

        # 迁移核心目录
        for dir_name in self.core_dirs:
            src_dir = self.source_dir / dir_name
            if src_dir.exists():
                dst_dir = self.migration_dir / dir_name
                print(f"📁 复制目录: {dir_name}")

                try:
                    for src_file in src_dir.rglob('*'):
                        if src_file.is_file() and not self.should_exclude(src_file):
                            rel_path = src_file.relative_to(src_dir)
                            dst_file = dst_dir / rel_path

                            if self.copy_with_verification(src_file, dst_file):
                                self.migration_report["migrated_files"].append(str(src_file.relative_to(self.source_dir)))
                            else:
                                self.migration_report["skipped_files"].append(str(src_file.relative_to(self.source_dir)))

                except Exception as e:
                    self.migration_report["errors"].append(f"目录迁移错误 {dir_name}: {e}")

        # 迁移根目录核心文件
        for file_name in self.core_files:
            src_file = self.source_dir / file_name
            if src_file.exists():
                dst_file = self.migration_dir / file_name
                print(f"📄 复制文件: {file_name}")

                if self.copy_with_verification(src_file, dst_file):
                    self.migration_report["migrated_files"].append(file_name)
                else:
                    self.migration_report["skipped_files"].append(file_name)

    def handle_logs_directory(self):
        """处理日志目录（选择性迁移）"""
        logs_dir = self.source_dir / "logs"
        if not logs_dir.exists():
            return

        print("📊 处理日志目录...")

        # 创建logs目录结构，但不复制大文件
        (self.migration_dir / "logs").mkdir(exist_ok=True)
        (self.migration_dir / "logs" / "images").mkdir(exist_ok=True)

        # 复制小的日志文件（<10MB）
        for log_file in logs_dir.rglob('*.log'):
            if log_file.stat().st_size < 10 * 1024 * 1024:  # <10MB
                rel_path = log_file.relative_to(logs_dir)
                dst_file = self.migration_dir / "logs" / rel_path
                self.copy_with_verification(log_file, dst_file)

        # 创建images目录说明
        readme_content = """# 报警图像目录说明

这个目录在生产环境中会存储报警时的图像快照。

原系统中有约21GB的历史报警图像，为了减少迁移包大小，这些文件没有包含在迁移包中。

如果需要历史数据，请单独传输 logs/images/ 目录。

迁移后系统会自动在此目录创建新的报警图像。
"""
        with open(self.migration_dir / "logs" / "images" / "README.md", "w", encoding="utf-8") as f:
            f.write(readme_content)

    def create_target_install_script(self):
        """创建目标环境安装脚本"""
        print("🛠️  创建目标环境安装脚本...")

        script_content = '''@echo off
chcp 65001 >nul
echo ============================================
echo   翻车机积煤检测系统 V3.0 - 目标环境安装
echo ============================================
echo.

echo [检查] 验证Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version

echo.
echo [安装] 升级pip...
python -m pip install --upgrade pip

echo.
echo [安装] 核心依赖...
pip install -r requirements.txt

echo.
echo [配置] 创建必要目录...
if not exist "logs" mkdir logs
if not exist "logs\\images" mkdir logs\\images

echo.
echo [检查] 验证安装...
python -c "import cv2, numpy, loguru, yaml; print('✓ 核心依赖安装成功')"

echo.
echo ============================================
echo   基础环境安装完成！
echo ============================================
echo.
echo   接下来的步骤：
echo   1. 生产环境: pip install pypylon pycomm3
echo   2. 配置网络: 编辑 config/config_prod.yaml
echo   3. 硬件测试: python tools/hardware_test.py
echo   4. 启动系统: python main.py
echo.
echo   Web监控界面: http://localhost:8000
echo ============================================
pause
'''

        with open(self.migration_dir / "install_target_env.bat", "w", encoding="utf-8") as f:
            f.write(script_content)

    def create_migration_guide(self):
        """创建迁移指南"""
        print("📖 创建迁移指南...")

        guide_content = f"""# 翻车机积煤检测系统 V3.0 - 迁移指南

## 迁移信息
- **迁移时间**: {self.timestamp}
- **源路径**: {self.source_dir}
- **迁移包**: {self.migration_dir.name}

## 快速部署步骤

### 1. 传输文件
将整个 `{self.migration_dir.name}` 文件夹复制到目标机器

推荐路径: `C:\\CoalDetection\\`

### 2. 安装基础环境
```cmd
cd {self.migration_dir.name}
install_target_env.bat
```

### 3. 生产环境额外依赖（如果是工控机）
```cmd
pip install pypylon pycomm3
```

### 4. 硬件连接
- 相机网线 → 工业交换机
- PLC网线 → 工业交换机
- 工控机网线 → 工业交换机

### 5. 网络配置
编辑 `config/config_prod.yaml`：
- 工控机IP: 192.168.1.10
- 相机IP: 192.168.1.100
- PLC IP: 192.168.1.200

### 6. 启动测试
```cmd
# 开发模式测试
python main.py --dev

# 生产模式
python main.py
```

### 7. Web监控
浏览器访问: http://localhost:8000

## 注意事项

### 🚨 重要安全提醒
- 本系统直接关联翻车机安全连锁
- 宁可漏报，不可误报
- 误报积煤可能导致翻车机急停

### 📁 文件说明
- **logs/images/**: 生产环境会自动创建报警图像，原有21GB历史数据未包含
- **config/**: 包含开发和生产环境配置，需根据实际情况修改
- **tests/**: 包含测试数据和测试脚本

### 🔧 硬件要求
- **相机**: Basler GigE 相机 + Pylon SDK
- **PLC**: Allen Bradley CompactLogix 1769-L16ER
- **网络**: 工业以太网交换机

### 📊 性能指标
- 单帧处理延迟: ≤ 80ms
- 端到端延迟: ≤ 150ms
- 跳帧率: ≤ 10%
- 心跳间隔: 500ms ± 50ms

## 故障排查

### 问题1: Python环境
确保安装Python 3.10+，并添加到PATH

### 问题2: 依赖安装失败
```cmd
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
```

### 问题3: 相机连接失败
1. 检查网线连接
2. 检查IP配置
3. 安装Basler Pylon SDK

### 问题4: PLC通信失败
1. 检查网络连通性: ping 192.168.1.200
2. 检查RSLogix 5000配置
3. 验证点位表配置

## 联系支持
如遇问题，请参考 `docs/` 目录下的详细文档。
"""

        with open(self.migration_dir / "迁移指南.md", "w", encoding="utf-8") as f:
            f.write(guide_content)

    def generate_migration_report(self):
        """生成迁移报告"""
        print("📈 生成迁移报告...")

        # 计算统计信息
        migrated_count = len(self.migration_report["migrated_files"])
        skipped_count = len(self.migration_report["skipped_files"])
        error_count = len(self.migration_report["errors"])

        # 计算大小
        migration_size = self.calculate_directory_size(self.migration_dir)
        self.migration_report["size_stats"] = {
            "migration_size_mb": round(migration_size / (1024*1024), 2),
            "migrated_files": migrated_count,
            "skipped_files": skipped_count,
            "errors": error_count
        }

        # 保存详细报告
        report_file = self.migration_dir / "migration_report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(self.migration_report, f, indent=2, ensure_ascii=False)

        # 打印摘要
        print("\n" + "="*60)
        print("🎉 迁移完成！")
        print("="*60)
        print(f"📦 迁移包位置: {self.migration_dir}")
        print(f"📊 迁移包大小: {self.migration_report['size_stats']['migration_size_mb']} MB")
        print(f"✅ 成功迁移: {migrated_count} 个文件")
        if skipped_count > 0:
            print(f"⏭️  跳过文件: {skipped_count} 个")
        if error_count > 0:
            print(f"❌ 错误: {error_count} 个")
        print("="*60)

    def run_migration(self):
        """执行完整迁移流程"""
        print("🔄 开始项目迁移...")
        print(f"源目录: {self.source_dir}")
        print(f"目标目录: {self.migration_dir}")
        print()

        try:
            self.migrate_core_files()
            self.handle_logs_directory()
            self.create_target_install_script()
            self.create_migration_guide()
            self.generate_migration_report()

        except Exception as e:
            print(f"❌ 迁移过程出错: {e}")
            self.migration_report["errors"].append(f"迁移过程出错: {e}")
            return False

        return True

def main():
    """主函数"""
    print("="*60)
    print("🏭 翻车机积煤检测系统 V3.0 - 项目迁移工具")
    print("="*60)

    migrator = ProjectMigrator()
    success = migrator.run_migration()

    if success:
        print("\n🚀 迁移完成！请查看迁移指南进行部署。")
    else:
        print("\n❌ 迁移失败，请检查错误信息。")

    input("\n按Enter键退出...")

if __name__ == "__main__":
    main()