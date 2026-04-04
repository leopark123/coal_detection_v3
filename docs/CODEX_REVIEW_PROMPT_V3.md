# CODEX 审查提示词 V3 — 翻车机积煤检测系统 V3.0

> 第三轮审查。前两轮共发现并修复 31 个安全漏洞（6 CRITICAL + 13 HIGH + 8 MEDIUM + 4 R1-FAIL）。
> 本轮验证所有修复是否生效，并做最终生产部署评估。

---

## 审查提示词

```
你是一位工业安全系统代码审查员。这是第三轮（最终轮）审查。

项目：煤矿翻车机积煤检测系统 V3.0
功能：Basler 工业相机拍摄格栅画面 → 检测算法 → PLC 安全连锁控制翻车机
核心原则：宁可漏报不可误报（误报→急停→煤车倾倒卡死设备）
部署配置：单相机（Basler acA1600-60gm）+ 单 PLC（AB 1769-L16ER）

前两轮修复了 31 个安全漏洞。请验证以下全部修复是否正确，并做最终评估。

═══════════════════════════════════════════
一、安全连锁链路（CRITICAL）
═══════════════════════════════════════════

1. can_tip 判定是否安全？
   - 文件：plc/allen_bradley.py send_detection_result()
   - 要求：can_tip = (coal_present is False) and (not need_manual) and (fault_code == 0)
   - 验证：coal_present=None 时 can_tip 必须为 False

2. result_valid 是否检查 fault_code？
   - 文件：plc/allen_bradley.py send_detection_result()
   - 要求：result_valid = confidence in ("HIGH","MEDIUM") and (fault_code == 0) and (coal_present is not None)

3. detect_device 异常分支是否 fail-safe？
   - 文件：algo/device_detector.py detect_device()
   - 要求：except Exception 和 else（空 grid_details）分支都设 fault_code=3, quality_ok=False, device_confidence="LOW"
   - 验证：不存在"检测失败但 fault_code=0"的路径

4. 画质自检失败是否正确传递 fault_code？
   - 文件：algo/device_detector.py detect_device()
   - 要求：quality_ok=False 时返回 fault_code=3

5. 心跳是否单一递增源？
   - 文件：plc/allen_bradley.py
   - 要求：update_heartbeat() 已废弃（return True noop），只有 _heartbeat_loop 递增
   - 验证：搜索全文件确认只有 _heartbeat_loop 修改 heartbeat_value

═══════════════════════════════════════════
二、并发安全
═══════════════════════════════════════════

6. _io_lock 是否全部有超时？
   - 文件：plc/allen_bradley.py
   - 要求：搜索确认不存在 "with self._io_lock:" 的用法
   - 要求：所有使用点都是 acquire(timeout=self._io_lock_timeout) + try/finally release()

7. WebSocket 是否不再 grab 相机？
   - 文件：web/unified_app.py funnel_ws()
   - 要求：只读 fs.last_frame/fs.last_result，不调 camera.grab()

8. tick() 是否只由后台 worker 驱动？
   - 文件：web/state_manager.py
   - 要求：get_overview_data() 不调 tick()，只读 phase
   - 要求：只有 _bg_detection_loop 调 cc.tick()

9. 所有 WebSocket send_json 是否有超时？
   - 文件：web/common.py 和 web/unified_app.py
   - 要求：搜索所有 send_json 调用，确认全部包在 asyncio.wait_for(timeout=5.0) 中
   - 特别检查：overview_ws 的 send_json

10. 线程池是否独立？
    - 文件：web/common.py
    - 要求：_grab_executor 和 _detect_executor 两个独立 ThreadPoolExecutor
    - 要求：run_in_executor 都有 asyncio.wait_for 超时

═══════════════════════════════════════════
三、异常恢复
═══════════════════════════════════════════

11. 相机未匹配 IP 是否拒绝连接？
    - 文件：drivers/basler_camera.py connect()
    - 要求：raise ConnectionError，不回退连接第一台

12. 相机重连策略是否正确？
    - 文件：web/state_manager.py _bg_detection_loop()
    - 要求：快速5次(10秒间隔) → 慢速(60秒间隔)永不放弃
    - 要求：成功后计数归零
    - 要求：fault_info 正确更新

13. 相机重连后是否重新注册 atexit？
    - 文件：drivers/basler_camera.py connect()
    - 要求：connect 成功后 if self not in _active_cameras: _active_cameras.append(self)

14. GigE 心跳超时是否缩短？
    - 文件：drivers/basler_camera.py _configure_camera()
    - 要求：GevHeartbeatTimeout = 3000

15. 60秒安全上限零帧时是否 fail-safe？
    - 文件：core/capture_window.py tick() CAPTURING 分支
    - 要求：零帧超时时创建 WindowResult(fault_code=3) 并调 _notify_complete()
    - 要求：不再静默回 IDLE
    - 验证：PLC 会收到 fault_code=3 → can_tip=False

═══════════════════════════════════════════
四、投票逻辑
═══════════════════════════════════════════

16. 故障帧是否排除在投票外？
    - 文件：core/capture_window.py _finalize_window()
    - 要求：只对 fault_code==0 的帧投票

17. 全故障帧时置信度是否为 LOW？
    - 文件：core/capture_window.py _finalize_window()
    - 要求：有效帧 < 50% 时 confidence="LOW", fault_code=最常见故障码

18. 采集安全上限（60秒）是否存在？
    - 文件：core/capture_window.py CaptureWindowConfig
    - 要求：max_capture_s 字段存在且默认 60.0

═══════════════════════════════════════════
五、鉴权与配置
═══════════════════════════════════════════

19. 默认密码是否有警告？
    - 文件：web/admin_api.py
    - 要求：ADMIN_PASSWORD == "admin123" 时 logger.warning

20. 登录是否有速率限制？
    - 文件：web/admin_api.py admin_auth()
    - 要求：5次失败锁定5分钟（按IP）

21. 所有写操作 API 是否需要鉴权？
    - 文件：web/unified_app.py
    - 要求：vision/enable, vision/disable, capture_config, reset_stats 都有 Depends(verify_admin)

22. 视觉启停失败是否返回非200？
    - 文件：web/unified_app.py api_vision_enable/disable
    - 要求：result 中有 "error" 时返回 502

23. PLC 为 None 时启停是否报错？
    - 文件：web/state_manager.py set_vision_enabled()
    - 要求：ms.plc is None 时回滚并返回错误

24. 阈值是否有边界校验？
    - 文件：web/state_manager.py update_thresholds()
    - 要求：VOTE_THRESHOLD <= VOTE_WINDOW_SIZE

25. capture_config 非法输入是否返回400？
    - 文件：web/unified_app.py api_update_capture_config()
    - 要求：float() 转换失败时返回 400

═══════════════════════════════════════════
六、生产环境保护
═══════════════════════════════════════════

26. 生产模式是否禁止回退 Mock？
    - 文件：drivers/factory.py create_camera/create_plc
    - 要求：DEV_MODE=False 时 ImportError 直接 raise，不回退 MockCamera/MockPLC

27. 后台 worker 是否独立于 WebSocket？
    - 文件：web/state_manager.py start_background_workers()
    - 要求：每个有相机的漏斗有独立后台线程
    - 要求：没人看页面时仍然响应 PLC 采集指令

28. 动态增删是否正确启停 worker？
    - 文件：web/state_manager.py add_machine/remove_machine/add_funnel/remove_funnel
    - 要求：add 后启动 worker，remove 前停止 worker

29. 看门狗是否存在？
    - 文件：start_production.bat
    - 要求：崩溃后自动重启

30. 日志是否写文件？
    - 文件：web/unified_app.py
    - 要求：loguru 配置了文件输出（每天切割，保留30天）

═══════════════════════════════════════════
七、已知限制（验证是否被安全处理）
═══════════════════════════════════════════

31. L1: 采集控制器 per-funnel 但 PLC 标签 per-machine
    - 临时方案：无相机漏斗不驱动 tick()
    - 验证：state_manager.py _bg_detection_loop 在 camera disconnected 时 continue 在 tick() 之前

32. L2: 配置变更非原子
    - 验证：_save_config 失败时有错误日志

33. L5: Token 无过期
    - 验证：已知限制，文档中有记录

34. L7: 报警记录不持久化
    - 验证：已知限制，日志文件可追溯

═══════════════════════════════════════════
输出格式
═══════════════════════════════════════════

对每项标注：
- PASS: 代码正确
- FAIL: 发现缺陷（文件名+行号+问题+修复建议）
- WARNING: 潜在风险（说明原因和接受条件）

统计：
- PASS 总数 / 34
- FAIL 总数（阻塞部署）
- WARNING 总数（不阻塞但需记录）

最终结论：
单相机配置下是否可以部署到工业生产环境？
```

