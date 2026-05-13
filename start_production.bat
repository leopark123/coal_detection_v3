@echo off
chcp 65001 >nul 2>nul
title CoalDetection V3.0

cd /d "%~dp0"
set COAL_ENV=PROD

if not exist logs mkdir logs

:loop
echo [%date% %time%] Starting service...
echo [%date% %time%] Starting >> logs\watchdog.log

python -m uvicorn web.unified_app:app --host 0.0.0.0 --port 8080

echo [%date% %time%] Service stopped (code: %ERRORLEVEL%)
echo [%date% %time%] Stopped (code: %ERRORLEVEL%) >> logs\watchdog.log

echo Restarting in 5 seconds...
ping -n 6 127.0.0.1 >nul

goto loop
