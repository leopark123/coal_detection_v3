# CODEX 最终全面审查提示词 — 翻车机积煤检测系统 V3.0

> 合并 15 轮迭代审查，一次性全面审查整个项目。累计修复 60 项。

---

## 审查提示词

```
你是工业安全系统代码审查员。这是最终全面审查（合并 15 轮迭代）。

项目：煤矿翻车机积煤检测系统 V3.0
功能：Basler 工业相机拍摄格栅 → YOLO/CV 检测 → PLC 安全连锁控制翻车机
核心原则：宁可漏报不可误报（误报→急停→煤车倾倒卡死设备）
累计修复：60 项安全漏洞（经 15 轮审查）

请按以下 8 大类 50 个检查点逐项审查。

═══════════════════════════════════════════════════════
一、安全连锁链路（最高优先级，10 项）
═══════════════════════════════════════════════════════

1. can_tip 判定
   - 文件：plc/allen_bradley.py send_detection_result()
   - 要求：can_tip = (coal_present is False) and (not need_manual) and (fault_code == 0)
   - 验证：coal_present=None → can_tip=False

2. result_valid 判定
   - 要求：confidence in ("HIGH","MEDIUM") and (fault_code == 0) and (coal_present is not None)

3. detect_device 异常 fail-safe
   - 文件：algo/device_detector.py detect_device()
   - 验证：except Exception 和 else(空 grid_details) 分支都设 fault_code=3

4. 画质自检
   - 文件：algo/detector.py _check_quality()
   - 验证：分区评估+对比度+自适应模糊（不是全局 mean 一刀切）
   - 验证：quality_ok=False → fault_code=3 传递到 DeviceResult

5. 窗口投票 — 故障帧排除
   - 文件：core/capture_window.py _finalize_window()
   - 验证：只对 fault_code==0 的帧投票
   - 验证：有效帧<50% → confidence=LOW + fault_code

6. 安全上限零帧 fail-safe
   - 文件：core/capture_window.py tick() CAPTURING 分支
   - 验证：60秒超时且零帧 → WindowResult(fault_code=3) + _notify_complete

7. PLC 梯形图对齐
   - 验证：Rung4 = Vision_Enable=0 直接允许 OR (Alive+CanTip+Valid+Fault=0)
   - 代码侧 Vision_Enable=False 时写 CanTip=True + FaultCode=0

8. 心跳单源
   - 验证：update_heartbeat() 已废弃为 noop
   - 验证：只有 _heartbeat_loop 递增 heartbeat_value
   - 验证：_heartbeat_value_lock 保护递增

9. 视觉启停鉴权
   - 文件：web/unified_app.py api_vision_enable/disable
   - 验证：Depends(verify_admin)
   - 验证：前端 toggleVision 从 sessionStorage 读 adminToken
   - 验证：无 token 时提示"请先登录"，不发匿名请求
   - 验证：401 响应正确处理（检查 r.ok，读 d.detail）
   - 验证：不做乐观更新（等 WebSocket 推送真实状态）

10. PLC 写入失败回滚
    - 文件：web/state_manager.py set_vision_enabled()
    - 验证：PLC 写入失败 → 回滚 vision_enabled + capture_controller
    - 验证：PLC 为 None → 回滚并返回错误
    - 验证：返回 502（不是 200）

═══════════════════════════════════════════════════════
二、并发安全（8 项）
═══════════════════════════════════════════════════════

11. _io_lock 全部超时
    - 文件：plc/allen_bradley.py
    - 验证：搜索确认不存在 "with self._io_lock:"
    - 验证：所有使用点 acquire(timeout=self._io_lock_timeout) + try/finally

12. 线程池隔离
    - 文件：web/common.py
    - 验证：_grab_executor(4) 和 _detect_executor(8) 独立
    - 验证：run_in_executor 都有 asyncio.wait_for 超时

13. WebSocket 不 grab 相机
    - 文件：web/unified_app.py funnel_ws()
    - 验证：只读 fs.last_frame/last_result，不调 camera.grab()

14. tick() 单源驱动
    - 验证：只有 _bg_detection_loop 调 cc.tick()
    - 验证：get_overview_data 不调 tick()

15. 所有 send_json 有超时
    - 搜索所有 send_json 调用（common.py + unified_app.py）
    - 验证：全部包 asyncio.wait_for(timeout=5.0)

16. 后台 worker 独立于 WebSocket
    - 验证：没人看页面时仍响应 PLC 采集指令
    - 验证：start_background_workers() 在 lifespan 中调用

17. 动态增删启停 worker
    - 验证：add_machine/add_funnel 启动 worker
    - 验证：remove_machine/remove_funnel 停止 worker

18. 多漏斗不争抢 PLC 标签
    - 验证：_ever_connected=False 的漏斗不调 tick()
    - 验证：不存在的 IP 不枚举 pypylon

═══════════════════════════════════════════════════════
三、异常恢复（8 项）
═══════════════════════════════════════════════════════

19. 相机 IP 不匹配拒绝
    - 文件：drivers/basler_camera.py connect()
    - 验证：raise ConnectionError，不回退第一台

20. 相机重连策略
    - _ever_connected=True → 快速5次(10s) → 慢速(60s)永不放弃
    - _ever_connected=False → 不重连，状态 not_available

21. GigE 心跳超时 3 秒
    - 文件：drivers/basler_camera.py _configure_camera()
    - 验证：GevHeartbeatTimeout = 3000

22. atexit 重连后重注册
    - 文件：drivers/basler_camera.py connect()
    - 验证：成功后 if self not in _active_cameras: append

23. PLC 断连边沿通知
    - 验证：_notify_disconnect 在所有 is_connected=False 路径后调用
    - 验证：write/read/check_connection/heartbeat 全覆盖
    - 验证：_was_connected 边沿触发不重复

24. PLC 重连边沿通知
    - 验证：_notify_connect 在 _try_reconnect_inline 成功后调用
    - 验证：不存在 _was_connected 预赋值抑制

25. PLC 重连后 CaptureState 重置
    - 文件：web/state_manager.py _register_plc_callback() connected 分支
    - 验证：遍历漏斗 → _phase=IDLE + _write_plc_state(0)
    - 验证：写失败 → _needs_state_reset=True
    - 验证：不 sleep（不阻塞心跳线程）

26. tick() 异步重试 State=0
    - 文件：core/capture_window.py tick() IDLE 分支
    - 验证：_needs_state_reset 检查在 poll_interval 内
    - 验证：成功后清除标志
    - 验证：__init__ 中初始化 _needs_state_reset=False

═══════════════════════════════════════════════════════
四、鉴权与输入校验（6 项）
═══════════════════════════════════════════════════════

27. 默认密码警告
    - 文件：web/admin_api.py
    - 验证：ADMIN_PASSWORD=="admin123" 时 logger.warning

28. 登录速率限制
    - 验证：5次失败锁定5分钟（按 IP）

29. 所有写 API 鉴权
    - vision/enable, vision/disable, capture_config, reset_stats
    - 验证：都有 Depends(verify_admin) 或 x_admin_token

30. ID 白名单校验
    - 文件：config/devices_config.py _validate_id()
    - 验证：^[A-Za-z0-9_-]+$
    - 验证：from_yaml + admin_api add_machine/add_funnel 都调用
    - 验证：非法 ID → HTTPException(400)

31. 阈值边界校验
    - 文件：web/state_manager.py update_thresholds()
    - 验证：VOTE_THRESHOLD <= VOTE_WINDOW_SIZE

32. capture_config 非法输入
    - 验证：float() 转换失败 → 400

═══════════════════════════════════════════════════════
五、生产环境保护（4 项）
═══════════════════════════════════════════════════════

33. 生产模式禁止回退 Mock
    - 文件：drivers/factory.py
    - 验证：DEV_MODE=False 时 ImportError 直接 raise

34. 看门狗自重启
    - 文件：start_production.bat
    - 验证：崩溃后自动重启

35. 日志文件输出
    - 文件：web/unified_app.py
    - 验证：loguru 配置文件输出（每天切割，保留 30 天）

36. 开机自启
    - 文件：install_autostart.bat
    - 验证：Windows 启动文件夹快捷方式

═══════════════════════════════════════════════════════
六、故障报警系统（6 项）
═══════════════════════════════════════════════════════

37. 故障事件 9 条路径闭环
    - 相机断开/从未连接/重连成功
    - PLC 初始化成功/失败
    - PLC 运行时断连/重连
    - PLC 动态新增成功/失败
    - 验证：每条路径有 add_fault_event 调用

38. faults API 数据结构
    - 文件：web/state_manager.py get_all_faults()
    - 验证：每条 fault 有 machine_id 字段
    - 验证：相机 fault 有 funnel_id 字段
    - 验证：PLC fault 有 status_display + reconnect_attempts（同构）

39. 故障面板前端匹配
    - 文件：web/templates/funnel_detail.html
    - 验证：相机按 f.machine_id === machineId && f.funnel_id === funnelId 精确匹配
    - 验证：PLC 按 f.machine_id === machineId 精确匹配
    - 验证：不使用 indexOf 模糊匹配

40. 总览页故障横幅
    - 文件：web/templates/overview.html
    - 验证：覆盖 disconnected + not_available + stopped 三种状态
    - 验证：XSS 转义（esc 函数）

41. 故障事件日志
    - 验证：最近 20 条事件
    - 验证：绿色=*_ok，红色=其他

42. 采集窗口记录
    - 验证：用 window_end 时间戳去重（不是帧数）
    - 验证：最多 15 条

═══════════════════════════════════════════════════════
七、UI 与前端安全（5 项）
═══════════════════════════════════════════════════════

43. 侧边栏导航
    - 验证：sidebar.css/js/html 三文件
    - 验证：4 个模板都有 {% include %} + app-layout 包裹
    - 验证：settings.html 类名改为 .settings-sidebar（不冲突）

44. 总览页增量更新
    - 验证：不用 innerHTML 全量重建
    - 验证：animate-in 只在首次创建时播放

45. 所有 innerHTML 动态内容 XSS
    - 搜索所有 innerHTML 赋值
    - 验证：用户可控内容经过 esc()/escapeHtml()/escSidebar() 转义
    - 验证：异常对象用 esc(String(e))

46. grid_details 序列化
    - 文件：algo/device_detector.py to_dict()
    - 验证：bool() 强转（防 numpy.bool_）

47. 时间格式统一
    - 验证：所有前端时间显示精确到秒
    - 验证：后端 add_fault_event 用 %Y-%m-%d %H:%M:%S

═══════════════════════════════════════════════════════
八、已知限制验证（3 项）
═══════════════════════════════════════════════════════

48. L1: 采集控制器 per-funnel
    - 验证：无相机漏斗不驱动 tick()（临时方案有效）

49. L5: Token 无过期
    - 验证：已知限制，文档中有记录

50. L7: 报警不持久化
    - 验证：已知限制，日志文件可追溯

═══════════════════════════════════════════════════════
输出格式
═══════════════════════════════════════════════════════

对每项标注 PASS / FAIL / WARNING。

统计：PASS / FAIL / WARNING 总数

最终结论（三选一）：
A. 单相机配置可以部署到工业生产环境
B. 有条件可以部署（列出条件）
C. 不可以部署（列出阻断项）
```

