"""
ArchiveJanitor 单元测试

覆盖：
1. start() 成功创建目录
2. 按日期清理（超过 retention_days 的被删）
3. 水位超标触发降级清理（删最旧的 10%）
4. 水位正常时不降级
5. 空目录 / 不存在目录的优雅处理
6. get_stats 字段完整
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from web.archive_janitor import ArchiveJanitor


def _cfg(tmp_path: Path, **overrides):
    base = dict(
        IMAGE_SAVE_DIR=str(tmp_path),
        archive_retention_days=7,
        archive_disk_warning_pct=90.0,
        archive_janitor_interval_s=999.0,  # 不让循环真的跑
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _touch(path: Path, age_seconds: int = 0):
    """创建文件，并把 mtime 调整到 age_seconds 前"""
    path.write_bytes(b"fake-jpeg")
    if age_seconds > 0:
        past = time.time() - age_seconds
        os.utime(path, (past, past))


def test_start_creates_dir(tmp_path):
    target = tmp_path / "new_arch"
    cfg = _cfg(target)
    j = ArchiveJanitor(cfg)
    j.start()
    try:
        assert target.exists()
    finally:
        j.stop()


def test_clean_by_date(tmp_path):
    cfg = _cfg(tmp_path, archive_retention_days=7)
    # 创建 5 张：3 张新，2 张老（10 天前）
    for i in range(3):
        _touch(tmp_path / f"NORMAL_new_{i}.jpg", age_seconds=0)
    for i in range(2):
        _touch(tmp_path / f"NORMAL_old_{i}.jpg", age_seconds=10 * 86400)

    j = ArchiveJanitor(cfg)
    count = j._clean_by_date()
    assert count == 2
    assert len(list(tmp_path.glob("*.jpg"))) == 3


def test_no_clean_when_all_fresh(tmp_path):
    cfg = _cfg(tmp_path, archive_retention_days=30)
    for i in range(5):
        _touch(tmp_path / f"NORMAL_{i}.jpg", age_seconds=86400)  # 1 天前
    j = ArchiveJanitor(cfg)
    assert j._clean_by_date() == 0
    assert len(list(tmp_path.glob("*.jpg"))) == 5


def test_clean_oldest_percent(tmp_path):
    cfg = _cfg(tmp_path)
    # 创建 10 张，mtime 依次递增
    for i in range(10):
        f = tmp_path / f"NORMAL_{i:02d}.jpg"
        f.write_bytes(b"x")
        past = time.time() - (10 - i) * 3600
        os.utime(f, (past, past))

    j = ArchiveJanitor(cfg)
    deleted = j._clean_oldest_percent(0.10)  # 删除 10% = 1 张
    assert deleted == 1
    # 最老的 00 被删
    assert not (tmp_path / "NORMAL_00.jpg").exists()
    assert (tmp_path / "NORMAL_01.jpg").exists()


def test_clean_oldest_percent_min_one(tmp_path):
    """即使 4×10% = 0.4 < 1，也至少删 1 张"""
    cfg = _cfg(tmp_path)
    for i in range(4):
        _touch(tmp_path / f"X_{i}.jpg")
    j = ArchiveJanitor(cfg)
    deleted = j._clean_oldest_percent(0.10)
    assert deleted == 1


def test_empty_dir_safe(tmp_path):
    cfg = _cfg(tmp_path)
    j = ArchiveJanitor(cfg)
    assert j._clean_by_date() == 0
    assert j._clean_oldest_percent(0.50) == 0


def test_disk_usage_pct_returns_number(tmp_path):
    cfg = _cfg(tmp_path)
    j = ArchiveJanitor(cfg)
    pct = j._get_disk_usage_pct()
    assert 0.0 <= pct <= 100.0


def test_check_and_clean_full_cycle(tmp_path, monkeypatch):
    """端到端：构造一堆过期文件，调用 _check_and_clean"""
    cfg = _cfg(tmp_path, archive_retention_days=7, archive_disk_warning_pct=99.99)

    # 5 新 + 5 旧
    for i in range(5):
        _touch(tmp_path / f"fresh_{i}.jpg", age_seconds=3600)
    for i in range(5):
        _touch(tmp_path / f"old_{i}.jpg", age_seconds=10 * 86400)

    # 让水位不超标，避免触发降级清理
    monkeypatch.setattr(
        ArchiveJanitor, "_get_disk_usage_pct", lambda self: 10.0
    )

    j = ArchiveJanitor(cfg)
    j._check_and_clean()

    stats = j.get_stats()
    assert stats["last_cleaned_by_date"] == 5
    assert stats["last_cleaned_by_size"] == 0
    assert stats["total_cleaned_by_date"] == 5
    # fresh 还在
    assert len(list(tmp_path.glob("fresh_*.jpg"))) == 5


def test_warning_pct_triggers_size_clean(tmp_path, monkeypatch):
    """水位超标触发降级删 10%"""
    cfg = _cfg(tmp_path, archive_retention_days=30, archive_disk_warning_pct=80.0)

    for i in range(10):
        f = tmp_path / f"x_{i:02d}.jpg"
        f.write_bytes(b"x")
        past = time.time() - (10 - i) * 3600
        os.utime(f, (past, past))

    # 返回水位 85% > 80%
    monkeypatch.setattr(ArchiveJanitor, "_get_disk_usage_pct", lambda self: 85.0)

    j = ArchiveJanitor(cfg)
    j._check_and_clean()

    stats = j.get_stats()
    # 日期没过期
    assert stats["last_cleaned_by_date"] == 0
    # 降级删了至少 1 张
    assert stats["last_cleaned_by_size"] >= 1


def test_get_stats_fields(tmp_path):
    cfg = _cfg(tmp_path)
    j = ArchiveJanitor(cfg)
    stats = j.get_stats()
    required = [
        "enabled", "save_dir", "retention_days", "warning_pct",
        "check_interval_s", "last_check_time", "last_disk_usage_pct",
        "last_cleaned_by_date", "last_cleaned_by_size",
        "total_cleaned_by_date", "total_cleaned_by_size",
        "current_disk_usage_pct", "last_error",
    ]
    for k in required:
        assert k in stats, f"缺字段: {k}"
