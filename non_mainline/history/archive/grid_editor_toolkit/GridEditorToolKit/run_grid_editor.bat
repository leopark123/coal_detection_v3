@echo off
echo ==========================================
echo      Grid Editor Toolkit v1.0.0
echo ==========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Please install Python 3.7+ first.
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Check if required packages are installed
echo Checking dependencies...
python -c "import cv2, numpy" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Required packages not found. Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
)

echo [OK] Dependencies verified.
echo.

REM Show available sample images
echo Available sample images:
if exist "samples\sample_image.png" echo   [1] samples\sample_image.png
if exist "samples\sample_image2.png" echo   [2] samples\sample_image2.png
if exist "samples\sample_image3.png" echo   [3] samples\sample_image3.png
echo   [C] Custom image path
echo.

set /p choice="Select image [1-3] or C for custom: "

if /i "%choice%"=="1" (
    set IMAGE_PATH=samples\sample_image.png
) else if /i "%choice%"=="2" (
    set IMAGE_PATH=samples\sample_image2.png
) else if /i "%choice%"=="3" (
    set IMAGE_PATH=samples\sample_image3.png
) else if /i "%choice%"=="c" (
    set /p IMAGE_PATH="Enter image path: "
) else (
    set IMAGE_PATH=samples\sample_image.png
)

REM Get grid dimensions
set /p rows="Grid rows (default 14): "
set /p cols="Grid columns (default 10): "

if "%rows%"=="" set rows=14
if "%cols%"=="" set cols=10

echo.
echo Starting Grid Editor...
echo Image: %IMAGE_PATH%
echo Grid: %rows% rows x %cols% columns
echo.

REM Run the grid editor
python src\grid_editor.py --image "%IMAGE_PATH%" --rows %rows% --cols %cols%

echo.
echo Grid Editor finished.
pause