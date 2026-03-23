@echo off
chcp 65001 >nul
echo ============================================
echo   翻车机积煤检测系统 V3.0 - 远程部署准备
echo ============================================
echo.

echo [提示] 此脚本将创建部署包，用于传输到目标工控机
echo.

:: 创建部署目录
set DEPLOY_DIR=coal_detection_deploy
if exist "%DEPLOY_DIR%" rmdir /s /q "%DEPLOY_DIR%"
mkdir "%DEPLOY_DIR%"

echo [1/6] 复制项目核心文件...
:: 复制主要目录
xcopy /E /I /Q "algo" "%DEPLOY_DIR%\algo\"
xcopy /E /I /Q "config" "%DEPLOY_DIR%\config\"
xcopy /E /I /Q "core" "%DEPLOY_DIR%\core\"
xcopy /E /I /Q "drivers" "%DEPLOY_DIR%\drivers\"
xcopy /E /I /Q "plc" "%DEPLOY_DIR%\plc\"
xcopy /E /I /Q "web" "%DEPLOY_DIR%\web\"
xcopy /E /I /Q "tools" "%DEPLOY_DIR%\tools\"
xcopy /E /I /Q "scripts" "%DEPLOY_DIR%\scripts\"

echo [2/6] 复制配置和启动文件...
copy "main.py" "%DEPLOY_DIR%\"
copy "requirements.txt" "%DEPLOY_DIR%\"
copy "pytest.ini" "%DEPLOY_DIR%\"
copy "start_prod.bat" "%DEPLOY_DIR%\"
copy "CLAUDE.md" "%DEPLOY_DIR%\"
copy "README.md" "%DEPLOY_DIR%\"

echo [3/6] 复制测试数据...
if exist "tests\mock_data" (
    xcopy /E /I /Q "tests\mock_data" "%DEPLOY_DIR%\tests\mock_data\"
)

echo [4/6] 创建目标机器安装脚本...
echo @echo off > "%DEPLOY_DIR%\install_on_target.bat"
echo chcp 65001 ^>nul >> "%DEPLOY_DIR%\install_on_target.bat"
echo echo ============================================ >> "%DEPLOY_DIR%\install_on_target.bat"
echo echo   翻车机积煤检测系统 V3.0 - 目标机器安装 >> "%DEPLOY_DIR%\install_on_target.bat"
echo echo ============================================ >> "%DEPLOY_DIR%\install_on_target.bat"
echo echo. >> "%DEPLOY_DIR%\install_on_target.bat"
echo echo [1/4] 检查 Python 环境... >> "%DEPLOY_DIR%\install_on_target.bat"
echo python --version ^>nul 2^>^&1 >> "%DEPLOY_DIR%\install_on_target.bat"
echo if errorlevel 1 ^( >> "%DEPLOY_DIR%\install_on_target.bat"
echo     echo [错误] 未找到 Python，请先安装 Python 3.10+ >> "%DEPLOY_DIR%\install_on_target.bat"
echo     pause >> "%DEPLOY_DIR%\install_on_target.bat"
echo     exit /b 1 >> "%DEPLOY_DIR%\install_on_target.bat"
echo ^) >> "%DEPLOY_DIR%\install_on_target.bat"
echo. >> "%DEPLOY_DIR%\install_on_target.bat"
echo echo [2/4] 安装基础依赖... >> "%DEPLOY_DIR%\install_on_target.bat"
echo pip install -r requirements.txt >> "%DEPLOY_DIR%\install_on_target.bat"
echo. >> "%DEPLOY_DIR%\install_on_target.bat"
echo echo [3/4] 安装硬件驱动... >> "%DEPLOY_DIR%\install_on_target.bat"
echo pip install pypylon pycomm3 >> "%DEPLOY_DIR%\install_on_target.bat"
echo. >> "%DEPLOY_DIR%\install_on_target.bat"
echo echo [4/4] 创建日志目录... >> "%DEPLOY_DIR%\install_on_target.bat"
echo if not exist "logs" mkdir logs >> "%DEPLOY_DIR%\install_on_target.bat"
echo if not exist "logs\images" mkdir logs\images >> "%DEPLOY_DIR%\install_on_target.bat"
echo. >> "%DEPLOY_DIR%\install_on_target.bat"
echo echo ============================================ >> "%DEPLOY_DIR%\install_on_target.bat"
echo echo   安装完成！ >> "%DEPLOY_DIR%\install_on_target.bat"
echo echo. >> "%DEPLOY_DIR%\install_on_target.bat"
echo echo   下一步操作： >> "%DEPLOY_DIR%\install_on_target.bat"
echo echo   1. 运行 scripts\network_setup.bat 配置网络 >> "%DEPLOY_DIR%\install_on_target.bat"
echo echo   2. 运行 python tools\hardware_test.py 测试硬件 >> "%DEPLOY_DIR%\install_on_target.bat"
echo echo   3. 运行 start_prod.bat 启动生产系统 >> "%DEPLOY_DIR%\install_on_target.bat"
echo echo ============================================ >> "%DEPLOY_DIR%\install_on_target.bat"
echo pause >> "%DEPLOY_DIR%\install_on_target.bat"

