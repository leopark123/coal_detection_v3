#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
临时禁用MockCamera的随机变化（调试用）
"""

import os
import sys
from pathlib import Path

def disable_mock_variations():
    """禁用MockCamera的随机变化"""
    mock_file = Path("drivers/mock_drivers.py")

    if not mock_file.exists():
        print(f"[ERROR] 找不到文件: {mock_file}")
        return False

    print("=" * 60)
    print("  临时禁用MockCamera随机变化")
    print("=" * 60)

    # 备份原文件
    backup_file = mock_file.with_suffix(".py.backup")
    import shutil
    shutil.copy(mock_file, backup_file)
    print(f"[INFO] 已备份原文件: {backup_file}")

    # 读取文件内容
    with open(mock_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 注释掉随机变化的代码
    replacements = [
        ("frame = self._add_timestamp(frame)", "# frame = self._add_timestamp(frame)  # 临时禁用"),
        ("frame = self._add_jitter(frame)", "# frame = self._add_jitter(frame)  # 临时禁用"),
        ("frame = self._add_sensor_noise(frame)", "# frame = self._add_sensor_noise(frame)  # 临时禁用"),
    ]

    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            print(f"[INFO] 已禁用: {old}")
        else:
            print(f"[WARNING] 未找到: {old}")

    # 写回文件
    with open(mock_file, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"[SUCCESS] 已禁用MockCamera随机变化")
    print(f"[INFO] 现在每次检测结果将完全相同")
    print(f"[INFO] 恢复方法: 用 {backup_file} 覆盖 {mock_file}")
    print("=" * 60)

    return True

def restore_mock_variations():
    """恢复MockCamera的随机变化"""
    mock_file = Path("drivers/mock_drivers.py")
    backup_file = mock_file.with_suffix(".py.backup")

    if not backup_file.exists():
        print(f"[ERROR] 找不到备份文件: {backup_file}")
        return False

    import shutil
    shutil.copy(backup_file, mock_file)
    backup_file.unlink()  # 删除备份

    print(f"[SUCCESS] 已恢复MockCamera随机变化")
    return True

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "restore":
        restore_mock_variations()
    else:
        disable_mock_variations()
        print("\n[USAGE] 恢复随机变化:")
        print("python disable_mock_variations.py restore")