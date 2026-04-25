# CODEX 审查提示词 V19 - 报警图像归档功能缺失排查

> 背景：运维巡检发现 `logs/images/` 最新文件停留在 **2026-03-18 13:58:23**，
> 但系统在 2026-04-15 重启后累计产生 10000+ 次报警窗口。
> 初步排查：报警图像保存功能在 `main.py` 归档重构（commit 28b34fb）时遗失。
>
> 本次审查要求：
> 1. 独立验证"主线代码确实没有图像归档"的结论（不采信排查结果）
> 2. 评估三个候选修复方案的优劣
> 3. 给出最终推荐方案（如无异议）
>
> **注意**：本审查仅做代码静态分析，不要求改代码。

---

## 一、问题现象

### 现场观测

- `logs/images/` 目录共 25 个文件，全部写入时间在 **2026-03-18 13:57:12 ~ 13:58:23**（71 秒内）
- 1 张周期帧（`frame_20260318_135712_000000.jpg`）+ 24 张报警帧（`ALARM_20260318_135718_frame000006.jpg` 起）
- 系统 04-15 重启后连续运行 8 天，4000+ 次报警（`报警 100%`），**无任何新增图像**
- CLAUDE.md 中声明的"~74000 张/月, 21GB"与现实严重不符

### 关键时间线（初步结论，需要验证）

```
2026-03-18 13:57  旧 main.py 最后一次运行保存图像
2026-03-19 23:39  生成迁移目录 coal_detection_migration_20260319_233903
(之后)            commit 28b34fb 归档 main.py，移至 scripts/legacy/
                  ImageSaver 类和 SAVE_ALARM_IMAGES 配置保留但未接入新主线
(至今)            统一 Web 主线运行，从不调用 cv2.imwrite
```

---

## 二、审查任务清单（10 项）

### A. 验证"主线无图像归档"（5 项）

**A1. `ImageSaver` 在主线的使用情况**
- 在 `web/`、`algo/`、`core/`、`plc/` 目录下搜索以下关键词：
  - `ImageSaver`（类名）
  - `create_image_saver`（工厂函数）
  - `image_saver`（变量名）
- 预期：主线 0 处匹配，只在 `drivers/`、`non_mainline/history/` 中出现
- 检查方法：
  ```
  grep -rn "ImageSaver\|create_image_saver\|image_saver" \
    web/ algo/ core/ plc/
  ```

**A2. `cv2.imwrite` 在主线的使用情况**
- 在 `web/`、`algo/`、`core/`、`plc/` 目录下搜索 `cv2.imwrite`、`imwrite`
- 预期：主线 0 处匹配
- 如有匹配，记录文件和行号

**A3. 保存相关配置项被读取情况**
- `config/config.py` 中的 `SAVE_ALARM_IMAGES`、`IMAGE_SAVE_DIR`、`SAVE_INTERVAL_FRAMES`
- `config/config_prod.yaml` 中同名字段
- 在主线代码中搜索这些字段是否被读取：
  ```
  grep -rn "SAVE_ALARM_IMAGES\|IMAGE_SAVE_DIR\|SAVE_INTERVAL_FRAMES" \
    web/ algo/ core/ plc/
  ```
- 预期：主线 0 处读取（即使配置项存在，也属于死配置）

**A4. 归档前的 main.py 图像保存位置**
- 打开 `non_mainline/history/scripts/legacy/main.py`，验证：
  - 第 20 行 `from drivers.factory import create_camera, create_plc, create_image_saver`
  - 第 62 行 `image_saver = create_image_saver(config)`
  - 第 139-144 行 `image_saver.save(...)` 调用
- 确认：旧 main.py 在检测循环中调用 `image_saver.save()`，统一主线的 `StateManager` 并未移植此逻辑

**A5. `StateManager.record_detection_result()` 或等价函数**
- 在 `web/state_manager.py` 中找到检测结果处理入口（通常是 `_bg_detection_loop` 或 `detect_device`）
- 确认：处理流程仅包括
  - 更新内存状态
  - 推送 WebSocket
  - 调用 `plc.send_detection_result()`
- 未包含任何磁盘写入（图像/视频）

### B. 评估三个修复方案（3 项）

**B6. 方案 A 评估：在 `state_manager.py` 加 `ImageSaver.save()`**

修复位置：`web/state_manager.py` 的 `_bg_detection_loop()`，在获得检测结果后调用 `ImageSaver.save()`

