@echo off
chcp 65001 >nul

:: 检查是否在开发机还是目标机
if exist "coal_detection_deploy" (
    echo 检测到开发环境，启动目标机器网络配置...
    call scripts\target_network_setup.bat
) else (
    echo 检测到目标机器，直接配置网络...
    call target_network_setup.bat
)