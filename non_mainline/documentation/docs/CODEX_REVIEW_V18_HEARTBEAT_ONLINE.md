# CODEX 审查提示词 V18 - 心跳线程 IPC_Online 保活修复

> 背景：PLC 掉电重启后所有标签值被清零，但视觉系统（95小时连续运行）未重启，
> 导致 IPC_Online 一直为 False，PLC 判定视觉系统不健康（Vision_Alive=False）。
> 修复方案：在心跳线程每次写入成功后顺带刷新 IPC_Online=True。
>
> 修改文件：plc/allen_bradley.py（心跳线程 _heartbeat_loop 方法）

---

## 检查清单（10 项）

### A. 修复正确性（4 项）

**A1. IPC_Online 写入位置**
- 验证 `_heartbeat_loop` 中，心跳写入成功（`not result.error`）后新增了 `self.plc.write("IPC_Online", True)`
- 验证该写入在 `_io_lock` 保护范围内（心跳写入本身已持有锁）
- 如果不在锁内，验证是否需要额外加锁（注意：心跳写入后锁已释放，新写入是否安全？）

**A2. 异常隔离**
- 验证 `IPC_Online` 写入失败不会影响心跳主逻辑
- 应有 `try/except` 包裹，且不修改 `_consecutive_failures` 计数
- 写入失败不应导致心跳线程退出或标记断连

**A3. 写入频率影响**
- 心跳间隔 500ms，每次额外写一个标签
- 验证 Ethernet/IP 单次写操作耗时是否在可接受范围（通常 <1ms）
- 确认不会导致心跳间隔显著增加（总耗时仍 < 500ms 预算）

**A4. 锁安全**
- 当前代码中心跳写入使用 `_io_lock.acquire(timeout=2.0)` + `try/finally release`
- 新增的 `IPC_Online` 写入是在锁释放之后还是之前？
- 如果在锁释放之后：`self.plc.write()` 是否线程安全？是否可能与 `send_detection_result` 并发？
- 如果存在竞争风险，是否需要将 `IPC_Online` 写入移到锁保护范围内？

### B. 安全信号影响（3 项）

**B5. can_tip 逻辑不受影响**
- 验证 `send_detection_result()` 中的 can_tip 判定逻辑未被修改
- `can_tip = (coal_present is False) and (not need_manual) and (fault_code == 0)` 仍成立

**B6. IPC_Online 语义正确**
- `IPC_Online = True` 的含义是"视觉系统在线"
- 每次心跳成功写入后刷新该值，语义正确（心跳成功 = 系统在线）
- 验证 `disconnect()`/`close()` 时仍然写入 `IPC_Online = False`

**B7. PLC 梯形图兼容**
- PLC Rung 2: `IPC_Online AND XIO(HB_Timer.DN) → Vision_Alive`
- 频繁写入 `IPC_Online = True`（每500ms）是否影响 PLC 侧扫描周期？
- AB CompactLogix 对频繁写入同一标签的处理是否正常？（通常无问题）

### C. 边界情况（3 项）

**C8. PLC 重启检测**
- 修复后，PLC 掉电重启清零所有标签 → 下一个心跳周期（500ms内）`IPC_Online` 被重新写为 True
- 验证这个恢复时间窗口是否满足 PLC 梯形图的超时设置（HB_Timer = 2秒）
- 时序：PLC 重启 → 最多 500ms 后心跳写入 → IPC_Online 恢复 → HB_Timer 未超时 → Vision_Alive 保持/恢复 True

**C9. 视觉系统正常关闭**
- `close()` 方法中先停心跳线程，再写 `IPC_Online = False`
- 停止心跳后不再有保活写入，`IPC_Online = False` 不会被覆盖
- 验证关闭流程中 `IPC_Online` 的最终值为 False

**C10. 重连场景**
- 心跳线程内重连（`_try_reconnect_inline`）成功后已经写了 `IPC_Online = True`（第574行）
- 初始连接（`connect`）成功后也写了 `IPC_Online = True`（第135行）
- 新增的心跳保活写入与这两处不冲突，仅是额外保险
- 验证三处写入不存在竞态条件

---

## 输出格式

```
每项一行：
[编号] [PASS/FAIL/WARNING]: 简要说明

最终统计：
PASS: X / 10
FAIL: X / 10
WARNING: X / 10

结论：
- FAIL=0：修复可以部署
- FAIL>0：需要调整后重审
```
