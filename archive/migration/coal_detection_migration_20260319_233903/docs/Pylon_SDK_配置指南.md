# Basler Pylon SDK 配置指南

## 1. 系统要求

- **操作系统**: Windows 10/11 (64位)
- **内存**: 最小4GB，推荐8GB+
- **网卡**: 千兆以太网卡
- **硬盘空间**: 2GB可用空间

## 2. 下载 Pylon SDK

### 下载地址
https://www.baslerweb.com/en/software/pylon/

### 版本选择
- **推荐版本**: Pylon 7.4.0 或更高版本
- **平台**: Windows x64
- **文件名**: 类似 `Basler_pylon_7.4.0.14900_Windows_x64_setup.exe`

## 3. 安装步骤

### 3.1 运行安装程序
1. 右键安装文件，选择"以管理员身份运行"
2. 选择安装语言（建议选择English）

### 3.2 选择安装组件

**必须安装的组件：**
- ✅ **Pylon Runtime** - 运行时环境
- ✅ **Pylon Viewer** - 相机测试工具
- ✅ **Pylon API** - Python API支持
- ✅ **GigE Vision SDK** - 千兆以太网支持
- ✅ **GenICam Runtime** - 相机通用接口

**可选组件：**
- ⭕ Pylon C++ API - C++开发（我们用Python，可不装）
- ⭕ Documentation - 文档（建议安装）
- ⭕ Sample Programs - 示例程序（建议安装）

### 3.3 安装路径
- 默认安装到：`C:\Program Files\Basler\pylon 7\`
- 建议保持默认路径

### 3.4 网络适配器配置
安装过程中会提示配置网络适配器：
- ✅ **选择工控机的以太网网卡**
- ✅ **启用 Jumbo Frames（9000字节）** - 提高传输效率

## 4. 安装后配置

### 4.1 验证安装
1. 开始菜单找到 "Basler" 文件夹
2. 运行 "Pylon Viewer"
3. 检查是否能正常启动

### 4.2 网络优化配置

#### 网卡高级设置：
1. 右键"此电脑" → 属性 → 设备管理器
2. 展开"网络适配器"
3. 右键以太网网卡 → 属性 → 高级

**关键设置：**
```
巨型数据包(Jumbo Packet): 9014字节
接收缓冲区: 2048
传输缓冲区: 2048
中断节制率: 自适应
Flow Control: Rx & Tx Enabled
```

#### Windows网络设置：
```powershell
# 以管理员身份运行PowerShell

# 禁用网卡电源管理
Get-NetAdapter | Set-NetAdapterAdvancedProperty -DisplayName "Power Saving Mode" -DisplayValue "Disabled"

# 设置接收缓冲区
Get-NetAdapter | Set-NetAdapterAdvancedProperty -DisplayName "Receive Buffers" -DisplayValue "2048"

# 启用巨型帧
Get-NetAdapter | Set-NetAdapterAdvancedProperty -DisplayName "Jumbo Packet" -DisplayValue "9014 Bytes"
```

## 5. Python环境配置

### 5.1 安装pypylon
```bash
pip install pypylon>=3.0.0
```

### 5.2 验证Python集成
创建测试文件 `test_pypylon.py`:

```python
#!/usr/bin/env python3
"""
Pylon SDK Python集成测试
"""
import os
import sys

def test_pypylon_import():
    """测试pypylon导入"""
    try:
        import pypylon
        print(f"✅ pypylon 导入成功，版本: {pypylon.__version__}")
        return True
    except ImportError as e:
        print(f"❌ pypylon 导入失败: {e}")
        return False

def test_pylon_installation():
    """测试Pylon SDK安装"""
    try:
        from pypylon import pylon
        print("✅ Pylon SDK 核心库导入成功")

        # 检查Transport Layer
        tlFactory = pylon.TlFactory.GetInstance()
        transportLayers = tlFactory.EnumerateTls()
        print(f"✅ 发现 {len(transportLayers)} 个传输层")

        for tl in transportLayers:
            print(f"   - {tl.GetFullName()}")

        return True
    except Exception as e:
        print(f"❌ Pylon SDK 测试失败: {e}")
        return False

