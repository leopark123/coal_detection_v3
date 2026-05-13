# CODEX V21 审查 — 归档回退后的全项目审查

> 时间：2026-04-25
> 审查目标分支：`feature/project-restructure`
> 审查目标 HEAD：`f0e3a0b`（等价于 `a4f9ccc fix(plc): 心跳线程保活IPC_Online + 锁内写入修复`）
> 前置：上一次完整闭环审查是 **V18**（心跳/IPC_Online 保活）。V19-V20 的归档分支已被 revert（不在审查范围）。
> 自审查报告：`docs/SELF_REVIEW_POST_REVERT.md`（先读这份再开始）

---

## 一、你是谁 / 角色

你是 CODEX，工业系统代码审查员。本系统是**煤矿翻车机积煤检测**，直接关联翻车机安全连锁。审查原则：**宁可漏报（人工确认），不可误报（积煤未清卡住设备）**。

**重要**：本轮审查不要重复审查 V18 之前已闭环的内容（C1-C6 / H1-H13 / M1-M8 / R1-R9）。本轮只审查：

1. **回退是否干净**（归档代码已完整移除）
2. **当前 HEAD 状态是否符合 `a4f9ccc` 基线**
3. **新发现/未解决的问题**（特别是用户报告的"刷新内存暴涨"）
4. **可合并性 / 可 push 性**

---

## 二、审查清单（13 项）

### Section A — 回退完整性（P0，必须 PASS）

#### A1. Git 历史完整性
- 验证：`git log --oneline a4f9ccc..HEAD` 应只见 6 个 commit（3 个归档 feat/fix + 3 个 revert，互相抵消）
- `git diff a4f9ccc..HEAD` 应为空
- 报告：是否真等价

#### A2. 主线代码已无归档痕迹
逐项 grep 验证：
- `web/archive_worker.py` 应不存在
- `web/archive_janitor.py` 应不存在
- `tests/test_archive_worker.py` 应不存在
- `tests/test_archive_janitor.py` 应不存在
- `tests/test_capture_window_archive.py` 应不存在
- `core/capture_window.py::feed_result` 签名应为 `def feed_result(self, result: Dict):`（无 frame 参数）
- `core/capture_window.py::_enqueue_archive` 应不存在
- `core/capture_window.py::_select_representative_frame` 应不存在
- `web/state_manager.py` 不应有 `archive_worker` / `archive_janitor` 字段或调用
- `web/unified_app.py` 不应有 `/api/archive/stats` 端点

#### A3. 配置层是否清理
**已知遗留**（自审查 B2 项）：
- `config/config.py:137-139` 仍保留 `SAVE_ALARM_IMAGES / SAVE_INTERVAL_FRAMES / IMAGE_SAVE_DIR`
- `config_dev.yaml:71-73` / `config_prod.yaml:73-75` 同样
- 主线**无消费方**

**问题**：这些字段是否真完全无消费方？是否有可能 Mock 驱动或其他历史路径还在偷偷读？请 grep 全项目验证：

```
grep -rn "SAVE_ALARM_IMAGES" .
grep -rn "SAVE_INTERVAL_FRAMES" .
grep -rn "IMAGE_SAVE_DIR" .
grep -rn "image_saver\|ImageSaver\|create_image_saver" .
```

期望：所有命中**仅在** `drivers/__init__.py / drivers/factory.py / drivers/mock_drivers.py / config/*.py / config/*.yaml` 内（即 B1+B2 自审查列出的范围），不应出现在 `web/`, `core/`, `algo/`, `plc/` 主线代码。

如果有泄漏到主线，列出文件+行号。

#### A4. 死代码 ImageSaver 残留
位置：
- `drivers/__init__.py:3` 导出 `create_image_saver`
- `drivers/factory.py:64-67` `create_image_saver()` 工厂
- `drivers/mock_drivers.py:303-399` `MockImageSaver` 类

判定：
- 是否真的无任何引用？
- 保留还是删除？保留作为"未来归档接入点"是否值得（vs 误导新人）？
- 建议：明确表态。

---

### Section B — 已知问题验证（P0，可能 FAIL）

#### B5. 用户报告的"刷新内存暴涨"问题在回退后是否仍然存在？

**背景**：在归档 V3.0.13（PID 4796）运行期间，用户观察到刷新浏览器页面时 RSS 从 177 → 383MB（+206MB / 12分钟），尔后回到 174MB。归档代码理论上不参与刷新路径，所以**回退后该问题大概率仍在**。

