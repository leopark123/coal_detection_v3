# CODEX 审查提示词 V9 — 翻车机积煤检测系统 V3.0（最终轮）

> 第九轮审查。V8 发现 3 个 FAIL + 1 个 WARNING，已全部修复。
> 本轮为最终验证，确认所有问题闭环后给出生产部署结论。

---

## 审查提示词

```
你是工业安全系统代码审查员。第九轮（最终轮）审查。

项目：煤矿翻车机积煤检测系统 V3.0
部署：单相机 Basler acA1600-60gm + 单 PLC AB 1769-L16ER
累计修复：50 项安全漏洞（经 8 轮审查迭代）

═══════════════════════════════════════════
一、V8 修复验证（4 项）
═══════════════════════════════════════════

1. **admin_api 动态创建 ID 校验**
   - V8 问题：POST /machines 和 POST /funnels 未校验 ID
   - 文件：web/admin_api.py add_machine() 和 add_funnel()
   - 验证：是否调用 _validate_id(req.id) 且在创建 Config 对象之前
   - 验证：非法 ID 如 "<script>" 是否抛异常

2. **add_machine PLC 事件+回调注册**
   - V8 问题：运行时新增翻车机缺 PLC 事件和 on_status_change 回调
   - 文件：web/state_manager.py add_machine()
   - 验证：PLC 连接成功时是否调 add_fault_event + _register_plc_callback
   - 验证：PLC 连接失败时是否调 add_fault_event 并设 fault_info

3. **PLC 回调注册提取为公共方法**
   - 文件：web/state_manager.py _register_plc_callback()
   - 验证：initialize() 和 add_machine() 是否都复用此方法
   - 验证：方法内容是否正确（断连写 plc 事件，重连写 plc_ok 事件）

4. **MockPLC 接口一致**
   - 文件：drivers/mock_drivers.py MockPLC
   - 验证：是否有 on_status_change = None 属性

═══════════════════════════════════════════
二、PLC 状态通知完整性（V8 FAIL #11 修复）
═══════════════════════════════════════════

5. **_notify_disconnect 边沿触发**
   - 文件：plc/allen_bradley.py
   - 验证：方法存在，使用 _was_connected 做边沿检测
   - 验证：只在 connected→disconnected 时触发一次（不重复回调）

6. **_notify_connect 边沿触发**
   - 验证：方法存在，只在 disconnected→connected 时触发一次

7. **运行时断连路径覆盖**
   - write() 通信失败 → is_connected=False → _notify_disconnect ✓?
   - read() 超时 → is_connected=False → _notify_disconnect ✓?
   - check_connection() 异常 → is_connected=False → _notify_disconnect ✓?
   - _heartbeat_loop 连续失败 → is_connected=False → _notify_disconnect ✓?

8. **运行时重连路径覆盖**
   - connect() 成功 → _was_connected=True ✓?
   - _try_reconnect_inline 成功 → _was_connected=True + _notify_connect ✓?

9. **fault_info["plc"] 同步**
   - 断连时：fault_info 设为 offline + error + since ✓?
   - 重连时：fault_info 设为 online + error=None ✓?
   - 总览横幅能正确反映 PLC 状态变化 ✓?

═══════════════════════════════════════════
三、故障事件完整覆盖表
═══════════════════════════════════════════

10. **验证以下 9 条事件路径全部有 add_fault_event 调用**

| # | 事件 | 文件:方法 | 事件类型 |
|---|------|----------|----------|
| 1 | 相机断开 | state_manager:_bg_detection_loop | camera |
| 2 | 相机从未连接 | state_manager:_bg_detection_loop | camera |
| 3 | 相机重连成功 | state_manager:_bg_detection_loop | camera_ok |
| 4 | PLC 初始化成功 | state_manager:initialize | plc_ok |
| 5 | PLC 初始化失败 | state_manager:initialize | plc |
| 6 | PLC 运行时断连 | allen_bradley → 回调 → state_manager | plc |
| 7 | PLC 运行时重连 | allen_bradley → 回调 → state_manager | plc_ok |
| 8 | PLC 动态新增成功 | state_manager:add_machine | plc_ok |
| 9 | PLC 动态新增失败 | state_manager:add_machine | plc |

═══════════════════════════════════════════
四、ID 白名单校验完整性
═══════════════════════════════════════════

11. **所有 ID 入口是否都经过校验？**
    - YAML 加载：from_yaml() 中 machine_id 和 funnel_id ✓?
    - 管理 API 创建：admin_api add_machine 和 add_funnel ✓?
    - 正则：^[A-Za-z0-9_-]+$ ✓?

═══════════════════════════════════════════
五、安全连锁快速回归（7 项）
═══════════════════════════════════════════

12. can_tip = (coal_present is False) and (not need_manual) and (fault_code == 0)
13. detect_device 异常 → fault_code=3
14. 安全上限零帧 → fail-safe 写 PLC
15. _io_lock 全部 acquire(timeout)，无 with self._io_lock: 残留
16. 心跳单源：update_heartbeat 已废弃为 noop
17. WebSocket 不 grab，tick() 单源
18. 重连策略：_ever_connected=False 不重连，True 永不放弃

═══════════════════════════════════════════
输出格式
═══════════════════════════════════════════

对每项标注：
- VERIFIED: 修复正确
- PASS: 检查通过
- FAIL: 发现新问题（文件+行号+问题+建议）
- WARNING: 潜在风险

统计：VERIFIED + PASS / FAIL / WARNING

最终结论（三选一）：
A. 单相机配置可以部署到工业生产环境
B. 有条件可以部署（列出条件）
C. 不可以部署（列出阻断项）
```

---

## 项目审查全历程

| 轮次 | 焦点 | 发现 | 修复 |
|------|------|------|------|
| V1 | 初始安全审查 | 5F | 27项(6C+13H+8M) |
| V2 | R1修复验证 | 1F | 4项 |
| V3 | 全面检查(34项) | 4F | 4项 |
| V4 | 崩溃根因 | 0F | 1项(pypylon冲突) |
| V5 | 重连策略 | 0F | 1项(永不放弃) |
| V6 | 故障面板 | 2F+1W | 3项 |
| V7 | V6修复验证 | 2F | 3项(ID校验+PLC运行时事件) |
| V8 | V7修复验证 | 3F+1W | 7项(admin校验+回调提取+边沿触发+MockPLC) |
| **V9** | **最终验证** | **待审** | **—** |
| **累计** | | | **50 项** |

## 审查文件清单

| 文件 | 本轮关键检查 |
|------|-------------|
| plc/allen_bradley.py | _notify_disconnect/connect 边沿触发 + _was_connected |
| web/state_manager.py | _register_plc_callback 复用 + add_machine 事件 + 9 条事件路径 |
| web/admin_api.py | _validate_id 校验 |
| config/devices_config.py | _validate_id 正则 + from_yaml 调用 |
| drivers/mock_drivers.py | on_status_change 属性 |