echo [5/6] 创建快速部署说明...
echo # 翻车机积煤检测系统 V3.0 - 目标机器部署说明 > "%DEPLOY_DIR%\部署说明.md"
echo. >> "%DEPLOY_DIR%\部署说明.md"
echo ## 部署步骤 >> "%DEPLOY_DIR%\部署说明.md"
echo. >> "%DEPLOY_DIR%\部署说明.md"
echo 1. 将整个 coal_detection_deploy 文件夹复制到目标工控机 >> "%DEPLOY_DIR%\部署说明.md"
echo 2. 在目标机器上运行 install_on_target.bat >> "%DEPLOY_DIR%\部署说明.md"
echo 3. 连接硬件（相机、PLC、网线） >> "%DEPLOY_DIR%\部署说明.md"
echo 4. 配置网络： scripts\network_setup.bat >> "%DEPLOY_DIR%\部署说明.md"
echo 5. 硬件测试： python tools\hardware_test.py >> "%DEPLOY_DIR%\部署说明.md"
echo 6. 启动系统： start_prod.bat >> "%DEPLOY_DIR%\部署说明.md"
echo. >> "%DEPLOY_DIR%\部署说明.md"
echo ## 网络配置 >> "%DEPLOY_DIR%\部署说明.md"
echo. >> "%DEPLOY_DIR%\部署说明.md"
echo - 工控机网卡：192.168.1.10 >> "%DEPLOY_DIR%\部署说明.md"
echo - Basler相机：192.168.1.100 >> "%DEPLOY_DIR%\部署说明.md"
echo - Allen Bradley PLC：192.168.1.200 >> "%DEPLOY_DIR%\部署说明.md"
echo. >> "%DEPLOY_DIR%\部署说明.md"
echo ## 监控地址 >> "%DEPLOY_DIR%\部署说明.md"
echo. >> "%DEPLOY_DIR%\部署说明.md"
echo - Web界面：http://localhost:8000 >> "%DEPLOY_DIR%\部署说明.md"

echo [6/6] 打包完成...

:: 获取部署包大小
for /f "tokens=3" %%a in ('dir "%DEPLOY_DIR%" /-c ^| find "个文件"') do set file_count=%%a
for /f "tokens=1" %%b in ('powershell "'{0:N2}' -f ((Get-ChildItem -Recurse %DEPLOY_DIR% | Measure-Object -Property Length -Sum).Sum / 1MB)"') do set size_mb=%%b

echo.
echo ============================================
echo   部署包创建完成！
echo ============================================
echo   位置: %cd%\%DEPLOY_DIR%
echo   文件数量: %file_count%
echo   大小: %size_mb% MB
echo.
echo   接下来步骤：
echo   1. 将 %DEPLOY_DIR% 文件夹复制到目标工控机
echo   2. 在目标机器运行 install_on_target.bat
echo   3. 按照 部署说明.md 进行硬件连接
echo ============================================

:: 可选：打开部署包目录
set /p open_folder=是否打开部署包目录？(Y/N):
if /i "%open_folder%"=="Y" explorer "%DEPLOY_DIR%"

pause