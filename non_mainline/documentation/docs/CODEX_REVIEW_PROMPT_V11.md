# CODEX 审查提示词 V11 — 翻车机积煤检测系统 V3.0

> 第十一轮审查。PLC 断网后采集永久停滞 bug + 重试机制。请验证。

---

## 审查提示词

```
你是工业安全系统代码审查员。第十一轮审查。

Bug：PLC 断网时 CaptureState 写失败残留→PLC 重连后不发采集指令→采集永久停滞。
已修复：PLC 重连回调重置 State=0 + 3 次重试 + tick() 持续重试兜底。

═══════════════════════════════════════════
一、PLC 重连回调重置验证
═══════════════════════════════════════════

1. **回调中是否遍历所有漏斗重置 State=0？**
   - 文件：web/state_manager.py _register_plc_callback() 的 connected 分支
   - 验证：遍历 _ms.funnels.values()
   - 验证：每个 cc._phase = CapturePhase.IDLE
   - 验证：调 cc._write_plc_state(0)

2. **重试机制是否正确？**
   - 验证：回调中写 State=0 最多重试 3 次，间隔 1 秒
   - 验证：3 次都失败后设 cc._needs_state_reset = True
   - 验证：成功时 break 退出循环并记日志
   - 验证：失败时记 WARNING 日志

3. **tick() 持续重试兜底**
   - 文件：core/capture_window.py tick() IDLE 分支
   - 验证：检查 _needs_state_reset 标志
   - 验证：调 _write_plc_state(STATE_IDLE)
   - 验证：成功后 _needs_state_reset = False 并记日志
   - 验证：失败时标志保留，下次 tick 继续重试

═══════════════════════════════════════════
二、_write_plc_state 返回值
═══════════════════════════════════════════

4. **是否返回 bool？**
   - 文件：core/capture_window.py _write_plc_state()
   - 验证：plc=None 时 return False
   - 验证：write 成功时 return bool(ok)（plc.write 返回 True/False）
   - 验证：异常时 return False
   - 验证：所有调用点（不只是重试处）是否兼容返回值变化

5. **调用点兼容性**
   - 搜索所有 _write_plc_state 调用
   - 之前返回 None，现在返回 bool
   - 验证：其他调用点是否忽略返回值（不受影响）
   - 特别检查：CAPTURING→COMPLETE 的 _write_plc_state(STATE_COMPLETE) 是否受影响

═══════════════════════════════════════════
三、完整恢复链路
═══════════════════════════════════════════

6. **场景还原：PLC 断网→重连→采集恢复**
   ```
   正常采集中 → PLC 断网 → 心跳 3 次失败 → is_connected=False
   → _notify_disconnect 回调 → fault_info=offline
   → CaptureWindow tick() 读 Cmd 返回 IDLE（read 失败→CMD_IDLE）
   → 停止采集 → 写 State=2 失败（PLC 断连）→ State 残留
   → PLC 重连 → _notify_connect 回调
   → 回调写 State=0（重试 3 次）
   → 成功 → PLC 看到 State=0 → Rung6 触发 → 发 Cmd=1
   → CaptureWindow tick() 读到 Cmd=1 → CAPTURING → 恢复采集
   ```
   验证：以上每一步的代码路径是否连通

7. **场景：回调写 State=0 三次都失败**
   ```
   回调失败 → _needs_state_reset=True
   → tick() IDLE 每次检查 → _write_plc_state(0)
   → 最终 PLC 稳定后写入成功 → _needs_state_reset=False
   → PLC Rung6 触发 → 采集恢复
   ```
   验证：tick() 轮询间隔是多少？（poll_interval_s 默认 0.2 秒）
   验证：_needs_state_reset 检查是否在 poll 间隔检查之前执行

8. **场景：服务重启后 State 残留**
   - 验证：CaptureWindow.start() 是否写 State=0
   - 验证：start() 中 _write_plc_state(STATE_IDLE) 是否存在

═══════════════════════════════════════════
四、time.sleep 在回调线程中的影响
═══════════════════════════════════════════

9. **PLC 回调在哪个线程执行？**
   - on_status_change 从 _heartbeat_loop 或 _try_reconnect_inline 调用
   - 这两个都在 plc-heartbeat 线程中
   - 回调中 time.sleep(1.0) × 3 次 = 最多阻塞 3 秒
   - 验证：这 3 秒阻塞是否影响心跳线程的 500ms 间隔
   - 评估：心跳在重连成功后才恢复，此时正在回调中 sleep
   - 心跳下一次 tick 要等回调返回 → 最多延迟 3 秒心跳
   - 是否可接受？（PLC 心跳超时是 2 秒，3 秒 sleep 可能导致超时）

═══════════════════════════════════════════
五、安全连锁快速回归
═══════════════════════════════════════════

10. can_tip 公式不变
11. 异常 fail-safe 不变
12. 心跳单源不变
13. 重连策略不变

═══════════════════════════════════════════
输出格式
═══════════════════════════════════════════

对每项标注 PASS / FAIL / WARNING。

重点关注第 9 项：回调中 sleep 3 秒是否会导致心跳超时。
```

---

## Bug 证据

```
47.5 小时运行，只有 1,164 帧（理论 ~171,000 帧）
Vision_CaptureState=1 残留，PLC 不发 CaptureCmd
```

## 修复层次

```
第一层：PLC 重连回调写 State=0（3 次重试）
第二层：tick() IDLE 持续重试（_needs_state_reset 标志）
第三层：服务重启时 start() 写 State=0
```

## 累计修复：57 项
