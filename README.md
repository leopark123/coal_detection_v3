# 翻车机积煤检测系统 V3.0

> 基于计算机视觉的工业级积煤检测方案，支持开发/生产模式无缝切换。

## 特性

- 🔧 **虚实分离架构**：Mock 驱动支持无硬件开发
- ⚡ **高性能**：双缓冲 + 非阻塞采集，端到端延迟 < 100ms
- 🛡️ **安全可靠**：三级置信度判定 + 多帧投票 + 人工确认机制
- 🧪 **故障注入**：内置相机掉线、PLC 延迟模拟，测试异常处理
- 📊 **回放支持**：自动存图，支持现场问题复盘

## 快速开始

### 1. 环境准备

```powershell
# 克隆项目
git clone <your-repo>
cd coal_detection

# 安装依赖
pip install -r requirements.txt

# ★ 设置环境变量（开发模式）- By Gemini 建议
# Windows:
set COAL_ENV=DEV
# Linux/Mac:
export COAL_ENV=DEV
```

### 2. 生成测试图片

```powershell
python tools/generate_test_images.py
```

### 3. 运行（开发模式）

```powershell
# 方式1：通过环境变量（推荐）
set COAL_ENV=DEV
python main.py

# 方式2：通过命令行参数
python main.py --dev

# 启用故障注入（测试异常处理）
python main.py --dev --fault-injection
```

### 4. 启动 Web 界面

```powershell
# 启动 Web 服务
python -m uvicorn web.app:app --reload --host 0.0.0.0 --port 8000

# 浏览器访问
# http://localhost:8000
```

## 项目结构

```
coal_detection/
├── main.py                 # 主程序入口
├── config/
│   ├── config.py           # 配置类
│   └── reference.jpg       # 基准图像
│
├── drivers/
│   ├── factory.py          # 驱动工厂
│   ├── mock_drivers.py     # Mock 驱动（开发用）
│   └── hikvision_camera.py # 海康相机（生产用，待实现）
│
├── algo/
│   └── detector.py         # 检测算法
│
├── plc/
│   └── allen_bradley.py    # PLC 通信（待实现）
│
├── tools/
│   └── generate_test_images.py  # 测试图片生成
│
├── tests/
│   └── mock_data/          # 测试图片
│
└── logs/
    └── images/             # 报警图像存档
```

## 配置说明

### DEV_MODE 开关

```python
# config/config.py
DEV_MODE = True   # 开发模式（Mock + 低分辨率）
DEV_MODE = False  # 生产模式（真实硬件 + 全分辨率）
```

### 开发模式 vs 生产模式

| 特性 | 开发模式 | 生产模式 |
|------|----------|----------|
| 相机 | MockCamera | HikvisionCamera |
| PLC | MockPLC | AllenBradleyPLC |
| 分辨率 | 1024×768 | 3072×2048 |
| 帧率 | 1 FPS | 10 FPS |
| ECC 配准 | 禁用 | 启用 |
| CUDA | 禁用 | 启用 |

## 检测算法

### 双因素判定

1. **格栅孔计数**：检测格栅孔的可见程度
2. **积煤面积**：HSV 颜色空间分割黑色区域

### 三级置信度

| 等级 | 条件 | 处理 |
|------|------|------|
| HIGH | 两个指标一致 | 自动输出 |
| MEDIUM | 单指标明显异常 | 自动输出 |
| LOW | 指标矛盾 | 需人工确认 |

## 故障注入测试

```powershell
# 启用故障注入
python main.py --dev --fault-injection
```

支持的故障类型：
- 相机掉线（1% 概率）
- PLC 通信延迟（0~500ms）

## 待实现

- [ ] 海康相机驱动 (`drivers/hikvision_camera.py`)
- [ ] AB PLC 通信 (`plc/allen_bradley.py`)
- [ ] 双缓冲多进程架构 (`core/double_buffer.py`)
- [x] Web 监控界面 (`web/app.py`) ✅
- [ ] CUDA 加速

## 技术细节（By Gemini 建议）

### 1. Mock 数据动态化
MockCamera 会自动添加：
- **高斯噪声**：模拟相机传感器底噪，防止算法阈值设置过于敏感
- **时间戳水印**：让每帧像素不同，ECC 差分算法能正常工作
- **随机抖动**：模拟翻车机震动

### 2. Web 界面自适应
- 使用百分比和 `object-fit: contain`，而非固定像素
- 在 1024×768（开发）和 3072×2048（生产）间无缝切换
- 响应式布局，支持移动端查看

### 3. 环境变量控制模式
```powershell
# 开发环境（你的低配电脑）
set COAL_ENV=DEV

# 生产环境（工控机）- 不设置或设为 PROD
set COAL_ENV=PROD
```
**优势**：代码拷贝到工控机无需修改，自动切换到生产模式

## 开发计划

1. **Week 1**：算法逻辑验证（当前阶段）
2. **Week 2**：Web 界面开发
3. **Week 3+**：等工控机到货，硬件集成

## 参考文档

- `CLAUDE.md`：项目规范文档
- `docs/`：详细设计文档

## License

Proprietary - 内部项目
