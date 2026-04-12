# CODEX 审查提示词 V15 — 翻车机积煤检测系统 V3.0

> 第十五轮审查。漏斗详情页：删除格栅热力图，替换为采集窗口记录+设备状态面板；修复 grid_details 序列化。

---

## 审查提示词

```
你是工业安全系统代码审查员。第十五轮审查，聚焦漏斗详情页改动。

═══════════════════════════════════════════
一、grid_details 序列化修复
═══════════════════════════════════════════

1. **DeviceResult.to_dict() 是否包含 grid_details？**
   - 文件：algo/device_detector.py to_dict()
   - 验证：grid_details 列表是否被序列化
   - 验证：has_coal / is_visible 是否用 bool() 强转（防 numpy.bool_ JSON 序列化失败）
   - 验证：grid_details 为 None 时是否安全（空列表）

═══════════════════════════════════════════
二、漏斗详情页 HTML 改动
═══════════════════════════════════════════

2. **格栅热力图是否完全删除？**
   - 文件：web/templates/funnel_detail.html
   - 验证：不存在 grid-heatmap、grid-cell、gcell- 相关 CSS/HTML/JS
   - 验证：gridCount 变量是否仍在使用（如果不用了应删除）

3. **采集窗口记录面板**
   - HTML：#window-list 容器存在
   - CSS：.window-list、.window-item、.window-badge 样式存在
   - JS：windowRecords 数组 + MAX_WINDOW_RECORDS=15
   - 数据源：fetch('/api/.../capture_status') 每 5 秒
   - 去重：检查是否与上一条记录的 frames/alarm 不同才追加
   - XSS：时间字符串是否经过 escapeHtml

4. **设备状态面板**
   - HTML：#ds-camera、#ds-plc、#ds-reconnects、#ds-uptime、#ds-phase
   - 数据源：fetch('/api/faults/all') 每 5 秒
   - 相机状态匹配：用 funnelId 过滤 faults
   - PLC 状态匹配：用 machineId 过滤 faults
   - XSS：状态文本是否经过 escapeHtml

5. **采集阶段实时更新**
   - 来源：WebSocket 推送的 data.capture_phase
   - 映射：idle→空闲、capturing→采集中 等
   - 验证：每帧 WebSocket 消息都会更新 #ds-phase

═══════════════════════════════════════════
三、API 调用安全
═══════════════════════════════════════════

6. **/api/faults/all 和 /api/.../capture_status 是否只读？**
   - 验证：GET 方法，无鉴权要求
   - 验证：不触发任何写操作
   - 验证：5 秒轮询频率是否合理

7. **fetch 失败处理**
   - 两个 fetch 都有 .catch(function(){})
   - 验证：API 不可达时页面不崩溃

═══════════════════════════════════════════
四、前后端数据一致性
═══════════════════════════════════════════

8. **capture_status API 返回结构**
   - 文件：web/unified_app.py api_capture_status
   - 返回：capture_controller.get_status()
   - 验证：last_result 包含 total_frames、alarm_frames、alarm_ratio、is_alarm、confidence

9. **faults API 返回结构**
   - 文件：web/state_manager.py get_all_faults()
   - 验证：faults 数组每项有 device、type、status_display、reconnect_attempts
   - 验证：system 有 uptime_h

═══════════════════════════════════════════
五、安全回归
═══════════════════════════════════════════

10. 核心检测链路不受 UI 改动影响
11. can_tip 公式不变
12. WebSocket 推流不受影响

═══════════════════════════════════════════
输出格式
═══════════════════════════════════════════

对每项标注 PASS / FAIL / WARNING。

重点关注：
- 第 1 项 numpy.bool_ 序列化
- 第 4 项 funnelId/machineId 过滤逻辑是否准确
```

---

## 改动文件

| 文件 | 改动 |
|------|------|
| algo/device_detector.py | to_dict() 新增 grid_details 序列化（bool 强转） |
| web/templates/funnel_detail.html | 删格栅热力图 → 采集窗口记录 + 设备状态面板 |

## 累计修复：59 项
