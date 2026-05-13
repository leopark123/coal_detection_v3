# ============================================================
# 翻车机积煤检测系统 V3.0 - 项目初始化脚本
# ============================================================

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  翻车机积煤检测系统 V3.0 - 项目初始化" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# 创建目录结构
$dirs = @(
    "config",
    "core",
    "algo",
    "drivers",
    "plc",
    "web",
    "web/static",
    "web/templates",
    "tools",
    "tests",
    "tests/mock_data",
    "tests/mock_data/clean",
    "tests/mock_data/coal_light",
    "tests/mock_data/coal_heavy",
    "tests/mock_data/edge_cases",
    "logs",
    "logs/images",
    "docs"
)

foreach ($dir in $dirs) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  [+] 创建目录: $dir" -ForegroundColor Green
    }
}

# 创建 __init__.py 文件
$packages = @("core", "algo", "drivers", "plc", "web", "tools", "tests")
foreach ($pkg in $packages) {
    $initFile = "$pkg/__init__.py"
    if (!(Test-Path $initFile)) {
        New-Item -ItemType File -Path $initFile -Force | Out-Null
        Write-Host "  [+] 创建文件: $initFile" -ForegroundColor Green
    }
}

# 创建 .gitignore
$gitignore = @"
# Python
__pycache__/
*.pyc
*.pyo
venv/
.venv/

# Logs
logs/
*.log

# IDE
.vscode/
.idea/

# Data
tests/mock_data/*.jpg
tests/mock_data/*.png
!tests/mock_data/.gitkeep

# OS
.DS_Store
Thumbs.db
"@
Set-Content -Path ".gitignore" -Value $gitignore
Write-Host "  [+] 创建文件: .gitignore" -ForegroundColor Green

# 创建 .claudeignore
$claudeignore = @"
# 排除大文件和无关目录
__pycache__/
*.pyc
logs/
tests/mock_data/
*.jpg
*.png
*.mp4
venv/
.git/
node_modules/
"@
Set-Content -Path ".claudeignore" -Value $claudeignore
Write-Host "  [+] 创建文件: .claudeignore" -ForegroundColor Green

# 创建 requirements.txt
$requirements = @"
# 核心依赖
numpy>=1.24.0
opencv-python>=4.8.0
loguru>=0.7.0
PyYAML>=6.0

# Web 界面
fastapi>=0.100.0
uvicorn>=0.23.0
python-multipart>=0.0.6
jinja2>=3.1.0

# PLC 通信（生产环境）
# pycomm3>=1.2.0

# 测试
pytest>=7.0.0
pytest-cov>=4.0.0
"@
Set-Content -Path "requirements.txt" -Value $requirements
Write-Host "  [+] 创建文件: requirements.txt" -ForegroundColor Green

# 创建 .gitkeep 占位文件
$keepDirs = @(
    "tests/mock_data/clean",
    "tests/mock_data/coal_light", 
    "tests/mock_data/coal_heavy",
    "tests/mock_data/edge_cases",
    "logs/images"
)
foreach ($dir in $keepDirs) {
    $keepFile = "$dir/.gitkeep"
    if (!(Test-Path $keepFile)) {
        New-Item -ItemType File -Path $keepFile -Force | Out-Null
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  初始化完成！" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步操作：" -ForegroundColor Yellow
Write-Host "  1. 安装依赖: pip install -r requirements.txt"
Write-Host "  2. 生成测试图片: python tools/generate_test_images.py"
Write-Host "  3. 启动开发: python main.py --dev"
Write-Host ""
