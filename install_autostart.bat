@echo off
chcp 65001 >nul
echo ====================================
echo   安装开机自启动
echo ====================================
echo.

:: 在 Windows 启动文件夹创建快捷方式
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set TARGET=%~dp0start_production.bat
set SHORTCUT=%STARTUP%\coal_detection.lnk

:: 用 PowerShell 创建快捷方式
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%TARGET%'; $s.WorkingDirectory = '%~dp0'; $s.Description = '翻车机积煤检测系统'; $s.Save()"

if exist "%SHORTCUT%" (
    echo [成功] 已创建开机自启动快捷方式
    echo 位置: %SHORTCUT%
    echo.
    echo 下次开机将自动启动检测系统。
) else (
    echo [失败] 创建快捷方式失败
    echo 请手动将 start_production.bat 的快捷方式放入:
    echo %STARTUP%
)

echo.
pause
