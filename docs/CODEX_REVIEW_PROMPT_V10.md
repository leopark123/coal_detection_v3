# CODEX 审查提示词 V10 — 翻车机积煤检测系统 V3.0（最终轮）

> 第十轮审查。V9 发现 5 个 FAIL，已全部修复。本轮为最终验证。

---

## 审查提示词

```
你是工业安全系统代码审查员。第十轮（最终轮）审查。
累计修复 55 项。请验证 V9 的 5 个 FAIL 是否全部正确修复。

═══════════════════════════════════════════
一、V9 修复验证（5 项）
═══════════════════════════════════════════

### FAIL #1: admin_api ID 校验抛 500 而非 400

- 文件：web/admin_api.py add_machine() 和 add_funnel()
- 修复：_validate_id 包在 try/except ValueError → HTTPException(400)
- 验证：
  1. add_machine 中 _validate_id 是否在 try 块内
  2. add_funnel 中 _validate_id 是否在 try 块内
  3. 非法 ID 是否返回 400（不是 500）

### FAIL #7: write/read/check_connection 异常不通知

- 文件：plc/allen_bradley.py
- 修复：3 处 is_connected=False 后加 _notify_disconnect(reason)
- 验证：
  4. write() 异常分支：累计失败达上限 → is_connected=False → _notify_disconnect() ✓?
     搜索 "写入异常累计" 确认
  5. read() 异常分支：timeout → is_connected=False → _notify_disconnect() ✓?
     搜索 "读取异常" 确认
  6. check_connection() result.error 分支：→ is_connected=False → _notify_disconnect() ✓?
     搜索 "连接检查失败" 确认

### FAIL #8: _try_reconnect_inline 回调被预赋值抑制

- 文件：plc/allen_bradley.py _try_reconnect_inline()
- 修复：删掉 self._was_connected = True，只由 _notify_connect() 内部翻转
- 验证：
  7. _try_reconnect_inline 重连成功处是否只有 _notify_connect() 调用，没有 _was_connected=True 赋值
  8. _notify_connect() 内部逻辑：not _was_connected and is_connected → 设 _was_connected=True + 调回调
  9. 模拟场景：PLC 断连 → _was_connected 变 False → 重连成功 → _notify_connect 检测到边沿 → 触发回调 → plc_ok 事件发出

### FAIL #9/#10: fault_info 不更新 + 事件路径不闭环

- 依赖 #8 修复
- 验证：
  10. #8 修复后，_notify_connect 能正常触发 → 回调写 plc_ok 事件 + fault_info=online
  11. 完整 9 条事件路径是否全部有 add_fault_event：

| # | 事件 | 验证 |
|---|------|------|
| 1 | 相机断开 | state_manager _bg_detection_loop 中 "camera" 事件 |
| 2 | 相机从未连接 | state_manager _bg_detection_loop 中 "camera" 事件 |
| 3 | 相机重连成功 | state_manager _bg_detection_loop 中 "camera_ok" 事件 |
| 4 | PLC 初始化成功 | state_manager initialize 中 "plc_ok" 事件 |
| 5 | PLC 初始化失败 | state_manager initialize 中 "plc" 事件 |
| 6 | PLC 运行时断连 | allen_bradley _notify_disconnect → 回调 → "plc" 事件 |
| 7 | PLC 运行时重连 | allen_bradley _notify_connect → 回调 → "plc_ok" 事件 |
| 8 | PLC 动态新增成功 | state_manager add_machine 中 "plc_ok" 事件 |
| 9 | PLC 动态新增失败 | state_manager add_machine 中 "plc" 事件 |

═══════════════════════════════════════════
二、边沿触发完整性
═══════════════════════════════════════════

12. **_notify_disconnect 所有调用点**
    - 搜索 _notify_disconnect( 确认所有调用位置：
      - write() 通信失败
      - write() 异常累计
      - read() 超时
      - read() 异常
      - check_connection() result.error
      - check_connection() 异常
      - _heartbeat_loop 连续失败
    - 每处是否都在 is_connected=False 之后？

13. **_notify_connect 所有调用点**
    - 搜索 _notify_connect( 确认：
      - _try_reconnect_inline 成功
    - connect() 成功时只设 _was_connected=True（不调回调，因为首次连接不是"重连"）

14. **不存在重复回调风险**
    - _notify_disconnect：_was_connected 从 True→False 只触发一次
    - _notify_connect：_was_connected 从 False→True 只触发一次
    - 连续多次 is_connected=False 不会重复调 _notify_disconnect

═══════════════════════════════════════════
三、安全连锁快速回归
═══════════════════════════════════════════

15. can_tip = (coal_present is False) and (not need_manual) and (fault_code == 0)
16. 异常 fault_code=3 + 零帧 fail-safe
17. _io_lock 全超时 + 心跳单源 + WebSocket 不 grab + tick 单源
18. 重连：_ever_connected=False 不重连，True 永不放弃

═══════════════════════════════════════════
输出格式
═══════════════════════════════════════════

对每项标注 VERIFIED / PASS / FAIL / WARNING。

最终结论（三选一）：
A. 单相机配置可以部署到工业生产环境
B. 有条件可以部署（列出条件）
C. 不可以部署（列出阻断项）
```

---

## 累计修复

| 轮次 | 修复数 | 关键 |
|------|--------|------|
| 初始 | 27 | 6C+13H+8M |
| R1-R2 | 8 | 审查修复 |
| R3 | 1 | pypylon崩溃根因 |
| R4 | 1 | 永不放弃重连 |
| R5-R6 | 6 | 故障面板+事件 |
| R7 | 3 | ID校验+PLC回调 |
| R8 | 4 | 边沿触发+异常通知 |
| R9 | 5 | 预赋值修复+400返回+3处通知补全 |
| **合计** | **55** |