---

## 审查文件清单

| 文件 | 行数 | 关键检查 |
|------|------|----------|
| plc/allen_bradley.py | ~600 | 安全信号+心跳+锁+边沿通知 |
| algo/detector.py | ~800 | 画质自检+判定 |
| algo/device_detector.py | ~260 | 异常fail-safe+grid_details序列化 |
| core/capture_window.py | ~450 | 投票+安全上限+State重置重试 |
| web/state_manager.py | ~850 | 后台worker+重连+故障事件+PLC回调 |
| web/unified_app.py | ~550 | API+WebSocket+鉴权 |
| web/common.py | ~280 | 线程池+超时+推流 |
| web/admin_api.py | ~280 | 鉴权+登录限速+ID校验 |
| drivers/basler_camera.py | ~420 | GigE+重连+atexit |
| drivers/factory.py | ~60 | 生产禁回退Mock |
| web/templates/*.html | ~1500 | 侧边栏+故障面板+XSS |
| web/static/css/sidebar.css | ~160 | 收起/展开 |
| web/static/js/sidebar.js | ~120 | 设备树+高亮 |

## 累计修复统计

| 轮次 | 数量 | 关键 |
|------|------|------|
| 初始 | 27 | 6C+13H+8M |
| R1-R2 | 8 | 审查修复 |
| R3 | 1 | pypylon崩溃 |
| R4 | 1 | 永不放弃重连 |
| R5-R9 | 15 | 故障面板+事件+ID+边沿 |
| R10-R12 | 5 | State重置+自审查 |
| R13 | 2 | 侧边栏类名+遮罩 |
| R14 | 1 | 启停鉴权前端 |
| R15 | 5 | faults精确匹配+去重+grid_details |
| **合计** | **65** |
