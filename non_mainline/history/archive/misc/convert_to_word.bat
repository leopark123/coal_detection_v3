@echo off
chcp 65001 >nul
echo ==========================================
echo 将Markdown文档转换为Word格式
echo ==========================================
echo.

echo [提示] 确保已安装Pandoc
echo 下载地址: https://pandoc.org/installing.html
echo.

echo [1/2] 转换迁移方案文档...
pandoc "docs\迁移方案详细文档.md" -o "docs\翻车机积煤检测系统V3.0-迁移方案.docx" ^
  --from markdown ^
  --to docx ^
  --toc ^
  --toc-depth=3 ^
  --highlight-style=tango ^
  --reference-doc="docs\word_template.docx"

if %errorlevel%==0 (
    echo ✓ 迁移方案文档转换成功
) else (
    echo ✗ 迁移方案文档转换失败
)

echo [2/2] 转换架构设计文档...
pandoc "docs\系统架构设计文档.md" -o "docs\翻车机积煤检测系统V3.0-架构设计.docx" ^
  --from markdown ^
  --to docx ^
  --toc ^
  --toc-depth=3 ^
  --highlight-style=tango ^
  --reference-doc="docs\word_template.docx"

if %errorlevel%==0 (
    echo ✓ 架构设计文档转换成功
) else (
    echo ✗ 架构设计文档转换失败
)

echo.
echo ==========================================
echo 转换完成！
echo 输出文件：
echo - docs\翻车机积煤检测系统V3.0-迁移方案.docx
echo - docs\翻车机积煤检测系统V3.0-架构设计.docx
echo ==========================================
pause