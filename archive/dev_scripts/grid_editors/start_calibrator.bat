@echo off
echo === 启动工业级柔性网格标定工具 ===
echo 图片: tests/mock_data/clean/2.png
echo 网格: 13行 x 10列
echo 输出: config/grid_baseline.json
echo.
echo 正在启动...
python tools/flexible_grid_calibrator.py tests/mock_data/clean/2.png --rows 13 --cols 10 --output config/grid_baseline.json
pause