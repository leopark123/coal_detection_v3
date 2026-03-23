@echo off
chcp 65001 > nul
echo ==========================================
echo    Stable Grid Editor V3.0
echo ==========================================
echo Mode Options:
echo   [1] GUI Mode - Graphical interface
echo   [2] Quick Mode - 14x10 grid, auto image
echo   [3] Direct Mode - Use default settings
echo.
set /p choice="Select mode [1-3] or Enter for default: "

if "%choice%"=="1" (
    echo Starting GUI mode...
    python tools/stable_grid_editor.py --gui
) else if "%choice%"=="2" (
    echo Starting quick mode...
    python tools/stable_grid_editor.py --auto
) else if "%choice%"=="3" (
    echo Starting direct mode...
    python tools/stable_grid_editor.py --auto
) else (
    echo Starting default mode...
    python tools/stable_grid_editor.py --auto
)

echo.
echo Process completed!
pause