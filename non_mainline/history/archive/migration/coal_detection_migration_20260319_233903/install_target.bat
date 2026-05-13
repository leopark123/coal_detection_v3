@echo off
echo ==========================================
echo 翻车机积煤检测系统 V3.0 - 安装依赖
echo ==========================================
echo.

echo [1/4] 检查Python环境...
python --version
if errorlevel 1 (
    echo 错误: 未找到Python，请先安装Python 3.10+
    pause
    exit /b 1
)

echo [2/4] 升级pip...
python -m pip install --upgrade pip

echo [3/4] 安装依赖...
pip install -r requirements.txt

echo [4/4] 创建目录...
if not exist "logs" mkdir logs
if not exist "logs\images" mkdir logs\images

echo.
echo 安装完成！
echo 开发模式: python main.py --dev
echo 生产模式: python main.py
echo Web界面: http://localhost:8000
pause
