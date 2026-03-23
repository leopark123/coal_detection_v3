# 煤检测项目交接包

本目录用于在不同 AI/开发者之间无损衔接，保证“模拟阶段先验证、生产链路后落地”。

## 当前基线（2026-02-19）

- 项目目录: `E:\DAYDAYUP\coal_detection_project`
- 当前阶段: 模拟开发阶段（手动添加照片）
- 生产链路: 暂未开发（待测试稳定后推进）
- 自动化测试: `python -m pytest -q` => `66 passed, 1 skipped`

## 文件说明

- `handoff/开发计划.md`: 阶段目标与里程碑。
- `handoff/开发进度表.csv`: 工作包状态、阻塞、下一步。
- `handoff/开发约束表.csv`: 当前边界条件与禁止事项。
- `handoff/上下文衔接表.md`: 每轮结束必须追加衔接记录。
- `handoff/决策记录表_ADR.csv`: 关键取舍与回滚策略。
- `handoff/缺陷跟踪表.csv`: 缺陷生命周期。
- `handoff/测试与验收表.csv`: 测试执行与证据。
- `handoff/AI切换SOP.md`: AI 接手标准流程。
- `handoff/启动提示词.txt`: 新 AI 可直接粘贴使用。
- `handoff/变更日志表.csv`: 范围/需求变更记录。
- `handoff/接口契约表.csv`: 模块接口契约。
- `handoff/数据集与标注表.csv`: 图像样本与标注版本记录。

## 使用顺序

1. 读取 `handoff/上下文衔接表.md` 最后一条记录。
2. 对照 `handoff/开发计划.md` 确认当前阶段目标。
3. 更新 `handoff/开发进度表.csv` 的进行中任务。
4. 本轮如有新限制，先改 `handoff/开发约束表.csv`。
5. 本轮结束回填 `ADR/缺陷/测试`，并追加衔接记录。
