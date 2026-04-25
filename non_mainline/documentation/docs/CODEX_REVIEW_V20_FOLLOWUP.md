# CODEX V20 追补审查 — A3 复核 + V3.0.13 三项新修复

> 前置：V20 首轮审查给出 12 检查点，11 PASS + 1 Block（A3 零帧完成路径未统一走 `_enqueue_archive`）。
> 首轮审查**未覆盖**文件名格式、路径注入防护、以及 CaptureWindow → ArchiveWorker 的帧引用生命周期。
> 现场联调时发现 Python RSS 从稳态 200MB 涨到 533MB，归因于 `WindowResult.frame_results` 持有整窗大帧。
>
> 本轮审查：**确认 A3 已 PASS，并独立审查 V3.0.13 的 3 项新修复**。

---

## 一、你是谁

你是 CODEX，工业系统代码审查员。本轮只审以下 4 项，每项给 PASS/FAIL + 证据，**最后给"可合并：YES/NO"**。

## 二、新增/改动的 commit

| SHA | 主题 |
|-----|------|
| `61d92be` | fix(archive): 统一零帧完成路径调用 _enqueue_archive (V20 A3) |
| `3394072` | fix(archive): 内存泄漏 + 文件名格式 + 路径注入防护 (V3.0.13) |

## 三、4 项审查点

### F1 — A3 复核：零帧完成路径契约统一

**检查**：`core/capture_window.py` 中所有完成路径（正常/半帧/零帧/安全超时零帧）是否都在 `_notify_complete()` 之前调用了 `_enqueue_archive`。

具体位置：
- 零帧 fail-safe 超时分支（约第 240-252 行）
- `_finalize_window` 的 `total == 0` 分支（约第 359-370 行）
- `_finalize_window` 的"半数以上故障"分支（约第 393-398 行）
- `_finalize_window` 的正常投票分支（约第 448-452 行）

同时确认 CMD_IDLE 下 `_frame_results` 为空（"窗口未成立"路径，约第 263-272 行）**不**归档且有注释说明为什么。

**期望**：PASS（V20 A3 已修复）。

---

### F2 — 内存泄漏修复：`_enqueue_archive` 的 frame_ref 释放

**背景**：`_frame_results` 每窗口 ~68 帧，每帧挂 BGR 5.76MB `frame_ref`。`_finalize_window` 把 `frames` 塞进 `WindowResult.frame_results`，`self.last_window_result` 持有整个 list，**直到下一窗口覆盖**。现场实测涨 ~300MB。

**检查** `core/capture_window.py::_enqueue_archive`（约 493-537 行）：

1. 整体是否用 `try/finally` 包住？
2. `finally` 块里是否**遍历 `frames`** 把 `frame_ref` 置 `None`？
3. 是否在**所有 return 路径**（worker is None / rep_frame is None / enqueue 抛异常 / 正常完成）都会执行清理？
4. 是否对 `f["frame_ref"]` 做了存在性检查（避免 `isinstance`/`get` 出错）？

**额外考察**：
- 清理是否"**破坏了** `WindowResult.frame_results` 的可读性"？（预期：是，但这是设计意图 — frame_results 只是元数据用，frame_ref 本来就不该被读取第二次）
- 有没有办法让 `_frame_results` 一开始就不持有 frame_ref，直接在 feed_result 里代代相传，而不是延迟到 `_enqueue_archive` 清？（讨论即可，不强求改）

**测试**：`tests/test_capture_window_archive.py` 中这 4 个新测试是否足够覆盖：
- `test_enqueue_archive_releases_frame_refs_on_success`
- `test_enqueue_archive_releases_frame_refs_on_worker_exception`
- `test_enqueue_archive_releases_frame_refs_when_worker_none`
- `test_enqueue_archive_releases_frame_refs_when_all_none`

**期望**：PASS。

---

### F3 — 文件名格式：ms + reason 尾段

**背景**：首轮 V20 审查未覆盖文件名格式。现场诊断发现实际命名为 `ALARM_machine-1_funnel-1_20260424_201841.jpg`，缺 ms 和 reason，与 `CLAUDE.md §7.5.3` 规范 `<PREFIX>_<funnel_tag>_<YYYYMMDD_HHMMSS>_<ms>_<reason>.jpg` 不符。

**风险**：同一漏斗同一秒内多次落盘会互相覆盖（极端边界场景：零帧超时 + 正常完成）。reason 丢失 → 数据集筛选无法区分 `first_alarm` / `middle` / `first_fault`。

