@echo off
chcp 65001 >nul
echo ============================================
echo   翻车机积煤检测系统 V3.0 - 快速启动
echo ============================================
echo.

:: 设置开发模式
set COAL_ENV=DEV

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

:: 检查依赖
echo [1/4] 检查依赖...
pip show loguru >nul 2>&1
if errorlevel 1 (
    echo [提示] 正在安装依赖...
    pip install -r requirements.txt
)

:: 检查测试图片
echo [2/4] 检查测试图片...
if not exist "tests\mock_data\clean\clean_01.jpg" (
    echo [提示] 正在生成测试图片...
    python tools\generate_test_images.py
)

:: 初始化目录
echo [3/4] 初始化目录...
if not exist "logs" mkdir logs
if not exist "logs\images" mkdir logs\images

:: 启动
echo [4/4] 启动系统...
echo.
echo ============================================
echo   按 Ctrl+C 停止
echo ============================================
echo.

python main.py --dev

pause
