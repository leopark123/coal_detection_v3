# CODEX 审查提示词 - 主线收口与归档验证

> 背景：项目从双主线并存（main.py + unified_app）收口为统一 Web 主线。
> 旧 main.py 及其关联的双进程模块、启动脚本已归档到 `scripts/legacy/`。
> 本审查验证归档操作的完整性和安全性，确保没有断裂依赖。

---

## 审查范围

```
提交: 28b34fb refactor: 收口统一Web主线，归档旧main.py双进程架构
分支: feature/project-restructure
```

## 检查清单

### A. 归档完整性（5 项）

**A1. 旧入口已移除**
- 验证根目录不存在 `main.py`
- 验证根目录不存在 `start_dev.bat`、`start_prod.bat`、`start_web.bat`、`start_web_local.bat`
- 验证 `web/app.py` 不存在
- 所有上述文件应在 `scripts/legacy/` 中找到
- 检查方法：`ls *.py *.bat` 对比 `ls scripts/legacy/`

**A2. 双进程模块已移除**
- 验证 `core/` 目录下只剩 `__init__.py` 和 `capture_window.py`
- `capture_process.py`、`detect_process.py`、`double_buffer.py`、`frame_state.py` 应在 `scripts/legacy/`
- 检查方法：`ls core/`

**A3. 无断裂 import**
- 在整个项目中搜索以下 import（排除 scripts/ 和 archive/）：
  ```
  from core.capture_process import
  from core.detect_process import
  from core.double_buffer import
  from core.frame_state import
  from web.app import
  import main
  ```
- 预期结果：0 处匹配（仅 `tests/test_performance.py` 可能有，需确认是否仍能运行）

**A4. 生产入口完整**
- `start_production.bat` 存在且指向 `web.unified_app`
- `start_unified.py` 存在且指向 `web.unified_app`
- `install_autostart.bat` 引用 `start_production.bat`（不是旧脚本）
- `install_service.bat` 引用 `start_production.bat`（不是旧脚本）
- `deploy_to_remote.bat` 不依赖已归档文件

**A5. legacy README 准确**
- `scripts/legacy/README.md` 存在
- 列出的文件与实际归档文件一致
- 归档原因描述准确

### B. 运行时安全（5 项）

**B6. 统一主线可启动**
- `python -c "from web.unified_app import app; print('OK')"` 不报 ImportError
- 确认 `web.unified_app` 不依赖任何已归档模块

**B7. StateManager 独立性**
- `web/state_manager.py` 不 import 任何 `core.capture_process`、`core.detect_process`、`core.double_buffer`、`core.frame_state`
- 它只使用 `core.capture_window.CaptureWindowController`

**B8. 测试可运行**
- `pytest tests/ -v --ignore=scripts/` 全部通过
- 如果 `test_performance.py` 依赖已归档模块，应跳过或标记 xfail，不应 import error

**B9. core/__init__.py 更新**
- 文档字符串不再引用 DoubleBuffer、FrameState、CaptureProcess、DetectProcess 为当前组件
- 应注明它们已归档

**B10. CLAUDE.md 目录结构**
- 目录树中不再包含 `main.py`、`start_dev.bat` 等已归档条目
- `core/` 部分只列出 `capture_window.py`
- `web/` 部分列出 `unified_app.py` 为主应用，不再列出 `app.py`
- 根目录入口列出 `start_unified.py` 和 `start_production.bat`

### C. 配置一致性（5 项）

**C11. devices.yaml 与现场硬件**
- 当前 `config/devices.yaml` 配置了几台翻车机、几个漏斗？
- 现场实际：1 台翻车机、1 个漏斗、相机 192.168.1.12、PLC 192.168.1.19
- 如果配置是多机模板（2 机 10 漏斗），记录为 WARNING（不阻断，但建议收缩）

**C12. PLC 标签完整性**
- `plc/allen_bradley.py` 中使用的标签名与现场 PLC 标签名精确匹配：
  - IPC_Heartbeat, IPC_Online
  - Vision_CanTip, Vision_FaultCode, Vision_ResultValid
  - Vision_Enable, Vision_CaptureState
  - PLC_CaptureCmd, Tipper_InPosition
- 大小写、下划线必须完全一致

**C13. hardware_test.py 覆盖度**
- `tools/hardware_test.py` 测试了哪些 PLC 标签？
- 如果只测试 5 个（缺 Vision_Enable、Vision_CaptureState、PLC_CaptureCmd、Tipper_InPosition），记录为 WARNING

**C14. 采集窗口状态机依赖**
- `core/capture_window.py` 读写哪些 PLC 标签？
- 确认这些标签在 `plc/allen_bradley.py` 中有对应的读写方法
- 确认 `CaptureWindowController` 的状态流转：IDLE → CAPTURING → JUDGING → COMPLETE → IDLE

**C15. 配置加载链路**
- `web/unified_app.py` 的 lifespan 中：
  1. 加载 Config → 确认路径
  2. 加载 devices.yaml → 确认用 `DevicesConfig.from_yaml()`
  3. 初始化 StateManager → 确认传入正确的 config 和 devices
  4. 启动后台 worker → 确认调用 `start_background_workers()`

### D. 杂物清理（3 项）

**D16. 根目录无临时文件**
- 不存在 `Ctempgit_status.txt`、`Dcoal_detection_project_install.txt`、`Dcoal_detection_project_pr2.txt`、`Dcoal_detection_projecttmp_status.txt`
- 根目录的文件应全部是项目正式文件

**D17. .gitignore 检查**
- `logs/` 是否在 .gitignore 中？（21GB 图像目录不应被跟踪）
- `__pycache__/`、`*.pyc` 是否被忽略？
- 临时文件模式是否被忽略？

**D18. 无死链引用**
- README.md 中引用的入口、命令是否指向现有文件？
- 不应引用 `main.py`、`start_dev.bat` 等已归档文件
- 如果 README 仍引用旧入口，记录为 FAIL

---

## 输出格式

```
每项输出一行：
[编号] [PASS/FAIL/WARNING]: 简要说明

最终统计：
PASS: X / 18
FAIL: X / 18
WARNING: X / 18

结论：[是否可以继续部署]
```

## 评判标准

- FAIL = 存在断裂依赖、运行时会崩溃、安全信号受影响
- WARNING = 不影响运行但应改进
- PASS = 符合要求