**审查任务**（你不需要联机复现，只审代码）：
读以下文件并评估每个嫌疑点：

1. **`web/unified_app.py::funnel_ws`**（约 196-269 行）
   - 5 FPS 循环里 `vis = fs.detector.visualize_device(frame, result)` 是否每次返回新 ndarray？
   - 旧 `vis` 是否会被 GC？
   - `encode_frame_jpeg_base64(vis, quality=85)` 每 200ms 一次产 base64 字符串，浏览器刷新后旧连接的 task 是否立即取消？

2. **`web/unified_app.py::overview_ws`**（约 174-193 行）
   - 客户端断开是否准确触发 `WebSocketDisconnect`？
   - 异常分支是否会泄漏？

3. **`web/unified_app.py::api_snapshot`**（约 446-457 行）
   - 每次请求 `cv2.imencode + tobytes` 的内存生命周期
   - 高频请求是否在 GC 间累积

4. **`web/state_manager.py::FunnelState.last_frame`**
   - 写入端（采集线程）和读出端（WS / snapshot）的访问模式
   - 是否有"读端持有引用导致写端旧 frame 不能被 GC"

5. **`web/common.py::encode_frame_jpeg_base64`**
   - 内部是否有缓存？
   - cv2.imencode 是否使用 memoryview 而非 copy？

请给出：
- 哪个嫌疑点最可能是真凶？
- 哪些只是无害的瞬时分配（GC 后回落）？
- **是否需要 reproduce 实验来确证**？（建议的实验设计：N 次 GET / 后 RSS 是否回到 baseline）

#### B6. 多漏斗共享 PLC 标签的限制（L1）

`core/capture_window.py` 是 per-funnel 实例，但 PLC 标签 `Vision_CaptureState` / `PLC_CaptureCmd` 是 per-machine 全局。

- 当 1 台翻车机有 N 个漏斗（N≥2）时，会发生什么？
- 当前 `state_manager.py` 给每个 funnel 都创建了 `CaptureWindowController`，多个 controller 是否互相覆盖 `Vision_CaptureState`？
- 现状缓解：machine-1 实际只接 funnel-1 一台相机
- 上线第 2 台相机前必修。请确认风险描述准确，并给出最小修法草图（**不要写实际代码**，只点路径）。

#### B7. logger 级别硬编码

`web/unified_app.py:39` 是否仍是 `logger.add(..., level="DEBUG")` 写死？应该读 `config.LOG_LEVEL`（dev=DEBUG, prod=INFO）。

如果是，给出修法。

---

### Section C — 安全连锁不变量（P0，必须 PASS）

#### C8. `Vision_CanTip` 判定逻辑
读 `plc/allen_bradley.py`，验证：
```python
can_tip = (coal_present is False) and (not need_manual) and (fault_code == 0)
```
- `coal_present is None` 时是否严格 `False`？
- `coal_present is True` 时是否严格 `False`？
- 任何 `fault_code != 0` 时是否严格 `False`？
- `confidence == "LOW"` 且 `need_manual=True` 时是否严格 `False`？

#### C9. 心跳保活
读 `plc/allen_bradley.py` 心跳线程：
- 周期是否 500ms？
- `IPC_Heartbeat` 是否在 `_io_lock` 下递增写入？
- `IPC_Online` 是否在心跳每周期保活（V18 修复点）？
- 启动 `IPC_Online=True`，shutdown `IPC_Online=False`？

#### C10. 三把锁的保护边界
- `_io_lock` 保护范围：所有 `self.plc.read()/write()` 调用？
- `_heartbeat_value_lock`：心跳值读-改-写？
- `_reconnect_lock`：替换 `self.plc` 引用的整个过程？
- 心跳线程递增 + 写入是否都在 `_io_lock` 下？

#### C11. 故障路径下 fail-safe
- 相机断线 → `Vision_FaultCode=1` + `Vision_CanTip=False`
- PLC 通信失败 → 内部状态正确（不会写入旧值）
- 画质失败 → `Vision_FaultCode=3` + `Vision_CanTip=False`
- 低置信度 → `Vision_FaultCode=4` + `need_manual=True` + `Vision_CanTip=False`
- 零帧窗口 → 仍写 fail-safe 故障码

---

### Section D — 文档与可观测性（P1）

