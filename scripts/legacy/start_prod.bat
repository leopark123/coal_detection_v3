@echo off
chcp 65001 >nul
echo ============================================
echo   翻车机积煤检测系统 V3.0 - 生产环境启动
echo ============================================
echo.

:: 确保不在开发模式
set COAL_ENV=PROD

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

:: 检查依赖
echo [1/5] 检查基础依赖...
pip show loguru >nul 2>&1
if errorlevel 1 (
    echo [提示] 正在安装依赖...
    pip install -r requirements.txt
)

:: 检查硬件驱动
echo [2/5] 检查硬件驱动...
pip show pypylon >nul 2>&1
if errorlevel 1 (
    echo [警告] pypylon 未安装，正在安装...
    pip install pypylon
)

pip show pycomm3 >nul 2>&1
if errorlevel 1 (
    echo [警告] pycomm3 未安装，正在安装...
    pip install pycomm3
)

:: 初始化目录
echo [3/5] 初始化目录...
if not exist "logs" mkdir logs
if not exist "logs\images" mkdir logs\images

:: 硬件连接测试
echo [4/5] 硬件连接测试...
python tools\hardware_test.py
if errorlevel 1 (
    echo.
    echo [错误] 硬件连接测试失败，请检查：
    echo   1. 网络连接 (相机、PLC)
    echo   2. 设备IP配置
    echo   3. 设备电源状态
    echo.
    echo 是否强制启动？(Y/N)
    set /p force_start=
    if /i not "%force_start%"=="Y" (
        echo 启动中止
        pause
        exit /b 1
    )
)

:: 启动生产系统
echo [5/5] 启动生产系统...
echo.
echo ============================================
echo   生产模式运行中...
echo   按 Ctrl+C 停止
echo ============================================
echo.
echo [提示] 系统状态监控: http://localhost:8000
echo.

python main.py --config config/config_prod.yaml

echo.
echo ============================================
echo   系统已停止
echo ============================================
pause