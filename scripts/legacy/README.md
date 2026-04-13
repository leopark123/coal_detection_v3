# Legacy Files (已归档)

这些文件属于旧的 main.py 单进程/双进程主线，已被统一 Web 主线 (`web/unified_app.py`) 取代。

## 归档原因
- 项目已收口到统一 Web 入口 (`start_production.bat` → `web.unified_app`)
- 15 轮 CODEX 安全审查仅覆盖统一主线
- PLC 现场已部署完整 9 标签采集窗口状态机，旧主线不支持

## 归档文件

| 文件 | 原路径 | 说明 |
|------|--------|------|
| main.py | / | 旧主入口（单进程检测循环 + 双进程模式） |
| start_dev.bat | / | 开发模式启动脚本（调用 main.py --dev） |
| start_prod.bat | / | 生产模式启动脚本（调用 main.py） |
| start_web.bat | / | 旧 Web 启动（调用 web.app，非 unified_app） |
| start_web_local.bat | / | 旧 Web 本地启动 |
| app.py | web/ | 旧单格栅 Web 应用（独立于 unified_app） |
| capture_process.py | core/ | 采集进程（双进程架构） |
| detect_process.py | core/ | 检测进程（双进程架构） |
| double_buffer.py | core/ | 共享内存双缓冲 |
| frame_state.py | core/ | 跨进程状态管理 |

## 当前正式入口
- 生产：`start_production.bat` → `web.unified_app`
- 开发：`start_unified.py` → `web.unified_app`
