# CODEX V20 审查提示词 — 异步归档实施验证

> 前置：V19 审查已确认"归档消失是 commit 28b34fb 带入的回归"，并在三个方案中推荐 **B7 + 异步化**。
> 本轮审查目标：**验证一次性完整实施后的正确性、线程安全、故障降级、性能、可观测性**。

---

## 一、你是谁 / 目的

你是 CODEX，一位偏保守的工业系统代码审查员。你的任务是**独立审计**本次异步归档的实施结果，并回答以下 12 个检查点。不要信任我的描述，逐项去读代码验证。

---

## 二、新增 / 改动的文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `docs/archive_design.md` | NEW | 设计文档（已 review） |
| `web/archive_worker.py` | NEW | 异步归档 Worker（daemon 线程 + queue.Queue） |
| `web/archive_janitor.py` | NEW | 定时清理守护（retention_days + disk 水位） |
| `core/capture_window.py` | MOD | `feed_result(result, frame=None)` + `_select_representative_frame` + `_enqueue_archive` |
| `web/state_manager.py` | MOD | 初始化/停止 worker+janitor；`_init_funnel` 注入；`_bg_detection_loop` 传 frame |
| `web/unified_app.py` | MOD | 新增 `GET /api/archive/stats` |
| `config/config.py` | MOD | 新增 `archive_*` 字段；`SAVE_ALARM_IMAGES`/`SAVE_INTERVAL_FRAMES` 标 deprecated |
| `config/config_prod.yaml` | MOD | 加 `archive_*` |
| `config/config_dev.yaml` | MOD | 加 `archive_*`（7 天 retention, 600s 巡检） |
| `config/devices_config.py` | MOD | `algo_attrs` 白名单加 `archive_*` |
| `tests/test_archive_worker.py` | NEW | 9 项 |
| `tests/test_archive_janitor.py` | NEW | 10 项 |
| `tests/test_capture_window_archive.py` | NEW | 11 项 |

全量：`137 passed + 9 skipped + 0 failed`。

---

## 三、12 个检查点（请逐项 PASS/FAIL + 证据）

### A 类 — 正确性（必须 PASS）

**A1. 代表帧选择策略是否与设计一致？**
- 读 `core/capture_window.py::_select_representative_frame`
- 报警窗口 → 第一个 `has_coal=True`，reason=`first_alarm`
- 故障窗口 → 第一个 `fault_code != 0`，reason=`first_fault`
- 正常窗口 → 中间帧，reason=`middle`
- 全部无 `frame_ref` → 返回 `(None, {})`，不调用 worker
- 报警但无 `has_coal=True` → 兜底 `fallback_first`

**A2. feed_result 是否向后兼容？**
- 旧调用点 `feed_result(result)`（无 frame）不应该报错
- 新调用点 `feed_result(result, frame=frame)` 应把 frame 存入 `_frame_results[i]["frame_ref"]`

**A3. 窗口完成路径是否都调用了 `_enqueue_archive`？**
- 正常完成路径（投票判定）
- 异常完成路径（强制结束、stop 触发）
- 两条路径**必须**都调用 `_enqueue_archive` 且在 `_notify_complete` **之前**（避免 UI 先收到完成通知但磁盘还没写）

### B 类 — 线程 / 故障安全

**B4. `_enqueue_archive` 的异常隔离是否到位？**
- `worker.enqueue` 抛异常不应传播到采集/判定主循环
- `archive_worker=None` 时不应报错
- 测试：`test_enqueue_archive_worker_exception_isolated` + `test_enqueue_archive_no_worker_noop`

**B5. ArchiveWorker 的反压策略是否正确？**
- 队列满 + 非报警 → `dropped_full++`，直接丢
- 队列满 + 报警 → `_make_room_for_alarm` 淘汰队列中最早的**非报警**，`dropped_non_alarm++`
- 队列满且全是报警 + 新来报警 → `dropped_alarm++`（不挤已入队报警）
- 测试：`test_alarm_evicts_non_alarm_when_full` + `test_queue_full_drops_non_alarm`

