@echo off
chcp 65001 >nul
setlocal

cd /d %~dp0
set COAL_ENV=DEV
set USE_REAL_GRID_IN_DEV=True
set DEVICE_ID=device-1

if exist "C:\Python314\python.exe" (
    set PY_EXE=C:\Python314\python.exe
) else (
    set PY_EXE=python
)

echo ============================================
echo Coal Detection Web (DEV)
echo URL: http://127.0.0.1:8000
echo Press Ctrl+C to stop
echo ============================================

%PY_EXE% -m uvicorn web.app:app --host 127.0.0.1 --port 8000

pause
