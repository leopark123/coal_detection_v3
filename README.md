# 翻车机积煤检测系统 V3.0

> 基于计算机视觉的工业级积煤检测系统，支持多翻车机多漏斗管理，开发/生产模式无缝切换。

## 特性

- **多机多漏斗架构**：配置驱动，支持 N 台翻车机 × M 个漏斗动态扩展
- **虚实分离**：Mock 驱动支持无硬件开发，DEV/PROD 一键切换
- **高性能**：双缓冲 + 非阻塞采集，单帧检测 < 15ms
- **安全可靠**：三级置信度判定 + 多帧投票 + 人工确认机制
- **实时 Web 监控**：三级页面（总览→翻车机→漏斗），WebSocket 实时推流
- **PLC 联锁**：5 个标签最小化通信，500ms 心跳监控

## 硬件环境

| 设备 | 型号 | 说明 |
|------|------|------|
| 相机 | Basler acA1600-60gm | Mono8 灰度, 1600×1200, GigE |
| PLC | AB 1769-L16ER/B B1B | CompactLogix, Ethernet/IP |
| 工控机 | Windows 10 Pro | Python 3.10+ |
| 网络 | 千兆交换机 | 相机/PLC/工控机互联 |

## 快速开始

### 1. 安装依赖

```powershell
pip install -r requirements.txt

# 生产环境额外依赖
pip install pypylon    # Basler 相机
pip install pycomm3    # AB PLC
pip install websockets # WebSocket 支持
```

### 2. 开发模式运行

```powershell
# 设置开发模式
set COAL_ENV=DEV

# 方式1：主检测程序
python main.py --dev

# 方式2：统一 Web 界面（推荐）
python -m uvicorn web.unified_app:app --host 0.0.0.0 --port 8080

# 浏览器访问 http://localhost:8080
```

### 3. 生产模式运行

```powershell
# 不设置 COAL_ENV 或设为 PROD（默认生产模式）
python main.py --config config/config_prod.yaml

# Web 监控
python -m uvicorn web.unified_app:app --host 0.0.0.0 --port 8080
```

### 4. 硬件测试

```powershell
# 测试相机和 PLC 连接
python tools/hardware_test.py

# 相机+PLC 联调
python tools/integration_test_hw.py --frames 20
```

## 系统架构

```
config/devices.yaml（配置驱动）
    │
    ▼
┌─ 服务器 ──────────────────────────────────────┐
│  StateManager（中央状态管理器）                 │
│  ├── 翻车机 1# (PLC: 192.168.1.19)           │
│  │   ├── 漏斗1 (相机: 192.168.1.12, 125格栅)  │
│  │   ├── 漏斗2 (相机: 192.168.1.13, N格栅)    │
│  │   └── ...                                  │
│  ├── 翻车机 2# (PLC: 192.168.2.19)           │
│  │   └── ...                                  │
│  └── 可动态增减                                │
│                                               │
│  unified_app.py (FastAPI)                     │
│  ├── /           总览页                        │
│  ├── /machine/X  翻车机详情（多路视频网格）     │
│  └── /machine/X/funnel/Y  漏斗详情            │
└───────────────────────────────────────────────┘
```

## 项目结构

```
coal_detection/
├── main.py                    # 主检测程序入口
├── config/
│   ├── config.py              # 配置类（DEV/PROD 模式）
│   ├── config_prod.yaml       # 生产环境配置
│   ├── config_dev.yaml        # 开发环境配置
│   ├── devices.yaml           # 多翻车机拓扑配置
│   └── devices_config.py      # 拓扑配置加载器
│
├── drivers/
│   ├── factory.py             # 驱动工厂（自动选 Mock/真实）
│   ├── basler_camera.py       # Basler GigE 相机驱动
│   └── mock_drivers.py        # Mock 驱动（开发用）
│
├── algo/
│   ├── detector.py            # 主检测算法（ECC+CLAHE+双因素）
│   ├── device_detector.py     # 设备级检测（多格栅聚合）
│   ├── judge.py               # 三级置信度判定
│   └── ...
│
├── plc/
│   └── allen_bradley.py       # AB PLC 通信（5 标签）
│
├── web/
│   ├── unified_app.py         # 统一 Web 应用
│   ├── state_manager.py       # 中央状态管理器
│   ├── common.py              # 共享工具
│   ├── templates/
│   │   ├── overview.html      # 总览页
│   │   ├── machine_detail.html # 翻车机详情页
│   │   └── funnel_detail.html # 漏斗详情页
│   └── static/js/
│       └── ws-reconnect.js    # WebSocket 自动重连
│
├── tools/
│   ├── hardware_test.py       # 硬件连接测试
│   └── integration_test_hw.py # 联调测试
│
├── tests/                     # 测试（98 cases）
└── logs/                      # 日志和报警图像
```

## 多机配置

编辑 `config/devices.yaml` 增删翻车机和漏斗：

```yaml
machines:
  - id: "machine-1"
    name: "1#翻车机"
    plc_ip: "192.168.1.19"
    funnels:
      - id: "funnel-1"
        name: "1#漏斗"
        camera_ip: "192.168.1.12"
        pixel_format: "mono"    # mono=灰度, color=彩色
        grid_count: 125         # 标定后确定

  - id: "machine-2"
    name: "2#翻车机"
    plc_ip: "192.168.2.19"
    funnels:
      - id: "funnel-1"
        camera_ip: "192.168.2.12"
        grid_count: 108
```

## PLC 点位表

| 标签 | 类型 | 说明 |
|------|------|------|
| `Vision_CanTip` | BOOL | 可翻转（无积煤=True，安全连锁核心） |
| `Vision_FaultCode` | DINT | 故障码（0=正常, 3=画质, 4=需人工） |
| `Vision_ResultValid` | BOOL | 结果可信（高/中置信度=True） |
| `IPC_Heartbeat` | DINT | 心跳递增（500ms 周期） |
| `IPC_Online` | BOOL | 视觉系统在线 |

## 开发模式 vs 生产模式

| 特性 | 开发模式 (DEV) | 生产模式 (PROD) |
|------|----------------|-----------------|
| 相机 | MockCamera | BaslerCamera |
| PLC | MockPLC | AllenBradleyPLC |
| 分辨率 | 1024×768 | 1600×1200 |
| 帧率 | 1 FPS | 5.5 FPS |
| ECC 配准 | 禁用 | 启用 |

## 测试

```powershell
# 运行全部测试
pytest tests/ -v

# 当前: 98 passed
```

## 参考文档

- `CLAUDE.md` — 项目技术规范
- `docs/` — 详细设计文档

## License

Proprietary - 内部项目