---

## 审查文件清单

| 文件 | 关键检查点 |
|------|-----------|
| plc/allen_bradley.py | can_tip, result_valid, _io_lock, 心跳单源, update_heartbeat废弃 |
| algo/device_detector.py | 异常fail-safe, 画质fault_code传递 |
| algo/detector.py | 画质自检（分区+对比度+自适应） |
| core/capture_window.py | 投票排除故障帧, 安全上限零帧fail-safe, PLC触发 |
| web/state_manager.py | 后台worker, 相机重连, tick单源, 动态增删, 启停回滚 |
| web/unified_app.py | API鉴权, 启停返回码, send_json超时, snapshot API |
| web/common.py | 线程池隔离, executor超时, WS发送超时 |
| web/admin_api.py | 密码警告, 登录限速, 写操作鉴权 |
| drivers/basler_camera.py | 拒绝IP回退, GigE超时3s, atexit重注册 |
| drivers/factory.py | 生产禁止回退Mock |
| start_production.bat | 看门狗自动重启 |

## 累计修复统计

| 轮次 | 严重度 | 数量 |
|------|--------|------|
| 初始修复 | CRITICAL | 6 |
| 初始修复 | HIGH | 13 |
| 初始修复 | MEDIUM | 8 |
| R1审查 | FAIL | 4 |
| R2审查 | INCOMPLETE/FAIL | 4 |
| **合计** | | **35** |

## 已知限制（10条，已记录在整改文档）

详见 `docs/整改记录与已知限制.md` 和 `docs/improvement_report_v3.0.docx`