优劣分析：
- ✅ 改动小，复用现有 `ImageSaver`
- ✅ 每漏斗独立 `ImageSaver` 实例，命名空间清晰
- ❌ 每帧都判断 + 可能每帧都写盘，与采集窗口模式不匹配
- ❌ 30 漏斗扩展时磁盘 I/O 压力大
- ⚠️ 原 main.py 是连续采集模式，新主线是 PLC 窗口采集（每窗口 66-70 帧），语义已变
- 审查要求：评估此方案在当前窗口采集模式下的合理性

**B7. 方案 B 评估：在 `core/capture_window.py` 的 `_finalize_window()` 保存代表帧**

修复位置：`core/capture_window.py::_finalize_window()` 窗口结束时保存 1 张代表帧

候选代表帧选择策略：
- 窗口内第一个有煤帧
- 窗口内投票结果最"强"的帧（置信度最高）
- 窗口中间时刻的帧

优劣分析：
- ✅ 与采集窗口模式一致（1 窗口 = 1 决策 = 1 图像）
- ✅ 磁盘量级可控（~1440 张/天 × 30 漏斗 = 43200 张/天）
- ✅ 图像与 PLC 触发事件严格对齐，易于审计回溯
- ❌ 每窗口内多帧信息损失（但可通过配置调整为 N 张）
- ❌ `_finalize_window()` 现有职责是投票+写 PLC，增加写盘可能影响响应延迟
- 审查要求：评估写盘耗时对 PLC 响应时序的影响（PLC 期望窗口结束 500ms 内完成）

**B8. 方案 C 评估：独立归档线程（异步）**

修复位置：新增 `web/archive_worker.py`，后台线程消费检测结果队列，独立写盘

优劣分析：
- ✅ 完全解耦，不影响主检测/PLC 响应延迟
- ✅ 可实现批量压缩、异步重试、归档策略
- ❌ 开发工作量最大（~1 天）
- ❌ 增加一条新线程，加剧 GIL 压力
- ❌ 需要设计队列溢出、重启恢复等边界情况
- 审查要求：评估 30 漏斗场景下的内存队列设计

### C. 推荐方案与实施建议（2 项）

**C9. 给出最终推荐方案**

请基于 B6/B7/B8 的评估，推荐一个方案，并说明：
- 为何选这个方案
- 针对该方案的缺点如何规避
- 实施步骤（不需要写代码，给出 TODO 列表即可）

**C10. 回归风险评估**

评估修复带来的潜在回归风险：
- 磁盘满载风险（30 漏斗满负荷 30 天估算）
- 写盘失败时的异常处理（ImageSaver 当前无异常处理）
- 权限问题（`logs/images/` 写权限）
- 对主检测循环延迟的影响（benchmark 估算）
- 是否需要配合归档/清理策略（crontab、size-based rotation）

---

## 三、输出格式

```
[A1] [PASS/FAIL]: 验证结论 + 证据路径
[A2] [PASS/FAIL]: ...
...
[B6] 方案 A 综合评分：X/10
[B7] 方案 B 综合评分：X/10
[B8] 方案 C 综合评分：X/10
[C9] 推荐方案：X + 理由
[C10] 风险清单 + 缓解措施

统计：
验证项：A1-A5，PASS X/5
方案评分：B6-B8
推荐：C9
风险：C10

最终结论：
- 排查结论是否准确？
- 推荐方案是否可执行？
- 是否需要先做哪些准备工作？
```

---

## 四、附：关键代码路径（供 CODEX 快速定位）

| 路径 | 作用 |
|------|------|
| `drivers/mock_drivers.py:303-399` | `ImageSaver` 类定义（完整可用，但无人调用） |
| `drivers/factory.py:64-67` | `create_image_saver()` 工厂函数 |
| `drivers/__init__.py:3,9` | `create_image_saver` 在 `__all__` 中导出 |
| `config/config.py:137-139` | `SAVE_ALARM_IMAGES=True` 等配置（死配置） |
| `config/config_prod.yaml:73-75` | 同上 YAML 配置 |
| `web/state_manager.py` | 主线状态管理，**未集成 ImageSaver** |
| `core/capture_window.py::_finalize_window()` | 窗口投票判定，候选修复点 |
| `non_mainline/history/scripts/legacy/main.py:20,62,139-144` | 旧 main.py 的图像保存实现（参考） |
| `logs/images/` | 目标输出目录（仅 25 个 3-18 的文件） |

---

## 五、特别说明

本次审查**不要求输出代码修复**，仅要求：
1. 验证排查结论是否准确
2. 评估三个方案优劣
3. 给出推荐方案

修复实施将在审查通过后作为独立任务执行。