def test_camera_detection():
    """测试相机检测"""
    try:
        from pypylon import pylon

        tlFactory = pylon.TlFactory.GetInstance()
        devices = tlFactory.EnumerateDevices()

        print(f"✅ 发现 {len(devices)} 台Basler相机")

        if len(devices) == 0:
            print("⚠️  未检测到Basler相机（这是正常的，如果相机还未连接）")
        else:
            for i, device in enumerate(devices):
                print(f"   相机 {i+1}:")
                print(f"     型号: {device.GetModelName()}")
                print(f"     序列号: {device.GetSerialNumber()}")
                if hasattr(device, 'GetIpAddress'):
                    print(f"     IP地址: {device.GetIpAddress()}")

        return True
    except Exception as e:
        print(f"❌ 相机检测失败: {e}")
        return False

def main():
    print("=" * 50)
    print("Basler Pylon SDK 配置验证")
    print("=" * 50)

    # 检查环境变量
    pylon_root = os.environ.get('PYLON_ROOT')
    if pylon_root:
        print(f"✅ PYLON_ROOT: {pylon_root}")
    else:
        print("⚠️  PYLON_ROOT 环境变量未设置（通常是正常的）")

    print()

    # 测试步骤
    tests = [
        ("pypylon 库导入", test_pypylon_import),
        ("Pylon SDK 安装", test_pylon_installation),
        ("相机设备检测", test_camera_detection),
    ]

    results = []
    for test_name, test_func in tests:
        print(f"🧪 {test_name}...")
        result = test_func()
        results.append(result)
        print()

    # 总结
    print("=" * 50)
    if all(results):
        print("🎉 Pylon SDK 配置验证通过！")
        print("✅ 可以开始使用Basler相机了")
    else:
        print("❌ 配置验证失败，请检查安装")
        sys.exit(1)
    print("=" * 50)

if __name__ == "__main__":
    main()
```

运行测试：
```bash
python test_pypylon.py
```

## 6. 相机网络配置

### 6.1 设置相机IP（使用Pylon Viewer）

1. **启动Pylon Viewer**
2. **连接相机**：
   - 在左侧设备列表中找到相机
   - 双击连接
3. **配置网络**：
   - 切换到"网络"标签页
   - 设置IP地址：192.168.1.100
   - 子网掩码：255.255.255.0
   - 网关：192.168.1.1
4. **保存配置**：点击"Write"按钮

### 6.2 相机参数配置

在Pylon Viewer中设置以下参数：

```
# 图像格式
PixelFormat: BayerRG8 或 RGB8Packed
Width: 3072
Height: 2048

# 采集设置
AcquisitionMode: Continuous
TriggerMode: Off
AcquisitionFrameRateEnable: True
AcquisitionFrameRate: 10.0

# 曝光设置
ExposureAuto: Off
ExposureTime: 5000.0 (5ms)

# 增益设置
GainAuto: Off
Gain: 1.0

# 网络设置
GevSCPSPacketSize: 8192
GevSCPD: 1000 (帧间延迟)
```

## 7. 防火墙配置

### 7.1 Windows防火墙设置
```powershell
# 以管理员身份运行
# 允许Pylon Viewer通过防火墙
netsh advfirewall firewall add rule name="Pylon Viewer" dir=in action=allow program="C:\Program Files\Basler\pylon 7\bin\PylonViewerApp.exe"

# 允许Python访问网络
netsh advfirewall firewall add rule name="Python GigE" dir=in action=allow protocol=UDP localport=3956
```

## 8. 故障排查

### 8.1 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| pypylon导入失败 | 环境不匹配 | 重新安装对应版本 |
| 检测不到相机 | 网络连接问题 | 检查网线和IP配置 |
| 图像采集超时 | 网络带宽不足 | 启用巨型帧，调整包大小 |
| 相机连接失败 | IP冲突 | 检查IP地址设置 |

### 8.2 网络诊断工具

**Pylon IP Configurator**：
- 位置：开始菜单 → Basler → Tools
- 功能：自动扫描和配置相机网络

**网络测试命令**：
```bash
# 测试相机连通性
ping 192.168.1.100

# 检查网络配置
ipconfig /all

# 检查路由表
route print
```

## 9. 性能优化

### 9.1 系统优化
- 关闭Windows自动更新
- 设置高性能电源模式
- 禁用病毒扫描实时监控（生产环境）
- 增加虚拟内存大小

### 9.2 网络优化
- 使用专用网卡连接相机
- 启用巨型帧（9000字节）
- 调整网卡缓冲区大小
- 使用千兆交换机

## 10. 完成验证

配置完成后，运行我们的硬件测试工具：
```bash
cd C:\CoalDetection
python tools\hardware_test.py
```

如果显示"✅ 相机连接成功"，则Pylon SDK配置完成！