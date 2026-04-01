@echo off
chcp 65001 >nul
echo ====================================
echo   注册 Windows 计划任务（开机自启）
echo   需要以管理员身份运行
echo ====================================
echo.

:: 删除旧任务（如果存在）
schtasks /Delete /TN "CoalDetectionSystem" /F >nul 2>&1

:: 创建计划任务：开机时启动，最高权限运行
schtasks /Create ^
    /TN "CoalDetectionSystem" ^
    /TR "\"%~dp0start_production.bat\"" ^
    /SC ONSTART ^
    /DELAY 0000:30 ^
    /RL HIGHEST ^
    /F

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [成功] 计划任务已创建: CoalDetectionSystem
    echo 触发条件: 系统启动后 30 秒
    echo 运行方式: 最高权限
    echo.
    echo 查看任务: schtasks /Query /TN "CoalDetectionSystem"
    echo 删除任务: schtasks /Delete /TN "CoalDetectionSystem" /F
) else (
    echo.
    echo [失败] 请以管理员身份运行此脚本
)

echo.
pause
