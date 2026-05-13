# Basler Pylon SDK 配置指南

## 相机信息

| 项目 | 值 |
|------|-----|
| 型号 | Basler acA1600-60gm |
| 接口 | GigE Vision |
| 分辨率 | 1600 x 1200 |
| 像素格式 | Mono8（灰度），将来可切换彩色 |
| 最大帧率 | ~5.5 FPS（GigE 带宽限制） |
| IP 地址 | 192.168.1.12 |
| 帧率节点 | AcquisitionFrameRateAbs（旧版 SFNC） |
| 曝光节点 | ExposureTimeAbs（旧版 SFNC） |

## 1. 系统要求

- **操作系统**: Windows 10/11 (64位)
- **内存**: 最小 4GB，推荐 8GB+
- **网卡**: 千兆以太网卡
- **硬盘空间**: 2GB 可用空间

## 2. 下载安装 Pylon SDK

### 下载地址
https://www.baslerweb.com/en/software/pylon/

### 版本选择
- **推荐版本**: Pylon 7.4.0 或更高版本
- **平台**: Windows x64

### 安装组件

**必须安装：**
- ✅ **Pylon Runtime** - 运行时环境
- ✅ **Pylon Viewer** - 相机测试工具
- ✅ **Pylon API** - Python API 支持
- ✅ **GigE Vision SDK** - 千兆以太网支持
- ✅ **GenICam Runtime** - 相机通用接口

### 网络适配器配置
安装过程中会提示配置网络适配器：
- ✅ 选择连接相机的以太网网卡
- ✅ 启用 Jumbo Frames（如交换机支持）

## 3. 安装 pypylon

```bash
pip install pypylon>=3.0.0
```

## 4. 相机网络配置

### 使用 Pylon Viewer 设置相机 IP

1. 启动 Pylon Viewer
2. 左侧设备列表找到相机
3. 右键 → IP Configuration
4. 设置：
   - IP 地址：**192.168.1.12**
   - 子网掩码：255.255.255.0
5. 点击 "Write" 保存

### 相机参数配置

在 Pylon Viewer 中设置以下参数：

```
# 图像格式
PixelFormat: Mono8
Width: 1600
Height: 1200

# 采集设置
AcquisitionMode: Continuous
TriggerMode: Off
AcquisitionFrameRateAbs: 5.5    # 注意：旧版 SFNC 节点名

# 曝光设置（需根据现场光照调整）
ExposureAuto: Off
ExposureTimeAbs: 10000.0        # 10ms，需补光灯后调整

# 增益设置
GainAuto: Off
GainRaw: 200                    # 需根据实际情况调整

# GigE 网络设置（★ 关键）
GevSCPSPacketSize: 1500         # 数据包大小
GevSCPD: 100                    # 包间延迟（★ 最佳值，太大降帧率，太小丢包）
```

> **注意**：acA1600-60gm 使用旧版 SFNC 节点名（`AcquisitionFrameRateAbs`, `ExposureTimeAbs`），不是新版的 `AcquisitionFrameRate`, `ExposureTime`。

## 5. 网卡优化配置

### 网卡高级设置

设备管理器 → 网络适配器 → 右键以太网网卡 → 属性 → 高级：

```
巨型数据包(Jumbo Packet): 9014字节（如交换机支持）
接收缓冲区: 2048
传输缓冲区: 2048
中断节制率: 自适应
Flow Control: Rx & Tx Enabled
```

## 6. 防火墙配置

```powershell
# 允许 Pylon Viewer
netsh advfirewall firewall add rule name="Pylon Viewer" dir=in action=allow program="C:\Program Files\Basler\pylon 7\bin\PylonViewerApp.exe"

# 允许 GigE Vision 协议（UDP 3956）
netsh advfirewall firewall add rule name="GigE Vision" dir=in action=allow protocol=UDP localport=3956

# 允许 Python
netsh advfirewall firewall add rule name="Python" dir=in action=allow program="C:\Python310\python.exe"
```

## 7. 验证测试

```bash
cd D:\coal_detection_project
python tools/hardware_test.py
```

应显示：
```
相机: acA1600-60gm, IP: 192.168.1.12
分辨率: 1600x1200, 格式: Mono8
采集测试: OK, mean brightness: XX.X
```

## 8. 故障排查

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| pypylon 导入失败 | Python 版本不匹配 | 确认 Python 64位，重装 pypylon |
| 检测不到相机 | 网络/IP 问题 | `ping 192.168.1.12`，检查网线 |
| "controlled by another application" | 上次进程未释放 | 等 30 秒或拔插网线 |
| 图像全黑 (mean<2) | 无补光灯/镜头盖未取 | 安装补光灯 |
| 帧率低于预期 | GevSCPD 设置过大 | 设为 100 |
| 丢包/图像花屏 | 网络带宽不足 | 启用 Jumbo Frame，GevSCPD=100 |

## 9. I/O 线缆（Hirose 6-pin）

相机 I/O 接口引出 5 根线：

| 线色 | 功能 | 当前状态 |
|------|------|----------|
| 白 | Line1 输入（外部触发） | 暂不接，预留硬触发 |
| 绿 | Line1 GND | 暂不接 |
| 黄 | Line2 输出（曝光信号，可触发补光灯） | 暂不接 |
| 蓝 | Line2 GND | 暂不接 |
| 裸线 | 屏蔽接地 | **建议接 PE 地排** |

电源线（Pin1+Pin6）已接通。
