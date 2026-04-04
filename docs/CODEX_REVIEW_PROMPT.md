# CODEX 审查提示词 — 翻车机积煤检测系统 V3.0

> 将以下内容粘贴到 Claude/GPT/Codex 中，让 AI 审查本项目代码

---

## 审查提示词

```
你是一位工业安全系统代码审查员。请审查以下 Python 工业视觉检测项目，该项目直接关联翻车机安全连锁，任何代码缺陷都可能导致翻车机误操作。

项目概述：
- 功能：通过 Basler 工业相机拍摄煤矿翻车机格栅画面，检测积煤覆盖，结果写入 AB PLC 控制翻车机允许/禁止翻转
- 核心原则：宁可漏报不可误报（误报→急停→煤车倾倒卡死设备）
- 技术栈：Python 3.10+ / OpenCV / pypylon / pycomm3 / FastAPI / loguru
- 架构：后台 worker 线程独立于 WebSocket 驱动检测，PLC 触发采集窗口

请重点审查以下文件和维度：

### 安全连锁链路（最高优先级）
1. `plc/allen_bradley.py` 的 `send_detection_result()`：
   - `can_tip` 的判定逻辑是否安全？`coal_present=None` 时是否拒绝？
   - `result_valid` 是否检查了 `fault_code`？
   - 心跳是否只在一个地方递增？是否有竞态条件？
   - PLC 读写的 `_io_lock` 是否所有路径都有超时？

2. `algo/device_detector.py` 的 `detect_device()`：
   - 画质自检失败时 `fault_code` 是否正确传递？
   - `device_has_coal=False` 在画质失败时是否安全？

3. `core/capture_window.py` 的 `_finalize_window()`：
   - 故障帧是否被排除在投票之外？
   - 全故障时置信度是否为 LOW？
   - 采集安全上限（60秒）是否生效？

### 并发安全
4. `web/state_manager.py` 的 `_bg_detection_loop()`：
   - 后台 worker 和 WebSocket 是否有并发 grab 相机的风险？
   - `tick()` 是否只由 worker 驱动（总览页不再调用）？
   - 多漏斗 worker 是否会争抢同一组 PLC 标签？
   - 动态增删翻车机/漏斗时 worker 生命周期是否正确？

5. `web/common.py` 的 `run_websocket_stream()`：
   - 三个线程池（grab/detect/default）是否独立？
   - 所有 `run_in_executor` 是否有超时保护？
   - WebSocket 发送是否有超时？

### 异常恢复
6. `web/state_manager.py` 相机重连逻辑：
   - 快速重连 5 次后是否转为慢速重连？
   - 重连成功后计数是否归零？
   - 相机 `fault_info` 是否正确更新？

7. `drivers/basler_camera.py`：
   - GigE 心跳超时是否设为 3 秒？
   - `atexit` 是否注册了全局清理？
   - 重连时是否先 release 再 connect？

### 配置与鉴权
8. `web/admin_api.py`：
   - 默认密码是否有启动警告？
   - 登录失败是否有速率限制？
   - 所有写操作 API 是否都需要鉴权？

9. `web/unified_app.py`：
   - 视觉启停失败是否返回 4xx/5xx（不是 200）？
   - PLC 写入失败是否回滚内存状态？

### 已知限制（验证是否被正确处理）
- L1: 采集控制器 per-funnel 但 PLC 标签 per-machine（临时方案：无相机不驱动）
- L2: 配置变更非原子
- L5: Token 无过期
- L7: 报警记录不持久化

### 输出格式
对每个问题标注：
- PASS: 代码正确
- FAIL: 发现缺陷（给出文件名、行号、具体问题、修复建议）
- WARNING: 潜在风险但不阻塞（说明原因）

最后给出总体评估：是否可以部署到工业生产环境。
```

---

## 审查范围文件清单

| 文件 | 行数 | 关键检查点 |
|------|------|-----------|
| plc/allen_bradley.py | ~570 | 安全信号、心跳、锁 |
| algo/detector.py | ~800 | 画质自检、判定逻辑 |
| algo/device_detector.py | ~250 | 设备级检测、fault_code |
| core/capture_window.py | ~400 | PLC 触发、投票、安全上限 |
| web/state_manager.py | ~750 | 后台 worker、重连、生命周期 |
| web/unified_app.py | ~500 | API、WebSocket、启停 |
| web/common.py | ~280 | 线程池、超时、推流 |
| web/admin_api.py | ~270 | 鉴权、速率限制 |
| drivers/basler_camera.py | ~400 | GigE 驱动、重连、释放 |
| drivers/factory.py | ~60 | 生产模式不回退 Mock |
| config/devices_config.py | ~200 | 拓扑配置加载 |

## 已修复漏洞数量

- CRITICAL: 6
- HIGH: 13
- MEDIUM: 8
- 已知限制: 10（已记录，接受风险）
