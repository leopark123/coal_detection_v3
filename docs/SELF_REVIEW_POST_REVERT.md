# 自审查报告 — 归档功能回退后

> 时间：2026-04-25
> HEAD 等价基线：`a4f9ccc fix(plc): 心跳线程保活IPC_Online + 锁内写入修复`
> 工作分支：`feature/project-restructure`（领先 origin 11 个 commit，含 6 个归档实施 + 3 个归档 revert）
> 本轮回归：107 passed + 9 skipped + 0 failed

---

## 一、当前主线状态

### 1.1 系统全景

```
┌──────────────────────────────────────────────────────────────────────┐
│                        翻车机积煤检测系统 V3.0                       │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Web 主线（FastAPI 单进程）                                          │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  unified_app.py — 路由层（页面 + WS + API）                    │  │
│  │  state_manager.py — 状态树（Machine→Funnel）+ 后台采集线程     │  │
│  │  common.py — WS 推流 / JPEG 编码 / 内存监控                    │  │
│  │  admin_api.py — 鉴权 + 限流 + 拓扑 CRUD                        │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                              ↓                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  core/capture_window.py — PLC 触发的窗口状态机                 │  │
│  │  algo/{detector,device_detector,judge,...} — 检测算法链路      │  │
│  │  plc/allen_bradley.py — Ethernet/IP 通信 + 心跳 + 三把锁       │  │
│  │  drivers/{basler_camera,mock_drivers,factory} — 相机驱动层     │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.2 配置拓扑（`config/devices.yaml`）

- 1 台运行机器（machine-1，"9#翻车机"），5 个漏斗
- 1 台空机器（machine-2，"2#翻车机"），0 个漏斗
- 实际硬件接入：funnel-1（相机 192.168.1.12 + PLC 192.168.1.19）

### 1.3 测试覆盖

| 测试文件 | 函数数 | 覆盖范围 |
|----------|--------|----------|
| `test_detector.py` | ~20 | 检测算法 |
| `test_unified_app.py` | ~15 | Web 路由 |
| `test_state_manager.py` | ~8 | 状态管理 |
| `test_web_common.py` | ~8 | WS / JPEG / 内存 |
| `test_admin_api.py` | ~6 | 鉴权 |
| `test_integration.py` | ~6 | 端到端 |
| `test_devices_config.py` | ~6 | 拓扑配置 |
| `test_config_env.py` | 2 | 环境变量 |
| 其他 | ~16 | performance / contract |

**总计**：~75-80 个测试函数，本轮 `pytest tests/ -q` = **107 passed / 9 skipped / 0 failed**

**覆盖盲区**：
- ❌ `drivers/basler_camera.py`（生产相机驱动无单测，仅 mock）
- ❌ `plc/allen_bradley.py`（PLC 驱动无单测，仅 mock）
- ⚠️ 心跳/重连超时路径未充分压测
- ⚠️ 三把锁的并发竞态无压力测试
- ⚠️ Web 刷新场景的内存压测无（**这次故障的来源**）

---

## 二、本轮回退后的实测状态

| 指标 | 值 | 状态 |
|------|-----|------|
| HEAD | `f0e3a0b`（等价 `a4f9ccc`） | ✅ |
| `git diff a4f9ccc..HEAD` | 空 | ✅ 真等价 |
| 服务 PID | 51824（重启后） | ✅ |
| RSS（重启后 ~10s） | 152.6 MB | ✅ 干净基线 |
| `/api/archive/stats` | 404 | ✅ 端点已移除 |
| `/api/health` | 200 | ✅ |
| pytest | 107/9/0 | ✅ |
| 主页 | 200 / 27KB | ✅ |

**结论**：回退完成、系统清洁、行为符合 `a4f9ccc` 基线。

---

## 三、识别到的问题清单

### A 类 — 必须处理（3 项）

#### A1. 已知刷新内存暴涨问题未根因定位

- **现象**：用户实测刷新浏览器页面时 RSS 大幅上涨（177→383MB 尖峰）
- **嫌疑点**（`web/unified_app.py`）：
  - `/ws/funnel/{m}/{f}` 5 FPS 循环 `vis = visualize_device(frame, result)` 可能产 5.76MB 新 BGR 图
  - `encode_frame_jpeg_base64(vis, quality=85)` 每 200ms 产 base64 字符串
  - `/ws/overview` 旧连接可能不及时清理
  - `/api/machine/.../snapshot` 端点 `cv2.imencode` + `tobytes` 路径
- **回退后是否消失**：**不确定**。归档没引入 WebSocket / snapshot 路径，理论上回退后该问题仍在。**待复现**。
- **影响**：长期运行内存可能蠕动上涨 → 终将 OOM

#### A2. 多漏斗共享 PLC 标签的架构限制（L1）

- **位置**：`core/capture_window.py` 是 per-funnel 实例，但 PLC 标签 `Vision_CaptureState` / `PLC_CaptureCmd` 是 per-machine 全局
- **影响**：单台翻车机有多个漏斗时，多个 capture_controller 抢着读写同一个标签 → 状态错乱
- **当前缓解**：machine-1 暂时只接了 funnel-1 一台相机
- **必须时机**：第 2 台相机接入前必须改造（计划 V3.1）

#### A3. logger 级别硬编码

- **位置**：`web/unified_app.py:39` 使用 `logger.add(..., level="DEBUG")` 写死
- **预期**：应读 `config.LOG_LEVEL`（dev=DEBUG, prod=INFO）
- **影响**：生产环境日志泛滥，磁盘占用 + 性能损耗
- **修法**：1 行改动

### B 类 — 应清理（5 项）

#### B1. 死代码 `ImageSaver` 残留

- `drivers/__init__.py:3` 导出 `create_image_saver`
- `drivers/factory.py:64-67` `create_image_saver()` 工厂
- `drivers/mock_drivers.py:303-399` `MockImageSaver` 类
- 主线**无任何调用**（grep `image_saver` / `ImageSaver` 无主线命中）
- 影响：误导新开发者认为有归档功能

#### B2. 配置死字段

- `config/config.py:137-139` 仍有 `SAVE_ALARM_IMAGES`, `SAVE_INTERVAL_FRAMES`, `IMAGE_SAVE_DIR`
- `config_dev.yaml:71-73` / `config_prod.yaml:73-75` 仍有同名字段
- 主线无消费方
- 修法：删除 + 在 release notes 写明

#### B3. 临时文件未清理

根目录残留：
- `_commit_msg.txt`
- `_step1_status.txt`
- `_step2_diffstat.txt`
- `_step3_add.txt`
- `_revert3.txt`
- `diff_c.txt`

均为前期 agent 工作过程产物，可全删。

#### B4. 已废弃的归档相关文档（主线 docs/）

| 文档 | 处置 |
|------|------|
| `docs/archive_design.md` | 移到 `non_mainline/documentation/docs/archive/` |
| `docs/CODEX_REVIEW_V19_IMAGE_ARCHIVAL.md` | 同上 |
| `docs/CODEX_REVIEW_V20_ARCHIVE.md` | 同上 |
| `docs/CODEX_REVIEW_V20_FOLLOWUP.md` | 同上 |
| `docs/翻车机积煤检测系统_30漏斗扩展方案_V1.0.docx` | 移到 `non_mainline/documentation/docs/` |
| `tools/generate_full_edge_plan.py` / `tools/generate_scaling_plan.py` | 同上 |

主线 `docs/` 应只留与当前 HEAD 一致的文档。

#### B5. 已存在但属于旧版的 CODEX 审查文档

- `docs/CODEX_REVIEW_V18_HEARTBEAT_ONLINE.md` 是上一次完整闭环（V18 + V18 followup）的提示词，可保留作历史参考。

### C 类 — 风险但已有缓解（4 项）

#### C1. 管理员 token 无过期（L5）

- 工业内网部署，外部不可达
- 上线前必须改默认密码（已写在 README.md）

#### C2. WebSocket 视频流无鉴权（L6）

- 同样依赖内网安全
- 后续可加 token 鉴权但不阻塞当前部署

#### C3. 报警记录重启丢失（L7）

- in-memory state，未持久化
- 需要时加 SQLite（属于 V3.1 范畴）

#### C4. PLC 被第三方挤掉后不自恢复 online（L9）

- 工程纪律：**禁止用独立脚本同时连 PLC**
- 已写入文档

### D 类 — 设计权衡（无需处理）

- D1. 单进程多线程（双缓冲共享内存的硬约束，不能改多进程）
- D2. ECC 降采样 320×240（性能必须，已验证精度）
- D3. vote_threshold = 0.6（5 帧 3 致，已验证抗噪声）
- D4. PLC 触发采集（机械事件比时间触发更安全）

---

## 四、安全连锁链路（必须保持的不变量）

### 4.1 Vision_CanTip 判定（`plc/allen_bradley.py`）

```python
can_tip = (coal_present is False) and (not need_manual) and (fault_code == 0)
```

**三个条件严格 AND**。
- `coal_present is None`（不确定）→ False（拒绝翻车）
- `need_manual=True`（低置信度）→ False
- `fault_code != 0`（任何故障）→ False

宁可漏报（人工二次确认）不可误报（积煤未清卡住设备）。

### 4.2 心跳协议

- 每 500ms 递增 `IPC_Heartbeat`
- PLC 梯形图 2 秒超时 → `Vision_Alive=False` → `Fault_Light=ON`
- 视觉系统启动写 `IPC_Online=True`，退出写 `False`

### 4.3 9 个 PLC 标签

服务器写：`Vision_CanTip / Vision_FaultCode / Vision_ResultValid / IPC_Heartbeat / IPC_Online / Vision_Enable / Vision_CaptureState`
PLC 写：`PLC_CaptureCmd / Tipper_InPosition`

### 4.4 三把锁

- `_io_lock`：保护所有 `plc.read()` / `plc.write()` 调用
- `_heartbeat_value_lock`：保护心跳值读-改-写
- `_reconnect_lock`：保护重连过程（替换 `self.plc` 引用）

---

## 五、CODEX 历次审查闭环

| 轮次 | 范围 | 状态 |
|------|------|------|
| V9-V15 | 早期单点审查 | 已合并 |
| V16 | 双主线收口（合并 main.py + unified_app → 单 Web 主线） | ✅ 闭环 |
| V17 | 复核 | ✅ |
| V18 | 心跳 / IPC_Online 保活 | ✅ 闭环 |
| V19 | 报警图像归档诊断（发现回归） | 分析文档 |
| V20 | 归档实施审查 | 12 项 PASS+1 Block，A3 修复 + V3.0.13 三项新修复，**未闭环就被回退** |

**当前状态**：自 V18 起，主线代码经过完整审查；V19-V20 的归档分支已 revert，相关审查文档应归档到 non_mainline。

**本轮自审查后建议**：发起一次**新的全项目审查**（暂称 V21），覆盖回退后的当前 HEAD 状态 + A1/A2/A3 已知问题 + 测试盲区。

---

## 六、本轮自审查给出的建议优先级

| 优先级 | 项 | 工作量 | 影响 |
|--------|-----|--------|------|
| P0 | A1 刷新内存暴涨复现+定位+修 | 1-3 天 | 高 |
| P1 | A3 logger 级别硬编码（1 行） | 5 分钟 | 低 |
| P1 | B3 清理临时文件 | 1 分钟 | 低 |
| P1 | B4 移走废弃文档到 non_mainline | 10 分钟 | 低 |
| P2 | B1 删 ImageSaver 死代码 | 30 分钟 | 中 |
| P2 | B2 删配置死字段 | 30 分钟 | 中 |
| P3 | A2 多漏斗 PLC 标签架构改造 | 1-2 周 | 高（接相机时阻塞） |
| P3 | drivers/plc 单测补强 | 数天 | 中（覆盖盲区） |

---

## 七、可合并性

**当前 HEAD 是否可 push 到 origin？**

可以。三个 revert commit 是合法的撤销，git 历史完整保留尝试痕迹。但是：

1. **建议先做 P1 清理**（B3 临时文件 + B4 废弃文档迁移）后再 push，避免主线长期带 V3.0.12 残骸
2. **建议先解决 A1**（刷新内存）或至少在 README 标注为已知问题
3. **建议生成 CODEX V21 审查闭环**后再 push
