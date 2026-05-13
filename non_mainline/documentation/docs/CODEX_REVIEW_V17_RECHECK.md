# CODEX 复查提示词 V17 - V16 审查 FAIL/WARNING 修复验证

> 背景：V16 审查结果 21 PASS / 2 FAIL / 4 WARNING。
> 本次修复提交：`0b404d0 fix: V16审查2项FAIL修复 + 环境清理`
> 本复查仅验证 2 个 FAIL 是否修复 + 4 个 WARNING 是否改善，不重复已 PASS 项。

---

## FAIL 修复验证（2 项）

**F1. [C16] CLAUDE.md 旧运行指令**
- 原问题：CLAUDE.md 第 651、671 行仍有 `python main.py --dev` 和 `python main.py --config ...`
- 验证：在 CLAUDE.md 中搜索 `main.py`
  - 部署指令部分不应出现 `python main.py`
  - 开发环境应指向 `python start_unified.py` 或 `python -m uvicorn web.unified_app:app`
  - 生产环境应指向 `start_production.bat` 或 `python -m uvicorn web.unified_app:app`
- 注意：`main.py` 可以出现在历史说明或归档描述上下文中，但不能出现在可执行指令中
- PASS 条件：部署章节（11.1、11.2）中不再有 `python main.py` 命令

**F2. [D19] .gitignore 覆盖不全**
- 原问题：只忽略 `logs/images/` 和 `logs/*.log`，未忽略整个 `logs/`；缺少 `coal_detection_deploy/`
- 验证：读取 `.gitignore`，确认：
  - 存在 `logs/` 规则（忽略整个日志目录）
  - 存在 `coal_detection_deploy/` 规则（忽略部署打包产物）
- PASS 条件：两条规则都存在

---

## WARNING 改善验证（4 项）

**W3. [A2/D21] core/__pycache__ 旧模块缓存**
- 原问题：`core/__pycache__/` 中残留 `capture_process`、`detect_process`、`double_buffer`、`frame_state` 的 `.pyc`
- 验证：列出 `core/__pycache__/` 内容
- PASS 条件：不存在上述旧模块的 `.pyc` 文件
- 降级为 PASS 或维持 WARNING

**W4. [D18] 根目录运行残留**
- 原问题：根目录存在 `__pycache__/`、`.pytest_cache/`、`.coverage`
- 验证：检查根目录是否仍有这些
- 注意：这些是运行时产物，受 `.gitignore` 保护不会入库，存在是正常的
- PASS 条件：`.gitignore` 中有对应规则（`__pycache__/`、`.pytest_cache/`、`.coverage`）

**W5. [D22] devices.yaml 仍是多机模板**
- 原问题：配置 2 台翻车机 + 多漏斗，与现场 1 机 1 漏斗不一致
- 验证：读取 `config/devices.yaml`，统计机器数和漏斗数
- 注意：这是配置问题不是代码问题，不阻断部署
- PASS 条件：维持 WARNING 即可（现场部署时调整）

**W6. [A2 重复] core/__pycache__ 同 W3**
- 与 W3 相同，合并验证

---

## 输出格式

```
[F1] [PASS/FAIL]: 说明
[F2] [PASS/FAIL]: 说明
[W3] [PASS/WARNING]: 说明
[W4] [PASS/WARNING]: 说明
[W5] [PASS/WARNING]: 说明

统计：
FAIL 修复: X/2 → PASS
WARNING 改善: X/4 → PASS 或维持 WARNING

结论：
- 2 FAIL 全部修复 → 可合并到 V16 结果更新为 23+ PASS
- 仍有 FAIL → 需继续修复
```
