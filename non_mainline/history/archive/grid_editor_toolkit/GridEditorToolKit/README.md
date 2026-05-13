# Grid Editor Toolkit v1.0.0

一个独立的、可移植的网格标定工具，支持任意行列数的精确网格标定。

![Grid Editor Demo](docs/demo.png)

## ✨ 主要特性

- 🎯 **精确标定**: 拖拽顶点实现像素级精确定位
- 🔧 **灵活配置**: 支持任意行列数的网格设置
- 💾 **配置保存**: JSON格式保存，支持重复使用
- 🖱️ **直观交互**: 鼠标拖拽+键盘快捷键操作
- 📱 **跨平台**: Windows/Linux/macOS全平台支持
- 📦 **独立运行**: 无需复杂环境，开箱即用

## 🚀 快速开始

### 方法1: 一键启动 (推荐)

**Windows:**
```bash
双击 run_grid_editor.bat
```

**Linux/macOS:**
```bash
./run_grid_editor.sh
```

### 方法2: 命令行启动

```bash
# 安装依赖
pip install -r requirements.txt

# 启动编辑器
python src/grid_editor.py --image samples/sample_image.png --rows 14 --cols 10
```

## 📋 系统要求

- **Python**: 3.7+
- **操作系统**: Windows 7+, Linux (Ubuntu 18+), macOS 10.15+
- **内存**: 最低 512MB
- **依赖库**: OpenCV, NumPy

## 🎮 使用说明

### 基本操作

| 操作 | 说明 |
|------|------|
| **左键拖拽** | 移动网格顶点，精确定位 |
| **右键点击** | 切换格子有效/无效状态 |
| **S键** | 保存配置到 config/grid_config.json |
| **R键** | 重置网格到初始状态 |
| **Q键 / ESC** | 退出编辑器 |

### 界面说明

- 🔵 **蓝色圆点**: 普通网格顶点
- 🟡 **黄色圆点**: 当前选中的顶点
- 🟢 **绿色圆点**: 有效格子中心
- ❌ **红色叉号**: 无效格子中心
- 🟢 **绿色线条**: 网格线

### 工作流程

1. **启动工具**: 运行启动脚本或命令行
2. **选择图片**: 选择要标定的图片
3. **设置参数**: 输入网格行数和列数
4. **精确标定**: 拖拽顶点调整网格位置
5. **状态切换**: 右键切换无效区域
6. **保存配置**: 按S键保存结果

## 📁 目录结构

```
GridEditorToolKit/
├── src/
│   └── grid_editor.py          # 主程序
├── samples/                    # 示例图片
│   ├── sample_image.png
│   ├── sample_image2.png
│   └── sample_image3.png
├── config/                     # 配置保存目录
│   └── grid_config.json        # 生成的配置文件
├── docs/                       # 文档目录
├── requirements.txt            # Python依赖
├── run_grid_editor.bat         # Windows启动脚本
├── run_grid_editor.sh          # Linux/macOS启动脚本
└── README.md                   # 本文档
```

## ⚙️ 配置文件格式

保存的配置文件 (`config/grid_config.json`) 格式：

```json
{
  "version": "1.0.0",
  "image_path": "samples/sample_image.png",
  "image_size": {
    "width": 1024,
    "height": 768
  },
  "grid_dimensions": {
    "rows": 14,
    "cols": 10
  },
  "grid_vertices": [...],
  "cell_states": [...],
  "valid_cells": 132,
  "total_cells": 140
}
```

## 🔧 高级用法

### 命令行参数

```bash
python src/grid_editor.py [选项]

选项:
  --image PATH          图片文件路径 (必需)
  --rows INT            网格行数 (默认: 14)
  --cols INT            网格列数 (默认: 10)
  --config PATH         配置文件路径 (默认: config/grid_config.json)
  --version             显示版本信息
  --help               显示帮助信息
```

### 批量处理示例

```bash
# 处理多张图片
python src/grid_editor.py --image image1.jpg --rows 10 --cols 8 --config config1.json
python src/grid_editor.py --image image2.jpg --rows 12 --cols 10 --config config2.json
```

## 🐛 故障排除

### 常见问题

**Q: 启动时提示"Python not found"**
A: 请先安装Python 3.7+，下载地址: https://www.python.org/downloads/

**Q: 提示"No module named cv2"**
A: 运行 `pip install opencv-python` 安装OpenCV

**Q: Linux下显示问题**
A: 可能需要安装额外包:
```bash
# Ubuntu/Debian
sudo apt-get install python3-opencv python3-tk libopencv-dev

# CentOS/RHEL
sudo yum install opencv-python3 tkinter
```

**Q: 图片不显示或显示异常**
A: 确认图片格式支持(PNG, JPG, BMP)，路径无中文字符

**Q: 配置文件无法保存**
A: 检查config目录权限，确保有写入权限

### 性能优化

- **大图处理**: 工具会自动缩放显示，原始坐标会自动转换
- **内存使用**: 大图片会消耗更多内存，建议单张图片<50MB
- **响应速度**: 网格顶点过多(>20x20)时可能影响响应速度

## 📞 技术支持

- **版本**: Grid Editor Toolkit v1.0.0
- **Python要求**: 3.7+
- **更新日期**: 2026-01-18

### 反馈问题

遇到问题请提供以下信息：
1. 操作系统和Python版本
2. 错误信息截图
3. 使用的图片和参数
4. config/grid_config.json文件内容(如有)

## 📄 使用许可

本工具为开源项目，遵循MIT许可证。

## 🔄 版本历史

### v1.0.0 (2026-01-18)
- ✨ 首个正式版本发布
- 🎯 支持任意行列数网格标定
- 💾 JSON格式配置保存
- 🖱️ 直观的鼠标交互
- 📱 跨平台兼容性
- 📦 独立工具包，开箱即用

---

**Grid Editor Toolkit** - 让网格标定变得简单高效！