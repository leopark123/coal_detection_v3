# CODEX 审查提示词 V16 - 主线收口 + 归档修复 综合审查

> 背景：项目从双主线并存（main.py + unified_app）收口为统一 Web 主线。
> 3 个 commit 的变更：归档旧入口 → CODEX 归档审查 → 4 项 FAIL 修复。
> 本审查覆盖归档操作、测试完整性、部署链路、运行时安全的全部面。
>
> 变更范围（3 个 commit）：
> - 28b34fb refactor: 收口统一Web主线，归档旧main.py双进程架构
> - 51094ba fix(archival): CODEX归档审查4项FAIL修复
> - 09bb4e9 fix(ui+safety): 漏斗详情页重构 + V15审查修复 + CODEX最终审查

---

## 审查方法

1. 按检查清单逐项验证
2. 每项执行实际命令/代码检查，不依赖假设
3. 输出格式：`[编号] [PASS/FAIL/WARNING]: 简要说明 + 证据路径`
4. 最终给出统计和部署建议

---

## A. 归档完整性（6 项）

**A1. 根目录入口收口**
- 验证根目录不存在 `main.py`、`start_dev.bat`、`start_prod.bat`、`start_web.bat`、`start_web_local.bat`
- 验证 `web/app.py` 不存在
- 验证以上文件全部在 `scripts/legacy/` 中
- 检查方法：`ls D:\coal_detection_project\*.py` + `ls D:\coal_detection_project\*.bat` + `ls D:\coal_detection_project\scripts\legacy\`

**A2. core/ 目录只剩活跃模块**
- `core/` 源码应只有 `__init__.py` 和 `capture_window.py`
- `capture_process.py`、`detect_process.py`、`double_buffer.py`、`frame_state.py` 应在 `scripts/legacy/`
- 额外检查：`core/__pycache__/` 中是否有旧模块的 `.pyc`（如有则是无害残留，记为 WARNING）

**A3. 断裂 import 已修复**
- 在整个项目中搜索以下 import（排除 `scripts/` 和 `archive/` 目录）：
  ```
  from main import
  import main
  from core.capture_process import
  from core.detect_process import
  from core.double_buffer import
  from core.frame_state import
  from web.app import
  ```
- 预期：匹配应仅在测试文件的 `skipif` 保护的方法内部（local import），或在文档/注释中
- 如果有未保护的顶层 import → FAIL

**A4. 测试 skip 保护正确**
- `tests/test_integration.py`：
  - `TestSystemIntegration` 类有 `@pytest.mark.skipif(not _has_main, ...)` 装饰器
  - `TestWebIntegration` 类有 `@pytest.mark.skipif(not _has_web_app, ...)` 装饰器
  - 原顶层 `from main import CoalDetectionSystem` 已移除
  - `CoalDetectionSystem` 只在 skipif 保护的方法内部 local import
- `tests/test_performance.py`：
  - `TestMultiProcessPerformance` 类有 `@pytest.mark.skipif(not _has_core_multiprocess, ...)` 装饰器
  - 原顶层 `from core.double_buffer/frame_state/capture_process/detect_process import` 已移除
  - 旧模块只在 skipif 保护的方法内部 local import
- `tests/test_web_routes_contract.py`：
  - `test_main_app_route_contract` 函数有 `@pytest.mark.skipif(not _has_web_app, ...)` 装饰器
  - 原顶层 `from web.app import app as main_app` 已移除
  - `web.app` 只在 skipif 保护的方法内部 local import

**A5. deploy_to_remote.bat 已更新**
- 不再复制 `main.py`
- 不再复制 `start_prod.bat`
- 改为复制 `start_unified.py`、`start_production.bat`、`start_monitor.bat`、`install_autostart.bat`、`install_service.bat`
- 生成的 `install_on_target.bat` 引导用户运行 `start_production.bat`（不是 `start_prod.bat`）
- 生成的部署说明中 IP 地址正确（192.168.1.12, 192.168.1.19, 端口 8080）

**A6. legacy README 准确**
- `scripts/legacy/README.md` 存在
- 列出的归档文件（10 个）与 `scripts/legacy/` 目录中的实际文件一致
- 注明了归档原因和当前正式入口

---

## B. 运行时安全（6 项）

**B7. 统一主线可导入**
- `python -c "from web.unified_app import app; print(type(app))"` 成功
- 不依赖任何已归档模块

**B8. pytest 全通过**
- `pytest tests/ -v --ignore=scripts/` 执行通过
- 预期结果：107 passed, 9 skipped, 0 failed
- 9 个 skip 分别是：
  - TestSystemIntegration (3)
  - TestWebIntegration (2)
  - TestMultiProcessPerformance (3)
  - test_main_app_route_contract (1)
- 如果有任何 FAIL 或额外 skip → 标记为 FAIL

**B9. 安全连锁逻辑未被归档操作影响**
- `plc/allen_bradley.py` 中 `send_detection_result()` 的 `can_tip` 判定仍是：
  ```python
  can_tip = (coal_present is False) and (not need_manual) and (fault_code == 0)
  ```
- `result_valid` 判定仍包含 `confidence in ("HIGH", "MEDIUM")` + `fault_code == 0` + `coal_present is not None`
- 确认这些安全关键代码在归档操作中**未被修改**

**B10. StateManager 不依赖已归档模块**
- `web/state_manager.py` 搜索：不 import `core.capture_process`、`core.detect_process`、`core.double_buffer`、`core.frame_state`
- 只依赖 `core.capture_window.CaptureWindowController`

**B11. core/__init__.py 文档已更新**
- 不再将 DoubleBuffer/FrameState/CaptureProcess/DetectProcess 列为当前组件
- 注明它们已归档

**B12. 心跳线程独立性**
- `plc/allen_bradley.py` 中 `_heartbeat_loop` 仍然独立运行
- 不依赖任何已归档的双进程模块
- `update_heartbeat()` 仍是 noop

---

## C. 文档一致性（5 项）

**C13. README.md 项目结构**
- 不再列出 `main.py` 作为入口
- 不再列出 `core/double_buffer.py`、`core/capture_process.py` 等已归档文件
- `core/` 部分只列出 `capture_window.py`
- 入口列出 `start_unified.py` 和 `start_production.bat`
- 列出 `scripts/legacy/` 为旧架构归档

**C14. README.md 内容准确**
- 快速开始命令指向 `web.unified_app`（不是 `main.py`）
- 漏斗详情页描述为"采集窗口时间线、设备状态"（不是"格栅热力图"）
- CODEX 审查引用指向 `docs/CODEX_FINAL_REVIEW.md`（不是旧版本）
- 安全漏洞数量为 65（不是 58）
- 审查轮次为 15（不是 12）
- Web 端口为 8080（不是 8000）

**C15. CLAUDE.md 目录结构**
- 与 README 一致，不包含已归档文件
- `web/` 部分列出 `unified_app.py` 为主应用
- 根目录入口正确

**C16. 无死链引用**
- 在 README.md 和 CLAUDE.md 中搜索 `main.py`、`start_dev.bat`、`start_prod.bat`、`web/app.py`
- 这些引用应不存在，或仅在历史说明/归档上下文中出现
- 如果有"运行 main.py"之类的指令仍然存在 → FAIL

**C17. deploy 部署说明一致**
- `deploy_to_remote.bat` 生成的部署说明中：
  - 启动命令指向 `start_production.bat`
  - IP 地址：相机 192.168.1.12，PLC 192.168.1.19
  - 端口 8080
  - 无 `main.py` 或 `start_prod.bat` 引用

---

## D. 环境清洁（5 项）

**D18. 根目录无杂物**
- 不存在 `Ctemp`（含全角冒号变体）
- 不存在 `Ctempgit_status.txt`
- 不存在 `Dcoal_detection_project_*.txt`
- 不存在 `pytest-cache-files-*` 目录
- 根目录所有文件/目录都是项目正式组成部分

**D19. .gitignore 有效**
- `logs/` 被忽略
- `__pycache__/` 被忽略
- `*.pyc` 被忽略
- `.pytest_cache/` 被忽略
- `coal_detection_deploy/` 被忽略（部署包不入库）

**D20. 无多余启动脚本**
- 根目录 `.bat` 文件只有：`start_production.bat`、`start_monitor.bat`、`install_autostart.bat`、`install_service.bat`、`deploy_to_remote.bat`
- 没有 `start_dev.bat`、`start_prod.bat`、`start_web.bat`、`start_web_local.bat`

**D21. 旧 __pycache__ 清理**
- 检查 `core/__pycache__/` 中是否有旧模块编译缓存（`frame_state.*.pyc`、`double_buffer.*.pyc` 等）
- 如有，记为 WARNING（无害但不整洁）
- 建议运行 `find . -type d -name __pycache__ -exec rm -rf {} +` 清理

**D22. devices.yaml 配置检查**
- 当前配置的翻车机/漏斗数量是否与现场一致？
- 现场实际：1 台翻车机、1 个漏斗、相机 192.168.1.12、PLC 192.168.1.19
- 如果配置仍是多机模板（2 机 10 漏斗），记为 WARNING（不阻断部署但应调整）

---

## E. 安全回归验证（5 项）

> 确认归档操作没有意外影响之前 15 轮 CODEX 审查通过的安全项

**E23. can_tip 安全信号未变**
- `plc/allen_bradley.py` 中 `can_tip` 判定逻辑与 V15 审查时一致
- `coal_present is False`（不是 `not coal_present`）

**E24. 采集窗口状态机完整**
- `core/capture_window.py` 仍存在于活跃目录（没有被误归档）
- 状态流转：IDLE → CAPTURING → COMPLETE → IDLE
- 60s 超时 fail-safe 仍在
- `_finalize_window()` 仍排除 fault 帧

**E25. 后台 worker 独立于 WebSocket**
- `web/state_manager.py` 中 `start_background_workers()` 仍在 lifespan 启动
- `_bg_detection_loop()` 不依赖 WebSocket 连接

**E26. 鉴权体系完整**
- `web/admin_api.py` 仍有 `verify_admin` 依赖
- 所有写入 API（vision/enable、vision/disable、capture_config）仍需管理员 token
- 登录限流（5 次 5 分钟锁定）仍在

**E27. 故障闭环 9 路径仍在**
- `web/state_manager.py` 中 `add_fault_event()` 仍覆盖：
  - 相机断开/未连接/重连成功
  - PLC 初始化成功/失败
  - PLC 运行时断连/重连
  - PLC 动态新增成功/失败

---

## 输出格式

```
每项一行：
[编号] [PASS/FAIL/WARNING]: 简要说明

如 FAIL/WARNING，附上相关文件路径和行号

最终统计：
PASS: X / 27
FAIL: X / 27
WARNING: X / 27

结论：
- FAIL=0 且 WARNING≤3：可以部署
- FAIL>0：必须修复后重审
```

## 评判标准

| 级别 | 含义 |
|------|------|
| FAIL | 存在断裂依赖、运行时崩溃风险、安全信号受影响、文档指向不存在的文件 |
| WARNING | 不影响运行但应改进（如 __pycache__ 残留、配置是模板不是实配） |
| PASS | 完全符合要求 |
