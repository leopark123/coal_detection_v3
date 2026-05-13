@echo off
chcp 65001 >nul
echo ============================================
echo   翻车机系统 - 目标工控机网络配置
echo ============================================
echo.

echo [重要] 请确保以管理员身份运行此脚本
echo.

:: 检查管理员权限
net session >nul 2>&1
if errorlevel 1 (
    echo [错误] 需要管理员权限！
    echo 请右键点击此脚本，选择"以管理员身份运行"
    pause
    exit /b 1
)

echo [1/4] 检测网络接口...
:: 列出所有网络接口
echo 可用的网络接口：
netsh interface show interface | find "已连接"
echo.

:: 尝试自动检测主要网络接口
for /f "tokens=4*" %%a in ('netsh interface show interface ^| find "已连接" ^| find "以太网"') do (
    set INTERFACE_NAME=%%b
    goto found_interface
)

for /f "tokens=4*" %%a in ('netsh interface show interface ^| find "已连接"') do (
    set INTERFACE_NAME=%%b
    goto found_interface
)

:found_interface
if not defined INTERFACE_NAME (
    echo [错误] 未找到可用的网络接口
    pause
    exit /b 1
)

echo 检测到网络接口: %INTERFACE_NAME%
echo.

echo [2/4] 配置静态 IP...
echo 正在设置工控机网络配置：
echo   IP地址: 192.168.1.10
echo   子网掩码: 255.255.255.0
echo   网关: 192.168.1.1
echo.

:: 配置静态IP
netsh interface ip set address "%INTERFACE_NAME%" static 192.168.1.10 255.255.255.0 192.168.1.1
if errorlevel 1 (
    echo [错误] IP配置失败，可能的原因：
    echo   1. 网络接口名称不正确
    echo   2. 权限不足
    echo   3. 网络接口被占用
    pause
    exit /b 1
)

echo [3/4] 验证网络配置...
echo 当前网络配置：
ipconfig | find "192.168.1"

echo.
echo [4/4] 测试硬件连通性...

echo 测试相机连接 (192.168.1.100)：
ping -n 3 192.168.1.100
set camera_result=%errorlevel%

echo.
echo 测试PLC连接 (192.168.1.200)：
ping -n 3 192.168.1.200
set plc_result=%errorlevel%

echo.
echo ============================================
echo   网络配置结果
echo ============================================

:: 显示结果
if %camera_result%==0 (
    echo ✅ 相机连通性测试: 通过
) else (
    echo ❌ 相机连通性测试: 失败 - 请检查相机IP和网线连接
)

if %plc_result%==0 (
    echo ✅ PLC连通性测试: 通过
) else (
    echo ❌ PLC连通性测试: 失败 - 请检查PLC IP和网线连接
)

echo.
if %camera_result%==0 if %plc_result%==0 (
    echo 🎉 网络配置完成！所有设备连通。
    echo.
    echo 下一步: 运行硬件测试
    echo   python tools\hardware_test.py
) else (
    echo ⚠️  网络配置完成，但部分设备不通。
    echo.
    echo 请检查：
    echo   1. 设备电源是否开启
    echo   2. 网线连接是否正确
    echo   3. 设备IP地址是否正确配置
    echo   4. 工业交换机是否正常工作
)

echo ============================================
pause