#### D12. 主线 docs/ 是否包含已废弃的归档文档？
应该清理：
- `docs/archive_design.md`
- `docs/CODEX_REVIEW_V19_IMAGE_ARCHIVAL.md`
- `docs/CODEX_REVIEW_V20_ARCHIVE.md`
- `docs/CODEX_REVIEW_V20_FOLLOWUP.md`

建议：移到 `non_mainline/documentation/docs/archive/` 而非删除（保留尝试历史）。

#### D13. 临时文件是否未清理
项目根可能残留：
- `_commit_msg.txt / _step1_status.txt / _step2_diffstat.txt / _step3_add.txt / _revert3.txt / diff_c.txt`
- `_post_revert_run.log` 等

应清理。

---

## 三、期望输出格式

```
# CODEX V21 审查结论

## A 类 - 回退完整性
### A1 git 历史
- 结论：PASS / FAIL
- 证据：...
### A2 主线代码已无归档痕迹
...
### A3 配置层清理
...
### A4 死代码 ImageSaver
...

## B 类 - 已知问题
### B5 刷新内存暴涨根因分析
...
### B6 多漏斗 PLC 标签限制
...
### B7 logger 级别硬编码
...

## C 类 - 安全连锁
### C8 Vision_CanTip
...
### C9 心跳保活
...
### C10 三把锁
...
### C11 fail-safe
...

## D 类 - 文档与可观测性
### D12 docs/ 清理
...
### D13 临时文件清理
...

## 追加发现
（不在 A-D 范围内的新风险）

## 总结
- Block（必须修复）：N 项 + 列表
- Nice-to-have：N 项 + 列表
- **可 push 到 origin？YES / NO**
- **可合并到 main？YES / NO**
- **若不可合并，最少必须修哪几项？**
```

---

## 四、审查约束

1. 不要重复审查 V18 之前已闭环的 C1-C6 / H1-H13 / M1-M8 / R1-R9 项（除非你发现退化）
2. 不要写实际代码修复，只点出路径 + 修法描述
3. **必须**在结论里给出明确的"可 push / 可合并"判定，不要模糊表述
4. 如果 B5（刷新内存暴涨）你认为只能通过实验确证，明确说"无法在静态审查得出结论，需要 reproduce 实验"
5. 重点关注**回退后的隐蔽残留**（A2/A3/A4）和**已知未修问题**（B5-B7），这两类是本轮的核心价值

---

## 五、上下文文件清单

审查时必读：

| 文件 | 用途 |
|------|------|
| `CLAUDE.md` | 项目规范（你已经在 system reminder 看到） |
| `README.md` | 部署 / 安全原则 / 65 个修复总览 |
| `docs/SELF_REVIEW_POST_REVERT.md` | 我的自审查报告（先看这份获得鸟瞰） |
| `non_mainline/documentation/docs/整改记录与已知限制.md` | 累计修复 + L1-L10 已知限制 |
| `non_mainline/documentation/docs/CODEX_FINAL_REVIEW.md` | 60 项累计修复全面审查（V16 闭环） |
| `core/capture_window.py` | 状态机（重点 feed_result / _finalize_window） |
| `web/state_manager.py` | FunnelState / 后台采集线程 |
| `web/unified_app.py` | WS / API 路由（B5 重点） |
| `web/common.py` | WS 推流 / JPEG 编码（B5 重点） |
| `plc/allen_bradley.py` | PLC 通信 + 心跳 + 三锁（C8-C11 重点） |

---

## 六、参考：自审查已识别的问题

为避免你重复劳动，我已经在 `docs/SELF_REVIEW_POST_REVERT.md` 第三节列了 13 项问题（A1-A3, B1-B5, C1-C4, D1-D4）。请：

- 对每项**独立验证**（不要照抄我的结论）
- 找出我**漏掉的问题**
- 对我列的问题，给出**严重度评估**（我可能高估或低估）

---

## 七、审查完成后

在本文件底部追加：

```
## CODEX V21 审查结论

### Section A 回退完整性
- A1: PASS/FAIL + 证据
- A2: ...
- A3: ...
- A4: ...

### Section B 已知问题
- B5: ...
- B6: ...
- B7: ...

### Section C 安全连锁
- C8: ...
- C9: ...
- C10: ...
- C11: ...

### Section D 文档可观测性
- D12: ...
- D13: ...

### 追加发现
...

### 最终判定
- 可 push: YES/NO
- 可合并 main: YES/NO
- Block: [...]
- Nice-to-have: [...]
- 备注: ...
```
