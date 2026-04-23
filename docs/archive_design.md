# 报警图像归档设计文档 V1.0

> 对应 CODEX V19 审查结论：方案 B（窗口结束保存代表帧）+ 异步化
>
> 状态：设计阶段，待 review → 实施 → CODEX V20 审查

---

## 一、问题背景

### 回归现象

- `logs/images/` 最后一张 `2026-03-18 13:58:23`
- commit `28b34fb` 归档 main.py 时，图像归档链路被遗漏
- 统一 Web 主线（web/state_manager.py + core/capture_window.py）**从未调用** `ImageSaver.save()`

### 影响

- 10000+ 次报警**无图像证据**
- 阈值调优缺少训练数据
- YOLO 升级（方案 C）数据集为零

---

## 二、设计目标

| 目标 | 指标 |
|------|------|
| **功能恢复** | 每个采集窗口产出 1 张代表帧（可配置 0/1/N） |
| **不阻塞主线** | 写盘完全异步，不影响 PLC 响应时序（< 500ms 窗口判定） |
| **磁盘可控** | 30 漏斗 × 1440 窗口/天 = 43200 张/天，配合自动清理控制在目标容量内 |
| **可观测** | 队列深度、落盘耗时、失败数、磁盘水位，都有 API 和日志 |
| **故障降级** | 写盘失败不影响检测，磁盘满时丢弃非报警帧 |
| **30 漏斗就绪** | 所有参数支持 per-funnel 配置 |

---

## 三、总体架构

```
┌─────────────────────────────────────────────────────────────┐
│ core/capture_window.py                                      │
│                                                             │
│  feed_result(result, frame=None)  ← 新增 frame 参数（可选）  │
│    └─ _frame_results.append({                               │
│         "timestamp": ...,                                   │
│         "has_coal": ...,                                    │
│         "frame_ref": frame,       ← 持有候选帧引用          │
│       })                                                    │
│                                                             │
│  _finalize_window()                                         │
│    └─ _select_representative_frame()  ← 选帧策略             │
│    └─ ArchiveWorker.enqueue(frame, metadata)  ← 异步入队    │
│    └─ _notify_complete()  ← 同步回调（不变）                │
└─────────────────────────────────────────────────────────────┘
             │ 异步
             ↓
┌─────────────────────────────────────────────────────────────┐
│ web/archive_worker.py  (新增)                                │
│                                                             │
│  ArchiveWorker 类                                           │
│    - 单独线程消费队列                                        │
│    - queue = Queue(maxsize=配置)                            │
│    - 背压策略：满时丢弃非报警帧，报警帧保留                  │
│    - 使用 ImageSaver.save() 实际写盘                        │
│                                                             │
│  stats:                                                     │
│    - queue_depth                                            │
│    - total_saved / alarm_saved / dropped                    │
│    - last_save_ms / p95_save_ms                             │
│    - io_errors                                              │
│    - disk_usage_pct / disk_warning                          │
└─────────────────────────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────────────┐
│ web/archive_janitor.py  (新增)                               │
│                                                             │
│  ArchiveJanitor 类                                          │
│    - 后台线程周期扫描 logs/images/                          │
│    - 按天轮转（删除超过 retention_days 的文件）              │
│    - 按容量降级（> warning_pct 删最旧）                      │
│    - 日志与告警                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 四、详细设计

### 4.1 capture_window.py 改动

**改动点 1**：`feed_result` 增加 `frame` 参数（向后兼容）

```python
def feed_result(self, result: Dict, frame: Optional[np.ndarray] = None):
    """
    喂入一帧的检测结果（仅 CAPTURING 阶段有效）

    Args:
        result: 检测结果字典
        frame: 可选的原始帧，供窗口结束时归档选帧
    """
    if self._phase != CapturePhase.CAPTURING:
        return

    with self._lock:
        self._frame_results.append({
            "timestamp": time.time(),
            "has_coal": result.get("has_coal", False),
            "coal_grids": result.get("coal_grids", 0),
            "alert_level": result.get("alert_level", "UNKNOWN"),
            "fault_code": result.get("fault_code", 0),
            "frame_ref": frame,  # 持有原始帧引用（numpy view，轻量）
        })
