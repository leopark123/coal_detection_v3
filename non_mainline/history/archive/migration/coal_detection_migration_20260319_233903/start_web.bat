@echo off
chcp 65001 >nul
echo ============================================
echo   翻车机积煤检测系统 V3.0 - Web 界面
echo ============================================
echo.

cd /d %~dp0

:: 强制开发模式，避免误走生产链路
set COAL_ENV=DEV
set USE_REAL_GRID_IN_DEV=True
set MOCK_SOURCE_DIR=tests\mock_data
set DEVICE_ID=device-1

:: 选择可用的 Python 解释器
if exist "C:\Python314\python.exe" (
    set PY_EXE=C:\Python314\python.exe
) else (
    set PY_EXE=python
)

:: 检查依赖
%PY_EXE% -m pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo [提示] 正在安装 Web 依赖...
    %PY_EXE% -m pip install fastapi uvicorn python-multipart jinja2
)

:: 检查测试图片目录
if not exist "tests\mock_data" (
    echo [提示] 正在生成测试图片...
    %PY_EXE% tools\generate_test_images.py
)

echo.
echo ============================================
echo   Web 界面地址: http://localhost:8000
echo   按 Ctrl+C 停止
echo ============================================
echo.

%PY_EXE% -m uvicorn web.app:app --reload --host 127.0.0.1 --port 8000

pause
