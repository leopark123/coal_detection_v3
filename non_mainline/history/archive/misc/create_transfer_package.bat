@echo off
chcp 65001 >nul
echo ============================================
echo   创建工控机传输包
echo ============================================
echo.

:: 创建传输包目录
set PACKAGE_DIR=CoalDetection_Transfer
if exist "%PACKAGE_DIR%" rmdir /s /q "%PACKAGE_DIR%"
mkdir "%PACKAGE_DIR%"

echo [1/7] 复制核心代码...
xcopy /E /I /Q "algo" "%PACKAGE_DIR%\algo\"
xcopy /E /I /Q "config" "%PACKAGE_DIR%\config\"
xcopy /E /I /Q "core" "%PACKAGE_DIR%\core\"
xcopy /E /I /Q "drivers" "%PACKAGE_DIR%\drivers\"
xcopy /E /I /Q "plc" "%PACKAGE_DIR%\plc\"
xcopy /E /I /Q "web" "%PACKAGE_DIR%\web\"
xcopy /E /I /Q "tools" "%PACKAGE_DIR%\tools\"

echo [2/7] 复制主程序文件...
copy "main.py" "%PACKAGE_DIR%\"
copy "requirements.txt" "%PACKAGE_DIR%\"
copy "CLAUDE.md" "%PACKAGE_DIR%\"
copy "README.md" "%PACKAGE_DIR%\"

echo [3/7] 复制配置文档...
xcopy /E /I /Q "docs" "%PACKAGE_DIR%\docs\"

echo [4/7] 创建日志目录...
mkdir "%PACKAGE_DIR%\logs"
mkdir "%PACKAGE_DIR%\logs\images"

echo [5/7] 创建工控机安装脚本...
> "%PACKAGE_DIR%\install_dependencies.bat" (
echo @echo off
echo chcp 65001 ^>nul
echo echo ============================================
echo echo   翻车机积煤检测系统 - 依赖安装
echo echo ============================================
echo echo.
echo.
echo echo [1/5] 检查Python环境...
echo python --version ^>nul 2^>^&1
echo if errorlevel 1 ^(
echo     echo [错误] 未找到Python，请先安装Python 3.10+
echo     echo 下载地址: https://www.python.org/downloads/
echo     pause
echo     exit /b 1
echo ^)
echo python --version
echo.
echo echo [2/5] 升级pip...
echo python -m pip install --upgrade pip
echo.
echo echo [3/5] 安装核心依赖...
echo pip install numpy^>=1.24.0
echo pip install opencv-python^>=4.8.0
echo pip install loguru^>=0.7.0
echo pip install PyYAML^>=6.0
echo.
echo echo [4/5] 安装Web界面依赖...
echo pip install fastapi^>=0.100.0
echo pip install uvicorn^>=0.23.0
echo pip install python-multipart^>=0.0.6
echo pip install jinja2^>=3.1.0
echo.
echo echo [5/5] 安装硬件驱动...
echo pip install pypylon^>=3.0.0
echo pip install pycomm3^>=1.2.0
echo.
echo echo ============================================
echo echo   依赖安装完成！
echo echo.
echo echo   下一步:
echo echo   1. 配置网络 ^(IP: 192.168.1.10^)
echo echo   2. 连接硬件 ^(相机、PLC^)
echo echo   3. 运行测试: python tools\hardware_test.py
echo echo   4. 启动系统: python main.py
echo echo ============================================
echo pause
)

echo [6/7] 创建启动脚本...
> "%PACKAGE_DIR%\start_system.bat" (
echo @echo off
echo chcp 65001 ^>nul
echo echo ============================================
echo echo   翻车机积煤检测系统 V3.0 - 生产启动
echo echo ============================================
echo echo.
echo.
echo :: 设置生产模式
echo set COAL_ENV=PROD
echo.
echo echo [1/3] 检查依赖...
echo python -c "import cv2, numpy, loguru, pypylon, pycomm3" 2^>nul
echo if errorlevel 1 ^(
echo     echo [错误] 依赖检查失败，请先运行 install_dependencies.bat
echo     pause
echo     exit /b 1
echo ^)
echo.
echo echo [2/3] 硬件连接测试...
echo python tools\hardware_test.py
echo if errorlevel 1 ^(
echo     echo [警告] 硬件测试失败，是否继续启动? ^(Y/N^)
echo     set /p continue=
echo     if /i not "%%continue%%"=="Y" exit /b 1
echo ^)
echo.
echo echo [3/3] 启动检测系统...
echo echo Web监控: http://localhost:8000
echo python main.py --config config/config_prod.yaml
echo.
echo pause
)

echo [7/7] 创建传输说明...
> "%PACKAGE_DIR%\传输部署说明.txt" (
echo 翻车机积煤检测系统 V3.0 - 工控机部署说明
echo ================================================
echo.
echo 1. 传输步骤:
echo    - 将整个 CoalDetection_Transfer 文件夹复制到工控机
echo    - 推荐位置: C:\CoalDetection\
echo.
echo 2. 软件环境配置:
echo    a. 安装 Python 3.10+ ^(勾选 Add to PATH^)
echo    b. 安装 Basler Pylon SDK
echo    c. 配置 RSLogix 5000 ^(参考 docs\PLC点位表配置.md^)
echo.
echo 3. 网络配置:
echo    - 工控机IP: 192.168.1.10
echo    - 相机IP: 192.168.1.100
echo    - PLC IP: 192.168.1.200
echo.
echo 4. 安装依赖:
echo    - 运行 install_dependencies.bat
echo.
echo 5. 硬件连接:
echo    - 连接相机网线到工业交换机
echo    - 连接PLC网线到工业交换机
echo    - 连接工控机网线到工业交换机
echo.
echo 6. 测试启动:
echo    - 运行 python tools\hardware_test.py
echo    - 运行 start_system.bat
echo.
echo 7. 监控界面:
echo    - 浏览器访问: http://localhost:8000
echo.
echo ================================================
echo 详细配置参考 docs\ 目录下的文档
)

echo.
echo ============================================
echo   传输包创建完成！
echo ============================================
echo   位置: %cd%\%PACKAGE_DIR%
echo   请将此文件夹复制到工控机进行部署
echo ============================================
pause