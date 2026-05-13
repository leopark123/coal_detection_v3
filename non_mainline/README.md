# Non-Mainline 分类说明

当前统一 Web 主线直接依赖的目录保留在根目录：

- `algo/`
- `config/`
- `core/`
- `drivers/`
- `plc/`
- `web/`
- `tests/`
- `tools/`

其余与主线运行无直接依赖的内容统一收纳到 `non_mainline/`，按职责分类：

## history

- `history/scripts/legacy/`
  旧 `main.py + web.app + 双进程` 主线归档。
- `history/archive/`
  更早期的实验脚本、迁移快照、标定工具、历史打包产物。

## documentation

- `documentation/docs/`
  设计方案、部署说明、CODEX 审查文档、PLC 点位文档。
- `documentation/handoff/`
  交接材料、ADR、接口契约、台账、计划表。

## artifacts

- `artifacts/root_cache/`
  从根目录收纳的缓存与运行产物，如 `__pycache__/`、`.pytest_cache/`、`.coverage`。

说明：

- `logs/` 仍保留在根目录，因为当前运行主线会直接写入该目录。
- `tools/` 仍保留在根目录，因为硬件联调和现场辅助脚本仍在使用。
