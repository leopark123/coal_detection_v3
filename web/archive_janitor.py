"""
归档清理 Janitor

职责：
1. 按保留天数清理过期图像（超过 retention_days 的文件）
2. 按磁盘水位降级清理（超过 warning_pct 时删最旧的 K%）
3. 提供磁盘用量统计

线程模型：
- 单独 daemon 线程周期扫描（默认每小时一次）
- 启动时立即执行一次
- stop() 设置事件退出
"""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger


class ArchiveJanitor:
    """归档文件清理守护线程"""

    # 水位超标时单次清理比例
    DEGRADE_CLEAN_PERCENT = 0.10

    def __init__(self, config):
        """
        Args:
            config: Config，需要字段：
                - IMAGE_SAVE_DIR: 归档目录
                - archive_retention_days: 保留天数
                - archive_disk_warning_pct: 磁盘使用率预警阈值
                - archive_janitor_interval_s: 巡检间隔秒数（默认 3600）
        """
        self.save_dir = Path(getattr(config, "IMAGE_SAVE_DIR", "logs/images"))
        self.retention_days = int(getattr(config, "archive_retention_days", 30))
        self.warning_pct = float(getattr(config, "archive_disk_warning_pct", 85.0))
        self.check_interval_s = float(getattr(config, "archive_janitor_interval_s", 3600.0))

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # 统计
        self._lock = threading.Lock()
        self.last_check_time: Optional[float] = None
        self.last_disk_usage_pct: float = 0.0
        self.total_cleaned_by_date: int = 0
        self.total_cleaned_by_size: int = 0
        self.last_cleaned_by_date: int = 0
        self.last_cleaned_by_size: int = 0
        self.last_error: Optional[str] = None

    def start(self):
        """启动后台线程（如果 save_dir 不存在也先建）"""
        if self._thread is not None and self._thread.is_alive():
            return

        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"[ArchiveJanitor] 无法创建/访问目录 {self.save_dir}: {e}")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="ArchiveJanitor",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            f"[ArchiveJanitor] 启动: dir={self.save_dir}, "
            f"retention={self.retention_days}d, warning={self.warning_pct}%, "
            f"interval={self.check_interval_s}s"
        )

    def stop(self, timeout: float = 3.0):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run_loop(self):
        # 启动立即跑一次（不阻塞主线程过久：放在后台线程内）
        try:
            self._check_and_clean()
        except Exception as e:
            logger.error(f"[ArchiveJanitor] 首次清理异常: {e}")

        while not self._stop_event.is_set():
            self._stop_event.wait(self.check_interval_s)
            if self._stop_event.is_set():
                break
            try:
                self._check_and_clean()
            except Exception as e:
                logger.error(f"[ArchiveJanitor] 周期清理异常: {e}")
                with self._lock:
                    self.last_error = str(e)

    def _check_and_clean(self):
        """检查磁盘水位并清理过期文件"""
        usage_pct = self._get_disk_usage_pct()
        now = time.time()

        # 1. 按日期清理
        cleaned_date = self._clean_by_date()

        # 2. 如果磁盘超水位，再按容量降级清理
        cleaned_size = 0
        if usage_pct > self.warning_pct:
            logger.warning(
                f"[ArchiveJanitor] 磁盘使用率 {usage_pct:.1f}% > {self.warning_pct}%，启动降级清理"
            )
            cleaned_size = self._clean_oldest_percent(self.DEGRADE_CLEAN_PERCENT)

        # 3. 重新统计
        post_usage_pct = self._get_disk_usage_pct()

        with self._lock:
            self.last_check_time = now
            self.last_disk_usage_pct = post_usage_pct
            self.last_cleaned_by_date = cleaned_date
            self.last_cleaned_by_size = cleaned_size
            self.total_cleaned_by_date += cleaned_date
            self.total_cleaned_by_size += cleaned_size
            self.last_error = None

        if cleaned_date or cleaned_size:
            logger.info(
                f"[ArchiveJanitor] 清理完成: 过期{cleaned_date}张 降级{cleaned_size}张, "
                f"磁盘: {usage_pct:.1f}% → {post_usage_pct:.1f}%"
            )

    def _get_disk_usage_pct(self) -> float:
        try:
            anchor = self.save_dir.resolve().anchor or str(self.save_dir.resolve())
            total, used, _free = shutil.disk_usage(anchor)
            return (used / total) * 100.0 if total else 0.0
        except Exception as e:
            logger.debug(f"[ArchiveJanitor] 读取磁盘使用率失败: {e}")
            return 0.0

    def _clean_by_date(self) -> int:
        """删除超过 retention_days 的 .jpg 文件"""
        if self.retention_days <= 0:
            return 0
        cutoff = time.time() - self.retention_days * 86400
        count = 0
        try:
            for f in self.save_dir.glob("*.jpg"):
                try:
                    if f.stat().st_mtime < cutoff:
                        f.unlink()
                        count += 1
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"[ArchiveJanitor] 扫描目录失败: {e}")
        return count

    def _clean_oldest_percent(self, percent: float) -> int:
        """按最旧优先，删除总数 percent 比例的文件"""
        try:
            files = list(self.save_dir.glob("*.jpg"))
        except Exception:
            return 0
        if not files:
            return 0

        # 按 mtime 升序
        files.sort(key=lambda f: f.stat().st_mtime if f.exists() else 0)
        delete_count = max(1, int(len(files) * percent))
        actually_deleted = 0
        for f in files[:delete_count]:
            try:
                f.unlink()
                actually_deleted += 1
            except Exception:
                pass
        return actually_deleted

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            snap = {
                "enabled": self._thread is not None and self._thread.is_alive(),
                "save_dir": str(self.save_dir.resolve()),
                "retention_days": self.retention_days,
                "warning_pct": self.warning_pct,
                "check_interval_s": self.check_interval_s,
                "last_check_time": self.last_check_time,
                "last_disk_usage_pct": round(self.last_disk_usage_pct, 2),
                "last_cleaned_by_date": self.last_cleaned_by_date,
                "last_cleaned_by_size": self.last_cleaned_by_size,
                "total_cleaned_by_date": self.total_cleaned_by_date,
                "total_cleaned_by_size": self.total_cleaned_by_size,
                "last_error": self.last_error,
            }
        # 附加当前即时磁盘水位
        snap["current_disk_usage_pct"] = round(self._get_disk_usage_pct(), 2)
        return snap
