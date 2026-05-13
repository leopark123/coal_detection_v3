@echo off
echo ==========================================
echo       稳定通用网格标定工具 V3.0
echo ==========================================
echo 功能: 完整稳定的网格标定系统
echo 特点: 多种启动方式，容错处理完善
echo.
echo 启动模式:
echo   [1] GUI模式 - 图形界面设置参数
echo   [2] 快速模式 - 14行x10列，自动选图
echo   [3] 自定义 - 命令行参数
echo.
set /p choice="请选择启动模式 [1-3]: "

if "%choice%"=="1" (
    echo 启动图形界面模式...
    python tools/stable_grid_editor.py --gui
) else if "%choice%"=="2" (
    echo 启动快速模式 (14行x10列)...
    python tools/stable_grid_editor.py --auto
) else if "%choice%"=="3" (
    set /p img_path="图片路径 (回车使用默认): "
    set /p rows="行数 (回车使用14): "
    set /p cols="列数 (回车使用10): "
    python tools/stable_grid_editor.py --image "%img_path%" --rows %rows% --cols %cols%
) else (
    echo 使用默认快速模式...
    python tools/stable_grid_editor.py --auto
)

echo.
echo 标定完成！
pause