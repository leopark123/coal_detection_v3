@echo off
chcp 65001 >nul 2>nul
title SystemMonitor - Coal Detection
cd /d D:\coal_detection_project
echo Starting system monitor (interval=30s)...
echo Press Ctrl+C to stop and see summary.
echo.
python tools/system_monitor.py --interval 30 --output logs/monitor_report.json
pause