**B6. frame 是否做了 copy 隔离？**
- `enqueue` 必须 `frame.copy()`，否则采集线程随后覆盖 buffer 会破坏已入队帧
- 测试：`test_frame_copy_isolation`

**B7. 启动失败是否明确返回 False 且 enqueue 成为 no-op？**
- `_preflight_dir`（或等价逻辑）失败 → `start()` False，`_startup_ok=False`
- 此后 `enqueue` 不 raise，静默丢弃
- 测试：`test_start_fails_on_unwritable_dir`

### C 类 — 清理 / 容量

**C8. Janitor 按日期清理是否精确？**
- `_clean_by_date`：只删 `mtime < now - retention_days * 86400` 的 `.jpg`
- 不删新文件，不删目录
- 测试：`test_clean_by_date` + `test_no_clean_when_all_fresh`

**C9. 水位超标的降级清理是否至少删 1 张？**
- `_clean_oldest_percent(0.10)`：4 张时也必须删 ≥1 张（`max(1, int(n*p))`）
- 删的是 mtime 最小的
- 测试：`test_clean_oldest_percent` + `test_clean_oldest_percent_min_one`

**C10. 水位触发顺序是否正确？**
- `_check_and_clean` 先按日期清，再看水位
- 水位 > `warning_pct` 才触发 `_clean_oldest_percent`
- 测试：`test_check_and_clean_full_cycle` + `test_warning_pct_triggers_size_clean`

### D 类 — 可观测性 / 配置

**D11. `/api/archive/stats` 字段是否齐全？**
- worker: `queue_depth/queue_max, total_saved/alarm_saved/normal_saved/fault_saved, dropped_*, io_errors, last_save_ms, p50_save_ms, p95_save_ms, disk_usage_pct, startup_ok, save_normal, jpeg_quality`
- janitor: `enabled, save_dir, retention_days, warning_pct, check_interval_s, last_check_time, last_disk_usage_pct, last_cleaned_by_date/by_size, total_cleaned_by_date/by_size, current_disk_usage_pct, last_error`
- 测试：`test_stats_fields` + `test_get_stats_fields`

**D12. 配置加载链路是否完整？**
- `config/config.py` 有默认值
- `config/config_prod.yaml` 和 `config_dev.yaml` 都有 `archive_*`
- `config/devices_config.py::build_funnel_config` 的 `algo_attrs` 白名单包含所有 `archive_*`（否则多机配置下会丢失）

---

## 四、期望输出格式

```
## 检查点结果

### A1 代表帧策略
- 结论：PASS / FAIL
- 证据：`core/capture_window.py:XXX-YYY` 第 N 行
- 备注：...

### A2 向后兼容
...

## 总结
- Block（必须修复）：N 项
- Nice-to-have：N 项
- 可合并：YES / NO
```

---

## 五、额外考察（可选，如有发现请单独列）

- **正确性盲点**：有没有边界条件我没覆盖？例如 `_frame_results` 为空、`frame_ref` 为 numpy 视图而非拷贝等
- **资源泄漏**：shutdown 时 worker 线程如果卡在 `queue.get()` 会不会无法退出？是否用了 poison pill 或 timeout？
- **性能隐患**：30 漏斗共享一个 Worker，单线程写盘 p95 可接受吗？是否需要多 Worker？
- **安全**：文件名生成是否对 `funnel_tag` 做了字符白名单校验（避免路径注入）？
- **与 PLC 侧影响**：`_enqueue_archive` 走 `_finalize_window` 路径，是否会延长窗口判定时间从而影响 `Vision_CaptureState=2` 的写入时机？

---

## 六、审查完成后

如果全部 PASS：
1. 在此文件底部追加 `## CODEX V20 结论` 段落
2. 给出"可合并"判定
3. 如有 nice-to-have 改进，单列一节

如果有 Block：
1. 逐项列出修复建议（文件 + 行号 + 具体改法）
2. 不要重写代码，只指路
