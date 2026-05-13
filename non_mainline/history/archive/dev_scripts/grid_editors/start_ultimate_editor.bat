@echo off
echo ===================================
echo      终极网格精修工具 V1.0
echo ===================================
echo 功能: 像PS变形工具一样的全手动标定
echo 网格: 13行 x 10列格栅
echo 图片: tests/mock_data/clean/2.png
echo 输出: config/grid_baseline.json
echo.
echo 操作说明:
echo   左键拖拽: 精确移动单个顶点
echo   右键点击: 切换格子有效/无效状态
echo   按键操作: S保存 / R重置 / Q退出
echo.
echo 正在启动...
echo ===================================
python run_editor.py
echo.
echo 编辑完成！
pause