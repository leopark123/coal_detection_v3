# CODEX 审查提示词 V2 — 翻车机积煤检测系统 V3.0

> 第二轮审查。第一轮发现 4 个 FAIL + 6 个 WARNING，其中 4 个 FAIL 已修复。
> 请验证修复是否正确，并检查是否引入新问题。

---

## 审查提示词

```
你是一位工业安全系统代码审查员，这是第二轮审查。

第一轮发现的 4 个 FAIL 已修复，请逐项验证：

### FAIL #1（已修复）：相机未匹配 IP 时回退连接第一台
- 文件：drivers/basler_camera.py 约第 131 行
- 修复方案：改为 raise ConnectionError，拒绝连接
- 验证：确认不再有回退到 devices[0] 的逻辑

### FAIL #2（已修复）：detect_device() 异常分支未置故障码
- 文件：algo/device_detector.py 约第 170 行
- 修复方案：异常时设 fault_code=3, quality_ok=False, device_confidence="LOW"
- 验证：确认 except Exception 分支和 else 分支都设了 fault_code≠0
- 验证：这样 can_tip = (coal_present is False) and (fault_code == 0) = False（安全）

### FAIL #3（已修复）：_io_lock 两处无超时
- 文件：plc/allen_bradley.py 约第 385 行和第 522 行
- 修复方案：改为 acquire(timeout=self._io_lock_timeout)
- 验证：搜索整个文件，确认不再有 `with self._io_lock:` 的用法
- 验证：所有 _io_lock 使用点都有超时 + try/finally

### FAIL #4（已修复）：错误消息发送无超时
- 文件：web/common.py 约第 160 行
- 修复方案：包 asyncio.wait_for(send_json, timeout=_WS_SEND_TIMEOUT)
- 验证：确认所有 send_json 调用都有超时保护

### 额外检查（第一轮 WARNING 项）

1. 画质失败时 device_has_coal=False 语义是否安全？
   - 文件：algo/device_detector.py:135
   - 关注：fault_code=3 时 can_tip 的完整判定路径

2. 60 秒安全上限触发且零帧时，是否输出故障结果？
   - 文件：core/capture_window.py:201
   - 关注：是否写 PLC fault_code 或只是静默回 IDLE

3. 相机重连后是否重新注册到 atexit 全局列表？
   - 文件：drivers/basler_camera.py connect() 和 _active_cameras

4. 多漏斗争抢 PLC 标签（L1）的临时方案是否有效？
   - 文件：web/state_manager.py:218-221
   - 关注：无相机漏斗确实不调 tick()

5. PLC 心跳是否只有一个递增源？
   - 文件：plc/allen_bradley.py
   - 关注：update_heartbeat() 是否还被任何运行路径调用

### 输出格式

对每个修复项标注：
- VERIFIED: 修复正确
- INCOMPLETE: 修复不完整（说明遗漏）
- REGRESSION: 引入了新问题（说明具体问题）

对额外检查项标注 PASS / FAIL / WARNING。

最后给出：第二轮审查后是否可以部署到工业生产环境（单相机配置）。
```

---

## 修复清单

| 轮次 | 编号 | 严重度 | 问题 | 状态 |
|------|------|--------|------|------|
| R1 | F1 | FAIL | 相机回退连接第一台 | ✅ 已修 |
| R1 | F2 | FAIL | detect_device 异常无 fault_code | ✅ 已修 |
| R1 | F3 | FAIL | _io_lock 2 处无超时 | ✅ 已修 |
| R1 | F4 | FAIL | 错误消息发送无超时 | ✅ 已修 |
| R1 | W1 | WARNING | 画质失败 has_coal=False 语义 | 接受（fault_code 保护） |
| R1 | W2 | WARNING | 安全上限零帧静默回 IDLE | 待验证 |
| R1 | W3 | WARNING | atexit 重连后未重注册 | 待验证 |
| R1 | W4 | WARNING | 动态删除收尾竞态 | 接受（daemon 线程） |
| R1 | W5 | WARNING | L1 多漏斗争抢 PLC | 接受（单相机规避） |

## 累计修复统计

| 严重度 | 数量 |
|--------|------|
| CRITICAL | 6 |
| HIGH | 13 |
| MEDIUM | 8 |
| R1 FAIL | 4 |
| **合计** | **31** |