**检查** `web/archive_worker.py::_save_one`（约 240-255 行）：

1. 文件名格式是否为 `{prefix}_{funnel_tag}_{YYYYMMDD_HHMMSS}_{ms:03d}_{reason}.jpg`？
2. `ms` 从哪来？ 应为 `int((window_end - int(window_end)) * 1000)`。
3. `reason` 从 `metadata["reason"]` 取，缺失默认为 `na`？
4. `ms:03d` 左补 0 确保 3 位（`000`-`999`）？

**测试**：`tests/test_archive_worker.py::test_filename_includes_ms_and_reason` 是否用正则锁定了格式？

**期望**：PASS。

---

### F4 — 路径注入防护：`_sanitize_tag`

**背景**：现场多漏斗场景下 `funnel_tag` 来自 `devices.yaml` 用户配置，恶意 yaml（如 `funnel_tag: "../../etc/passwd"`）会导致 `Path(self.save_dir) / filename` 跳出归档目录，构成 CWE-22 路径遍历。

**检查** `web/archive_worker.py`：

1. 是否定义了 `_sanitize_tag(value, default, max_len)`？位于模块顶层？
2. 正则 `_SAFE_TAG_RE` 是否为 `[^A-Za-z0-9_\-]`（只保留字母数字下划线中划线）？
3. `funnel_tag` 和 `reason` 在拼 filename 前都走一遍 `_sanitize_tag`？
4. `default` 是否合理（funnel_tag 默认 "unknown"，reason 默认 "na"）？
5. `max_len` 防止超长输入 DOS？

**测试**：
- `test_filename_sanitizes_funnel_tag`：`"../../etc/passwd"` 喂进来，落盘必须在 save_dir 下，文件名不含 `/`、`\`、`..`
- `test_filename_sanitizes_missing_reason`：缺 reason 时默认 `na`

**额外考察**：
- `devices_config.py` 里 machine_id / funnel_id 已有 `_VALID_ID` 正则校验，funnel_tag 在 `state_manager.py` 拼接为 `f"{mc.id}_{fc.id}"`，理论上已经安全。`_sanitize_tag` 是**深度防御**的第二道防线。这是合理的"带刺护栏"还是冗余代码？

**期望**：PASS（即使是冗余，加一道防御更安全）。

---

## 四、期望输出

```
## F1 A3 复核
- 结论：PASS / FAIL
- 证据：core/capture_window.py:XXX-YYY
- 备注：...

## F2 内存泄漏修复
...

## F3 文件名格式
...

## F4 路径注入防护
...

## 追加考察
- 是否发现新的盲点/风险（不在 F1-F4 范围内）？
- 有无建议但非必须（nice-to-have）的改进？

## 总结
- Block（必须修复）：N 项
- Nice-to-have：N 项
- **可合并：YES / NO**
- 可 push：YES / NO
```

---

## 五、可选额外考察

- **frame_ref 引用生命周期**：`feed_result` 存的 frame 是从 `_bg_detection_loop` 传来的（`get_latest_frame()` 产物）。这些 frame 的上游是否已做 copy？如果没做，采集循环在 3 秒窗口期间可能覆盖 buffer 而污染已入队的 frame_ref。是否需要在 `feed_result` 入口就做 copy？（权衡：窗口期间 ~N×5.76MB 缓存代价）

- **reason 字段缺失**：正常投票路径（line 448-452）传递的 metadata 里的 reason 来自 `_select_representative_frame` 返回的 `rep_meta` dict。如果选中 `middle`，reason=`middle`；所有路径都有合法 reason。但如果**未来**有人在 `_enqueue_archive` 里漏传 `reason`，会拼出 `_na.jpg`。文件名锁定测试是否足够？

- **性能**：finally 块里的 for-loop 清理是 O(N)，N=68 时大约 ~10 μs，可忽略。但如果将来 N=1000（长窗口）或高帧率，要不要改成批量？

- **30 漏斗规模下**：单 worker 写盘 p95≈19ms。30 漏斗每 30 秒一次窗口 = 1 张/秒落盘，远低于单线程瓶颈，暂无并发隐患。

---

## 六、审查完成后

在本文件底部追加：

```
## CODEX V20 追补审查结论

### F1 A3 复核
...（PASS/FAIL + 证据）

### F2 内存泄漏
...

### F3 文件名格式
...

### F4 路径注入防护
...

### 最终判定
- 可合并：YES / NO
- 可 push：YES / NO
- 备注：...
```
