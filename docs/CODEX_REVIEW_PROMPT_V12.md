# CODEX 审查提示词 V12 — 翻车机积煤检测系统 V3.0

> 第十二轮审查。V11 发现回调中 time.sleep 阻塞心跳线程等 4 个问题，经自审查后已全部修复。
> 本轮验证自审查修复是否正确，确认采集停滞 bug 完全闭环。

---

## 审查提示词

```
你是工业安全系统代码审查员。第十二轮审查。

背景：
- V11 修复了"PLC 断网后 CaptureState 残留→采集永久停滞"bug
- V11 自审查发现回调中 time.sleep 会阻塞心跳线程（可能导致重连-超时死循环）
- 已修复为：回调单次尝试（不 sleep）+ _needs_state_reset 标志 + tick() 异步重试

═══════════════════════════════════════════
一、自审查修复验证（4 项）
═══════════════════════════════════════════

### 修复 A：回调中删除 time.sleep

- V11 问题：回调中 time.sleep(1.0) × 3 次，在心跳线程执行，阻塞 3-15 秒
- PLC 心跳超时 2 秒 → 可能导致"重连→sleep→超时→断连"死循环
- 文件：web/state_manager.py _register_plc_callback() connected 分支
- 验证：
  1. 搜索该方法内是否还有 time.sleep
  2. 搜索是否还有 for _retry 循环
  3. 确认改为：单次 _write_plc_state(0) → 失败设标志 → 不阻塞返回

### 修复 B：_write_plc_state 返回 bool

- V11 问题：之前返回 None，调用方无法判断成功/失败
- 文件：core/capture_window.py _write_plc_state()
- 验证：
  4. plc=None 时 return False
  5. write 成功时 return bool(ok)
  6. 异常时 return False
  7. 其他调用点（10+ 处）忽略返回值，不受影响

### 修复 C：_needs_state_reset 初始化

- V11 问题：属性只在外部设置（state_manager），类自身未声明
- 文件：core/capture_window.py __init__()
- 验证：
  8. __init__ 中是否有 self._needs_state_reset: bool = False
  9. 不再依赖 getattr 默认值

### 修复 D：tick() 重试在 poll_interval 内

- V11 问题：_needs_state_reset 检查在 poll_interval 外，每次 tick 都写 PLC
- 文件：core/capture_window.py tick() IDLE 分支
- 验证：
  10. _needs_state_reset 检查是否在 if now - _last_poll_time >= poll_interval_s 之内
  11. 成功后 _needs_state_reset = False + 日志
  12. 失败时标志保留，下个 poll 周期（0.2秒后）重试

═══════════════════════════════════════════
二、完整恢复链路端到端验证
═══════════════════════════════════════════

13. **正常流程（PLC 未断连）**
    - tick() IDLE → poll → 读 Cmd=1 → CAPTURING → 采集 → 停止 → COMPLETE → IDLE
    - _needs_state_reset 始终为 False，不影响
    - 验证：正常路径无多余操作

14. **PLC 断网→重连→采集恢复（一次写成功）**
    ```
    PLC 断网 → 心跳失败 → _notify_disconnect
    → PLC 重连 → _notify_connect → 回调
    → 回调写 State=0 成功 → _needs_state_reset=False
    → tick() IDLE 正常轮询 → PLC 发 Cmd=1 → 恢复采集
    ```
    验证：此路径代码连通

15. **PLC 断网→重连→首次写失败→tick 重试成功**
    ```
    PLC 重连 → 回调写 State=0 失败(返回 False) → _needs_state_reset=True
    → tick() IDLE → poll_interval 到 → 检测标志 → _write_plc_state(0)
    → 成功 → _needs_state_reset=False → 日志 "State=0 重试写入成功"
    → PLC 发 Cmd=1 → 恢复采集
    ```
    验证：此路径代码连通

16. **服务重启后**
    - start() 写 State=0（已有）
    - _needs_state_reset 初始化为 False（已有）
    - 验证：重启后不依赖回调，直接从 IDLE 开始

═══════════════════════════════════════════
三、心跳线程安全
═══════════════════════════════════════════

17. **回调执行时间**
    - 现在回调中：遍历 5 漏斗 × 1 次 write = 5 次 PLC 写操作
    - 每次 write 需获取 _io_lock（超时 5 秒）
    - 最坏情况：5 × write 延迟 ≈ 几十 ms（PLC 通信正常时）
    - 验证：不再有 sleep，总耗时远小于心跳超时 2 秒

18. **回调中 write 失败是否会抛异常中断遍历？**
    - _write_plc_state 内部有 try/except
    - 验证：一个漏斗写失败不影响其他漏斗的重置

═══════════════════════════════════════════
四、安全连锁快速回归
═══════════════════════════════════════════

19. can_tip 公式
20. 异常 fail-safe
21. _io_lock 全超时
22. 心跳单源
23. 重连策略（_ever_connected）

═══════════════════════════════════════════
输出格式
═══════════════════════════════════════════

对每项标注：
- VERIFIED: 自审查修复正确
- PASS: 检查通过
- FAIL: 发现新问题
- WARNING: 潜在风险

最终结论（三选一）：
A. 采集停滞 bug 已完全闭环，可以部署
B. 有条件闭环（列出条件）
C. 未闭环（列出阻断项）
```

---

## 修复层次（三层兜底）

```
第一层：PLC 重连回调写 State=0（单次，不阻塞）
  ↓ 失败
第二层：tick() IDLE 每 0.2 秒重试写 State=0（_needs_state_reset 标志）
  ↓ PLC 彻底不可用
第三层：服务重启时 start() 写 State=0
```

## 自审查修复清单

| 项 | V11 问题 | 修复 |
|---|----------|------|
| A | 回调 time.sleep 阻塞心跳 | 删除 sleep，改单次+标志 |
| B | _write_plc_state 返回 None | 改返回 bool |
| C | _needs_state_reset 未初始化 | __init__ 中声明 |
| D | 重试无节流 | 放入 poll_interval 检查内 |

## 累计修复：58 项