```

**改动点 2**：`_finalize_window` 选帧 + 入队

```python
def _finalize_window(self):
    """窗口结束，汇总投票"""
    with self._lock:
        frames = self._frame_results.copy()

    # ... 原有投票逻辑不变 ...

    # 新增：选代表帧并入队归档
    self._enqueue_archive(frames, result)

    self._notify_complete()

def _enqueue_archive(self, frames, window_result):
    """归档：选代表帧并入队（不阻塞）"""
    if self._archive_worker is None:
        return  # 归档未启用

    rep_frame, rep_meta = self._select_representative_frame(frames, window_result)
    if rep_frame is None:
        return

    self._archive_worker.enqueue(
        frame=rep_frame,
        is_alarm=window_result.is_alarm,
        metadata={
            "funnel_tag": self._funnel_tag,
            "window_start": window_result.window_start,
            "window_end": window_result.window_end,
            "alarm_ratio": window_result.alarm_ratio,
            "confidence": window_result.confidence,
            "fault_code": window_result.fault_code,
            **rep_meta,
        }
    )

def _select_representative_frame(self, frames, window_result):
    """
    代表帧选择策略：
    - 报警窗口：选第一个 has_coal=True 的帧
    - 正常窗口：选窗口中间时刻的帧
    - 故障窗口：选第一个故障帧
    - 无 frame_ref 的帧跳过
    """
    frames_with_ref = [f for f in frames if f.get("frame_ref") is not None]
    if not frames_with_ref:
        return None, {}

    if window_result.is_alarm:
        # 报警：第一个有煤帧
        for f in frames_with_ref:
            if f.get("has_coal"):
                return f["frame_ref"], {"reason": "first_alarm"}
        return frames_with_ref[0]["frame_ref"], {"reason": "fallback_first"}
    elif window_result.fault_code != 0:
        # 故障：第一个故障帧
        for f in frames_with_ref:
            if f.get("fault_code", 0) != 0:
                return f["frame_ref"], {"reason": "first_fault"}
        return frames_with_ref[0]["frame_ref"], {"reason": "fallback_first"}
    else:
        # 正常：中间帧
        mid = frames_with_ref[len(frames_with_ref) // 2]
        return mid["frame_ref"], {"reason": "middle"}
```

**改动点 3**：`CaptureWindowController.__init__` 接受 `archive_worker` 和 `funnel_tag`

```python
def __init__(self, config, plc=None, archive_worker=None, funnel_tag="unknown"):
    ...
    self._archive_worker = archive_worker
    self._funnel_tag = funnel_tag
```

---

### 4.2 web/archive_worker.py（新增）

```python
"""
异步归档 Worker

从 capture_window 接收代表帧，异步写盘。
不阻塞主检测路径和 PLC 响应。
"""

class ArchiveWorker:
    def __init__(self, config):
        self.config = config
        self.queue = queue.Queue(maxsize=config.archive_queue_max)
        self.saver = ImageSaver(config)

        # 监控统计
        self.total_saved = 0
        self.alarm_saved = 0
        self.dropped_non_alarm = 0
        self.dropped_full = 0
        self.io_errors = 0
        self.last_save_ms = 0.0
        self.recent_save_ms = deque(maxlen=100)  # 最近100次耗时

        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        """启动后台线程"""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run_loop, name="ArchiveWorker", daemon=True
        )
        self._thread.start()

    def stop(self, timeout=5.0):
        """停止（等待队列清空）"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout)

    def enqueue(self, frame, is_alarm, metadata):
        """
        入队（非阻塞）

        背压策略：
        - 队列满 + 报警帧：强制丢弃最旧的非报警帧腾位
        - 队列满 + 非报警帧：直接丢弃
        """
        item = {
            "frame": frame.copy() if frame is not None else None,
            "is_alarm": is_alarm,
            "metadata": metadata,
            "enqueue_time": time.time(),
        }

        try:
            self.queue.put_nowait(item)
        except queue.Full:
            if is_alarm:
                # 报警帧必须保留：尝试丢弃一个非报警
                if self._make_room_for_alarm():
                    try:
                        self.queue.put_nowait(item)
                        return
                    except queue.Full:
                        pass
            self.dropped_full += 1
            if is_alarm:
                self.dropped_alarm = getattr(self, 'dropped_alarm', 0) + 1
                logger.warning(f"[ArchiveWorker] 队列满，丢失报警帧")

    def _make_room_for_alarm(self):
        """尝试从队列中移除一个非报警帧"""
        # 遍历队列，移除第一个非报警帧
        try:
            items = []
            while not self.queue.empty():
                items.append(self.queue.get_nowait())
            removed = False
            for item in items:
                if not removed and not item["is_alarm"]:
                    removed = True
                    self.dropped_non_alarm += 1
                    continue
                try:
                    self.queue.put_nowait(item)
                except queue.Full:
                    pass
            return removed
        except Exception:
            return False

    def _run_loop(self):
        """消费循环"""
        while not self._stop_event.is_set():
            try:
                item = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                t0 = time.perf_counter()
                self._save_item(item)
                elapsed_ms = (time.perf_counter() - t0) * 1000
                self.last_save_ms = elapsed_ms
                self.recent_save_ms.append(elapsed_ms)
            except Exception as e:
                self.io_errors += 1
                logger.error(f"[ArchiveWorker] 写盘失败: {e}")

    def _save_item(self, item):
        """调用 ImageSaver 写盘"""
        frame = item["frame"]
        metadata = item["metadata"]
        is_alarm = item["is_alarm"]

        if frame is None:
            return

        # 构造文件名：funnel_tag + 时间戳 + 报警标记
        funnel_tag = metadata.get("funnel_tag", "unknown")
        ts = time.strftime("%Y%m%d_%H%M%S",
                           time.localtime(metadata.get("window_end", time.time())))
        prefix = "ALARM" if is_alarm else "NORMAL"
        filename = f"{prefix}_{funnel_tag}_{ts}.jpg"

        save_dir = Path(self.saver.save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        filepath = save_dir / filename

        # 标注元数据到图像
        annotated = self._annotate(frame, metadata, is_alarm)

        # 写盘（可能抛异常，由外层 try 捕获）
        ok = cv2.imwrite(str(filepath), annotated,
                         [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise IOError(f"cv2.imwrite 返回 False: {filepath}")

        self.total_saved += 1
        if is_alarm:
            self.alarm_saved += 1

    def _annotate(self, frame, metadata, is_alarm):
        """在图像上标注检测信息"""
        # 类似 ImageSaver._annotate_result，但附加漏斗信息
        ...

    def get_stats(self):
        """获取归档统计"""
        p95 = 0.0
        if self.recent_save_ms:
            sorted_ms = sorted(self.recent_save_ms)
            p95 = sorted_ms[int(len(sorted_ms) * 0.95)]

        return {
            "queue_depth": self.queue.qsize(),
            "queue_max": self.config.archive_queue_max,
            "total_saved": self.total_saved,
            "alarm_saved": self.alarm_saved,
            "dropped_non_alarm": self.dropped_non_alarm,
            "dropped_full": self.dropped_full,
            "io_errors": self.io_errors,
            "last_save_ms": round(self.last_save_ms, 2),
            "p95_save_ms": round(p95, 2),
        }
```

---

### 4.3 web/archive_janitor.py（新增）

```python
"""
归档清理 Janitor

