"""
翻车机积煤检测系统 V3.0 - Web 监控界面

特性：
1. 自适应布局 - 支持不同分辨率无缝切换（By Gemini）
2. WebSocket 实时推流
3. 检测结果展示
4. 参数配置

运行：
    uvicorn web.app:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config
from drivers.factory import create_camera
from algo.detector import CoalDetector, DetectionResult
from web.common import (
    apply_mock_source_from_env,
    apply_sample_resolution,
    mount_static,
    read_bool_env,
    run_websocket_stream,
    StreamAppState,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan hook."""
    await startup()
    try:
        yield
    finally:
        await shutdown()


app = FastAPI(title="翻车机积煤检测系统 V3.0", lifespan=lifespan)

# 静态文件
mount_static(app, static_dir=str(Path(__file__).parent / "static"), create_dirs=True)


# HTML 模板（内嵌，便于开发）
INDEX_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>翻车机积煤检测系统 V3.0</title>
    <style>
        /* ═══════════════════════════════════════════════════════════
           自适应布局 - By Gemini 建议
           关键：使用百分比和 max-width，而不是固定像素值
           这样在 1024x768 开发和 3072x2048 生产环境都能正常显示
        ═══════════════════════════════════════════════════════════ */
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
        }
        
        .header {
            background: #16213e;
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #0f3460;
        }
        
        .header h1 {
            font-size: 1.5rem;
            color: #00d9ff;
        }
        
        .status-badge {
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9rem;
        }
        
        .status-normal { background: #00c853; color: #000; }
        .status-warning { background: #ffc107; color: #000; }
        .status-alarm { background: #ff1744; color: #fff; animation: pulse 1s infinite; }
        .status-unknown { background: #9e9e9e; color: #fff; }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .main-container {
            display: flex;
            flex-wrap: wrap;
            padding: 1rem;
            gap: 1rem;
            max-width: 1800px;
            margin: 0 auto;
        }
        
        /* ★ 关键：视频容器自适应 */
        .video-section {
            flex: 2;
            min-width: 300px;
            max-width: 100%;
        }
        
        .video-container {
            background: #000;
            border-radius: 8px;
            overflow: hidden;
            position: relative;
            /* ★ 保持宽高比 16:9 的技巧 */
            padding-top: 56.25%;
        }
        
        .video-container img {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: contain;  /* ★ 关键：保持比例，不拉伸 */
        }
        
        .info-section {
            flex: 1;
            min-width: 280px;
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }
        
        .card {
            background: #16213e;
            border-radius: 8px;
            padding: 1rem;
            border: 1px solid #0f3460;
        }
        
        .card h3 {
            color: #00d9ff;
            margin-bottom: 1rem;
            font-size: 1rem;
            border-bottom: 1px solid #0f3460;
            padding-bottom: 0.5rem;
        }
        
        .metric {
            display: flex;
            justify-content: space-between;
            padding: 0.5rem 0;
            border-bottom: 1px solid #0f346033;
        }
        
        .metric:last-child {
            border-bottom: none;
        }
        
        .metric-label {
            color: #888;
        }
        
        .metric-value {
            font-weight: bold;
            font-family: 'Courier New', monospace;
        }
        
        .metric-value.good { color: #00c853; }
        .metric-value.warning { color: #ffc107; }
        .metric-value.danger { color: #ff1744; }
        
        .progress-bar {
            width: 100%;
            height: 8px;
            background: #0f3460;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 0.25rem;
        }
        
        .progress-fill {
            height: 100%;
            transition: width 0.3s, background 0.3s;
        }
        
        .log-container {
            max-height: 200px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 0.8rem;
            background: #0a0a15;
            padding: 0.5rem;
            border-radius: 4px;
        }
        
        .log-entry {
            padding: 0.25rem 0;
            border-bottom: 1px solid #1a1a2e;
        }
        
        .log-time { color: #666; }
        .log-info { color: #00d9ff; }
        .log-warn { color: #ffc107; }
        .log-error { color: #ff1744; }
        
        /* 响应式布局 */
        @media (max-width: 768px) {
            .main-container {
                flex-direction: column;
            }
            .video-section, .info-section {
                flex: none;
                width: 100%;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🏭 翻车机积煤检测系统 V3.0</h1>
        <div id="status-badge" class="status-badge status-unknown">连接中...</div>
    </div>
    
    <div class="main-container">
        <div class="video-section">
            <div class="video-container">
                <img id="video-feed" src="" alt="实时画面">
            </div>
        </div>
        
        <div class="info-section">
            <div class="card">
                <h3>📊 检测结果</h3>
                <div class="metric">
                    <span class="metric-label">积煤判定</span>
                    <span id="coal-result" class="metric-value">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">置信度</span>
                    <span id="confidence" class="metric-value">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">格栅可见率</span>
                    <span id="grid-ratio" class="metric-value">-</span>
                </div>
                <div class="progress-bar">
                    <div id="grid-progress" class="progress-fill" style="width: 0%; background: #00c853;"></div>
                </div>
                <div class="metric">
                    <span class="metric-label">积煤覆盖率</span>
                    <span id="coal-coverage" class="metric-value">-</span>
                </div>
                <div class="progress-bar">
                    <div id="coverage-progress" class="progress-fill" style="width: 0%; background: #00c853;"></div>
                </div>
            </div>
            
            <div class="card">
                <h3>⚡ 性能指标</h3>
                <div class="metric">
                    <span class="metric-label">帧号</span>
                    <span id="frame-id" class="metric-value">0</span>
                </div>
                <div class="metric">
                    <span class="metric-label">处理耗时</span>
                    <span id="process-time" class="metric-value">- ms</span>
                </div>
                <div class="metric">
                    <span class="metric-label">运行模式</span>
                    <span id="run-mode" class="metric-value">{{ mode }}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">分辨率</span>
                    <span id="resolution" class="metric-value">{{ resolution }}</span>
                </div>
            </div>
            
            <div class="card">
                <h3>📝 运行日志</h3>
                <div id="log-container" class="log-container">
                    <div class="log-entry"><span class="log-time">[--:--:--]</span> <span class="log-info">系统启动中...</span></div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        // WebSocket 连接 (添加时间戳防止缓存)
        const timestamp = new Date().getTime();
        const ws = new WebSocket(`ws://${window.location.host}/ws?t=${timestamp}`);
        
        const videoFeed = document.getElementById('video-feed');
        const statusBadge = document.getElementById('status-badge');
        const logContainer = document.getElementById('log-container');
        
        ws.onopen = () => {
            addLog('WebSocket 连接成功', 'info');
            statusBadge.textContent = '已连接';
            statusBadge.className = 'status-badge status-normal';
        };
        
        ws.onclose = () => {
            addLog('WebSocket 连接断开', 'error');
            statusBadge.textContent = '已断开';
            statusBadge.className = 'status-badge status-unknown';
        };
        
        ws.onerror = (error) => {
            addLog('WebSocket 错误: ' + error, 'error');
        };
        
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            // 更新画面
            if (data.image) {
                videoFeed.src = 'data:image/jpeg;base64,' + data.image;
            }
            
            // 更新检测结果
            if (data.result) {
                updateResult(data.result);
            }
        };
        
        function updateResult(result) {
            // 积煤判定
            const coalResult = document.getElementById('coal-result');
            if (result.has_coal === true) {
                coalResult.textContent = '🚨 检测到积煤';
                coalResult.className = 'metric-value danger';
                statusBadge.textContent = '积煤报警';
                statusBadge.className = 'status-badge status-alarm';
            } else if (result.has_coal === false) {
                coalResult.textContent = '✅ 正常';
                coalResult.className = 'metric-value good';
                statusBadge.textContent = '运行正常';
                statusBadge.className = 'status-badge status-normal';
            } else {
                coalResult.textContent = '❓ 需人工确认';
                coalResult.className = 'metric-value warning';
                statusBadge.textContent = '需确认';
                statusBadge.className = 'status-badge status-warning';
            }
            
            // 置信度
            const confidence = document.getElementById('confidence');
            confidence.textContent = result.confidence;
            confidence.className = 'metric-value ' + 
                (result.confidence === 'HIGH' ? 'good' : 
                 result.confidence === 'LOW' ? 'danger' : 'warning');
            
            // 格栅可见率
            const gridRatio = result.grid_visible_ratio * 100;
            document.getElementById('grid-ratio').textContent = gridRatio.toFixed(1) + '%';
            const gridProgress = document.getElementById('grid-progress');
            gridProgress.style.width = gridRatio + '%';
            gridProgress.style.background = gridRatio > 85 ? '#00c853' : gridRatio > 60 ? '#ffc107' : '#ff1744';
            
            // 积煤覆盖率
            const coverage = result.coal_coverage * 100;
            document.getElementById('coal-coverage').textContent = coverage.toFixed(1) + '%';
            const coverageProgress = document.getElementById('coverage-progress');
            coverageProgress.style.width = Math.min(coverage * 5, 100) + '%';  // 放大显示
            coverageProgress.style.background = coverage < 5 ? '#00c853' : coverage < 15 ? '#ffc107' : '#ff1744';
            
            // 性能指标
            document.getElementById('frame-id').textContent = result.frame_id;
            document.getElementById('process-time').textContent = result.process_time_ms.toFixed(1) + ' ms';
        }
        
        function addLog(message, level = 'info') {
            const time = new Date().toLocaleTimeString();
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            entry.innerHTML = `<span class="log-time">[${time}]</span> <span class="log-${level}">${message}</span>`;
            logContainer.appendChild(entry);
            logContainer.scrollTop = logContainer.scrollHeight;
            
            // 只保留最近 50 条
            while (logContainer.children.length > 50) {
                logContainer.removeChild(logContainer.firstChild);
            }
        }
    </script>
</body>
</html>
"""


# 全局状态
class AppState(StreamAppState):
    def __init__(self):
        super().__init__()
        self.detector: Optional[CoalDetector] = None
        self.latest_result: Optional[DetectionResult] = None


state = AppState()


async def startup():
    """应用启动"""
    state.config = Config()
    # 默认开启真实格栅，可通过环境变量 USE_REAL_GRID_IN_DEV 覆盖
    state.config.USE_REAL_GRID_IN_DEV = read_bool_env("USE_REAL_GRID_IN_DEV", default=True)

    apply_mock_source_from_env(
        state.config,
        app_tag="[WebApp]",
        log_when_missing=True,
    )
    apply_sample_resolution(state.config, width=462, height=603)

    state.camera = create_camera(state.config)
    state.detector = CoalDetector(state.config)
    state.is_running = True

    # 显示格栅配置信息
    grid_count = len(state.detector.grid_rois)
    logger.info(f"Web 服务启动完成 - 格栅数量: {grid_count}")
    if grid_count == 125:
        logger.info("✓ 使用GridEditorToolKit精确标注格栅 (125个)")
    else:
        logger.warning(f"⚠ 格栅数量异常: {grid_count}个")


async def shutdown():
    """应用关闭"""
    state.stop_runtime(app_tag="[WebApp]")
    logger.info("Web 服务已关闭")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """主页"""
    config = state.config or Config()
    mode = "开发模式" if config.DEV_MODE else "生产模式"
    resolution = f"{config.frame_width} x {config.frame_height}"
    
    # 替换模板变量
    html = INDEX_HTML.replace("{{ mode }}", mode).replace("{{ resolution }}", resolution)
    return HTMLResponse(content=html)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 实时推流"""
    def _detect_frame(frame, frame_id):
        return state.detector.detect(frame, frame_id)

    def _on_result(result):
        state.latest_result = result

    def _render_frame(frame, result):
        if result.annotated_frame is not None:
            return result.annotated_frame
        return frame

    def _build_response(result, image_base64):
        return {"image": image_base64, "result": result.to_dict()}

    await run_websocket_stream(
        websocket,
        app_tag="[WebApp]",
        state=state,
        detect_frame=_detect_frame,
        on_result=_on_result,
        build_history_entry=None,
        render_frame=_render_frame,
        build_response_data=_build_response,
        jpeg_quality=70,
    )


@app.get("/api/camera/debug")
async def debug_camera():
    """调试相机状态"""
    if not state.camera:
        return {"error": "相机未初始化"}

    info = {
        "camera_type": type(state.camera).__name__,
        "source_dir": str(getattr(state.camera, "source_dir", "N/A")),
        "files_count": len(getattr(state.camera, "files", [])),
        "files": [str(f) for f in getattr(state.camera, "files", [])],
        "current_idx": getattr(state.camera, "idx", "N/A"),
        "config_mock_source_dir": state.config.MOCK_SOURCE_DIR,
    }

    return info

@app.get("/api/status")
async def get_status():
    """获取系统状态"""
    return {
        "is_running": state.is_running,
        "dev_mode": state.config.DEV_MODE if state.config else None,
        "latest_result": state.latest_result.to_dict() if state.latest_result else None
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