定时清理过期图像，防止磁盘满。
策略：
1. 按天清理：删除超过 retention_days 的文件
2. 按容量降级：如果磁盘使用率 > warning_pct，删除最旧的 K%
"""

class ArchiveJanitor:
    def __init__(self, config):
        self.save_dir = Path(config.IMAGE_SAVE_DIR)
        self.retention_days = config.archive_retention_days
        self.warning_pct = config.archive_disk_warning_pct
        self.check_interval_s = 3600  # 每小时巡检一次

        self._stop_event = threading.Event()
        self._thread = None

        # 统计
        self.last_check_time = None
        self.total_cleaned = 0
        self.last_disk_usage_pct = 0.0

    def start(self):
        self._thread = threading.Thread(
            target=self._run_loop, name="ArchiveJanitor", daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _run_loop(self):
        # 启动立即跑一次
        self._check_and_clean()

        while not self._stop_event.is_set():
            self._stop_event.wait(self.check_interval_s)
            if self._stop_event.is_set():
                break
            self._check_and_clean()

    def _check_and_clean(self):
        """检查并清理"""
        try:
            # 1. 检查磁盘水位
            usage_pct = self._get_disk_usage_pct()
            self.last_disk_usage_pct = usage_pct
            self.last_check_time = time.time()

            if usage_pct > self.warning_pct:
                logger.warning(
                    f"[ArchiveJanitor] 磁盘使用率 {usage_pct:.1f}% > "
                    f"预警阈值 {self.warning_pct}%，启动降级清理"
                )

            # 2. 按日期清理（保留 retention_days 天）
            cleaned_by_date = self._clean_by_date()

            # 3. 如果还超水位，按容量删最旧
            if usage_pct > self.warning_pct:
                cleaned_by_size = self._clean_oldest_percent(0.10)
            else:
                cleaned_by_size = 0

            total_cleaned = cleaned_by_date + cleaned_by_size
            self.total_cleaned += total_cleaned

            if total_cleaned > 0:
                logger.info(
                    f"[ArchiveJanitor] 清理完成: 过期{cleaned_by_date}张, "
                    f"降级{cleaned_by_size}张, 磁盘{usage_pct:.1f}%"
                )

        except Exception as e:
            logger.error(f"[ArchiveJanitor] 清理异常: {e}")

    def _get_disk_usage_pct(self):
        """获取归档目录所在磁盘使用率"""
        import shutil
        total, used, free = shutil.disk_usage(str(self.save_dir.resolve().anchor))
        return (used / total) * 100

    def _clean_by_date(self):
        """删除超过 retention_days 的文件"""
        cutoff = time.time() - self.retention_days * 86400
        count = 0
        for f in self.save_dir.glob("*.jpg"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    count += 1
            except Exception:
                pass
        return count

    def _clean_oldest_percent(self, percent):
        """删除最旧的 percent 比例文件"""
        files = sorted(
            self.save_dir.glob("*.jpg"),
            key=lambda f: f.stat().st_mtime
        )
        delete_count = int(len(files) * percent)
        for f in files[:delete_count]:
            try:
                f.unlink()
            except Exception:
                pass
        return delete_count

    def get_stats(self):
        return {
            "enabled": True,
            "retention_days": self.retention_days,
            "warning_pct": self.warning_pct,
            "last_check_time": self.last_check_time,
            "last_disk_usage_pct": round(self.last_disk_usage_pct, 2),
            "total_cleaned": self.total_cleaned,
        }
```

---

### 4.4 StateManager 集成改动

```python
# __init__
self.archive_worker: Optional[ArchiveWorker] = None
self.archive_janitor: Optional[ArchiveJanitor] = None

# initialize
if self.base_config.archive_enable:
    self.archive_worker = ArchiveWorker(self.base_config)
    self.archive_worker.start()
    self.archive_janitor = ArchiveJanitor(self.base_config)
    self.archive_janitor.start()

# _init_funnel，创建 CaptureWindowController 时传入
fs.capture_controller = CaptureWindowController(
    cap_cfg,
    plc=ms.plc,
    archive_worker=self.archive_worker,
    funnel_tag=f"{mc.id}_{fc.id}",
)

# _bg_detection_loop，feed_result 传入 frame
cc.feed_result({...}, frame=frame)
```

---

### 4.5 配置项（config.py 新增）

```python
# ═══════════════════════════════════════════════════════════════
# 归档设置
# ═══════════════════════════════════════════════════════════════
archive_enable: bool = True                    # 总开关
archive_queue_max: int = 200                   # 入队上限
archive_retention_days: int = 30               # 保留天数
archive_disk_warning_pct: float = 85.0         # 磁盘预警阈值
archive_save_normal: bool = True               # 是否保存正常窗口（False=仅报警）
archive_jpeg_quality: int = 85                 # JPEG 压缩质量
```

保留旧的 `SAVE_ALARM_IMAGES`、`IMAGE_SAVE_DIR`、`SAVE_INTERVAL_FRAMES` 字段以保持向后兼容，但标记为 deprecated。

---

### 4.6 API 端点（unified_app.py 新增）

```python
@app.get("/api/archive/stats")
async def api_archive_stats():
    """归档统计"""
    if not state_manager.archive_worker:
        return {"enabled": False}

    return {
        "enabled": True,
        "worker": state_manager.archive_worker.get_stats(),
        "janitor": (state_manager.archive_janitor.get_stats()
                    if state_manager.archive_janitor else {"enabled": False}),
    }
```

---

## 五、30 漏斗规模校验

| 场景 | 数值 |
|------|------|
| 每窗口图像数 | 1 张 |
| 每漏斗窗口/天 | 1440（~60s/窗口） |
| 30 漏斗/天 | 43200 张 |
| 单张大小（JPEG 85%） | ~200KB |
| 每日磁盘增量 | ~8.6 GB |
| 30 天保留 | ~258 GB |
| 当前磁盘余量 | 663 GB |
| 水位 | 258/663 ≈ 38.9%（正常） |

**结论**：30 漏斗 + 30 天保留，磁盘占用约 260GB，当前硬件完全可承受。

---

## 六、故障场景与应对

| 故障场景 | 应对 |
|---------|------|
| 队列满 + 报警帧 | 丢弃最旧非报警帧腾位；若全是报警则丢弃最新非报警帧 |
| 队列满 + 非报警 | 直接丢弃，计数 `dropped_non_alarm++` |
| 磁盘写失败 | try/except，`io_errors++`，不影响检测循环 |
| 磁盘 > 85% | Janitor 删最旧 10% 图像 |
| 磁盘 > 95% | Worker 停止写盘（仅报警），Janitor 紧急清理 |
| 目录不存在 | Worker 启动时 mkdir，失败则禁用归档 |
| 目录不可写 | Worker 启动时预检，失败则禁用归档，发日志 |
| 权限问题 | 同上 |
| Worker 崩溃 | 看门狗日志告警；不影响主进程 |

---

## 七、回归测试清单

| 测试项 | 验证目标 |
|--------|---------|
| feed_result 无 frame | 旧用法仍工作（向后兼容） |
| 窗口结束无 frame | 归档跳过，不崩溃 |
| Worker 正常消费 | 队列深度周期归零 |
| Worker 队列满 | 非报警被丢弃，报警保留 |
| Worker 写盘失败 | io_errors 正确计数 |
| Janitor 日期清理 | 超过 retention_days 的文件被删 |
| Janitor 水位清理 | 水位 > 85% 时触发清理 |
| 磁盘只读 | 归档自动禁用，主检测不崩 |
| 关闭 Worker | 队列残余数据能被消费完 |
| Stats API | 所有字段正确 |

---

## 八、实施顺序

```
阶段 1: 核心归档（capture_window + archive_worker + saver 改造）
  ├─ 扩展 feed_result 签名
  ├─ 扩展 _frame_results schema
  ├─ 新增 _select_representative_frame + _enqueue_archive
  ├─ 新增 web/archive_worker.py
  └─ StateManager 集成（创建 worker + 传参）

阶段 2: 磁盘轮转与水位监控
  └─ 新增 web/archive_janitor.py

阶段 3: 监控指标 + API
  └─ unified_app.py 新增 /api/archive/stats

阶段 4: 配置项
  ├─ config.py 新增字段
  ├─ devices_config.py 加入 allow list
  └─ config_prod.yaml 示例

阶段 5: 测试
  ├─ test_archive_worker.py（队列/丢弃/异常）
  ├─ test_archive_janitor.py（清理/水位）
  └─ test_capture_window_archive.py（选帧策略）

阶段 6: 文档
  ├─ CLAUDE.md 更新架构
  ├─ README.md 更新配置
  └─ 生成 CODEX V20 审查提示词
```

---

## 九、审查要点（供 CODEX V20）

1. 选帧策略是否合理（报警/故障/正常各自选取）
2. 队列背压策略是否能保证报警帧不丢
3. 磁盘清理策略是否够激进（水位回退速度）
4. 异步化是否彻底（主路径延迟 < 10ms）
5. 配置项默认值是否合适
6. 单元测试覆盖率

---

## 十、不做的事（Out of Scope）

- 不做视频录制（仅图像）
- 不做远程归档（S3/NFS）
- 不做压缩归档（zip/tar）
- 不做检测元数据落库（PostgreSQL），仅写 JPEG
- 不做图像内容加密
- 不改 `ImageSaver` 的原始接口（保持向后兼容）
