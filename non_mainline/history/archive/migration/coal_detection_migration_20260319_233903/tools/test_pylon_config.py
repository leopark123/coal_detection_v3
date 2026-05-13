#!/usr/bin/env python3
"""
Basler Pylon SDK 配置验证工具

功能：
1. 检查 pypylon 安装
2. 验证 Pylon SDK 集成
3. 测试相机连接
4. 网络配置诊断
5. 性能测试

使用方法：
    python tools/test_pylon_config.py
"""

import os
import sys
import time
import subprocess
import socket
from pathlib import Path

def print_header(title):
    """打印标题"""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def print_section(title):
    """打印小节标题"""
    print(f"\n🔧 {title}")
    print("-" * 40)

def test_pypylon_import():
    """测试 pypylon 导入"""
    print_section("测试 pypylon 库导入")

    try:
        import pypylon
        print(f"✅ pypylon 导入成功")
        print(f"   版本: {pypylon.__version__}")

        # 检查安装路径
        module_path = pypylon.__file__
        print(f"   安装路径: {os.path.dirname(module_path)}")

        return True
    except ImportError as e:
        print(f"❌ pypylon 导入失败: {e}")
        print("   解决方案: pip install pypylon>=3.0.0")
        return False

def test_pylon_sdk():
    """测试 Pylon SDK 核心功能"""
    print_section("测试 Pylon SDK 核心功能")

    try:
        from pypylon import pylon
        print("✅ Pylon SDK 核心库导入成功")

        # 获取版本信息
        try:
            version = pylon.GetPylonVersion()
            print(f"   Pylon 运行时版本: {version}")
        except:
            print("   无法获取版本信息")

        # 检查传输层
        tlFactory = pylon.TlFactory.GetInstance()
        transportLayers = tlFactory.EnumerateTls()

        print(f"✅ 发现 {len(transportLayers)} 个传输层:")
        for tl in transportLayers:
            tl_name = tl.GetFullName()
            print(f"   - {tl_name}")

        return True

    except Exception as e:
        print(f"❌ Pylon SDK 测试失败: {e}")
        print("   解决方案: 重新安装 Basler Pylon SDK")
        return False

def test_camera_detection():
    """测试相机检测"""
    print_section("测试 Basler 相机检测")

    try:
        from pypylon import pylon

        tlFactory = pylon.TlFactory.GetInstance()
        devices = tlFactory.EnumerateDevices()

        print(f"🔍 扫描结果: 发现 {len(devices)} 台 Basler 相机")

        if len(devices) == 0:
            print("⚠️  未检测到 Basler 相机")
            print("   可能原因:")
            print("   1. 相机未连接网线")
            print("   2. 相机未上电")
            print("   3. 网络IP配置错误")
            print("   4. 防火墙阻止连接")
            return False

        # 显示相机详细信息
        for i, device in enumerate(devices):
            print(f"\n📷 相机 {i+1} 详细信息:")
            print(f"   型号: {device.GetModelName()}")
            print(f"   序列号: {device.GetSerialNumber()}")

            # 尝试获取IP地址
            try:
                if hasattr(device, 'GetIpAddress'):
                    ip = device.GetIpAddress()
                    print(f"   IP地址: {ip}")
                elif hasattr(device, 'GetDeviceInfo'):
                    dev_info = device.GetDeviceInfo()
                    if hasattr(dev_info, 'GetIpAddress'):
                        ip = dev_info.GetIpAddress()
                        print(f"   IP地址: {ip}")
            except:
                print("   IP地址: 无法获取")

            # 尝试获取MAC地址
            try:
                if hasattr(device, 'GetMacAddress'):
                    mac = device.GetMacAddress()
                    print(f"   MAC地址: {mac}")
            except:
                print("   MAC地址: 无法获取")

        return True

    except Exception as e:
        print(f"❌ 相机检测失败: {e}")
        return False

def test_camera_connection():
    """测试相机连接和图像采集"""
    print_section("测试相机连接和图像采集")

    try:
        from pypylon import pylon
        import numpy as np

        tlFactory = pylon.TlFactory.GetInstance()
        devices = tlFactory.EnumerateDevices()

        if len(devices) == 0:
            print("❌ 无相机可测试")
            return False

        # 使用第一台相机进行测试
        device = devices[0]
        print(f"🎯 测试相机: {device.GetModelName()} (SN: {device.GetSerialNumber()})")

        # 创建相机实例
        camera = pylon.InstantCamera(tlFactory.CreateDevice(device))

        try:
            # 打开相机
            print("   正在连接相机...")
            camera.Open()
            print("   ✅ 相机连接成功")

            # 配置相机（基本设置）
            node_map = camera.GetNodeMap()

            # 设置像素格式
            try:
                pixel_format = node_map.GetNode("PixelFormat")
                if pixel_format:
                    pixel_format.SetValue("RGB8Packed")
                    print("   ✅ 像素格式设置: RGB8Packed")
            except:
                print("   ⚠️  像素格式设置跳过")

            # 开始采集
            print("   开始图像采集测试...")
            camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

            # 采集测试图像
            grab_result = camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)

            if grab_result.GrabSucceeded():
                image = grab_result.GetArray()
                print(f"   ✅ 图像采集成功!")
                print(f"      图像尺寸: {image.shape}")
                print(f"      数据类型: {image.dtype}")

                # 保存测试图像
                try:
                    import cv2
                    test_img_path = "logs/pylon_test_image.jpg"
                    Path("logs").mkdir(exist_ok=True)
                    cv2.imwrite(test_img_path, image)
                    print(f"      测试图像已保存: {test_img_path}")
                except:
                    print("      图像保存失败（缺少 OpenCV）")

                result = True
            else:
                print(f"   ❌ 图像采集失败: {grab_result.GetErrorCode()}")
                result = False

            grab_result.Release()

        except pylon.TimeoutException:
            print("   ❌ 图像采集超时")
            result = False

        except Exception as e:
            print(f"   ❌ 相机操作失败: {e}")
            result = False

        finally:
            # 清理资源
            try:
                if camera.IsGrabbing():
                    camera.StopGrabbing()
                if camera.IsOpen():
                    camera.Close()
            except:
                pass

        return result

    except Exception as e:
        print(f"❌ 相机连接测试失败: {e}")
        return False

def test_network_config():
    """测试网络配置"""
    print_section("网络配置检查")

    # 检查本机IP配置
    try:
        result = subprocess.run(['ipconfig'], capture_output=True, text=True, timeout=10)
        if '192.168.1.' in result.stdout:
            print("✅ 检测到 192.168.1.x 网段配置")
        else:
            print("⚠️  未检测到 192.168.1.x 网段，请检查IP配置")

        # 查找具体的IP地址
        lines = result.stdout.split('\n')
        for line in lines:
            if 'IPv4' in line and '192.168.1.' in line:
                ip = line.split(':')[-1].strip()
                print(f"   本机IP: {ip}")

    except Exception as e:
        print(f"❌ 网络配置检查失败: {e}")

    # Ping测试目标相机IP
    print("\n🌐 连通性测试:")
    target_ips = ['192.168.1.100', '192.168.1.200']  # 相机和PLC

    for ip in target_ips:
        device_type = "相机" if ip.endswith('100') else "PLC"
        try:
            result = subprocess.run(['ping', '-n', '3', ip],
                                 capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print(f"   ✅ {device_type} ({ip}): 连通")
            else:
                print(f"   ❌ {device_type} ({ip}): 不通")
        except Exception as e:
            print(f"   ❌ {device_type} ({ip}): 测试失败 - {e}")

def check_pylon_installation():
    """检查 Pylon 安装路径"""
    print_section("Pylon 安装路径检查")

    # 常见的 Pylon 安装路径
    pylon_paths = [
        "C:\\Program Files\\Basler\\pylon 7",
        "C:\\Program Files\\Basler\\pylon 6",
        "C:\\Program Files (x86)\\Basler\\pylon 7",
        "C:\\Program Files (x86)\\Basler\\pylon 6"
    ]

    found_installation = False

    for path in pylon_paths:
        if os.path.exists(path):
            print(f"✅ 发现 Pylon 安装: {path}")

            # 检查重要文件
            viewer_path = os.path.join(path, "bin", "PylonViewerApp.exe")
            if os.path.exists(viewer_path):
                print(f"   ✅ Pylon Viewer: {viewer_path}")

            found_installation = True
            break

    if not found_installation:
        print("❌ 未找到 Pylon 安装")
        print("   请从以下地址下载安装 Pylon SDK:")
        print("   https://www.baslerweb.com/en/software/pylon/")

    return found_installation

def generate_report(results):
    """生成测试报告"""
    print_header("Pylon SDK 配置验证报告")

    test_items = [
        ("pypylon 库导入", results[0]),
        ("Pylon SDK 核心功能", results[1]),
        ("相机检测", results[2]),
        ("相机连接和采集", results[3]),
        ("Pylon 安装检查", results[4])
    ]

    print("\n📋 测试结果总结:")
    all_passed = True

    for test_name, result in test_items:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {test_name}: {status}")
        if not result:
            all_passed = False

    print("\n" + "="*60)

    if all_passed:
        print("🎉 Pylon SDK 配置验证完全通过！")
        print("✅ 系统已准备好使用 Basler 相机")
        print("\n下一步:")
        print("   1. 运行完整硬件测试: python tools/hardware_test.py")
        print("   2. 启动检测系统: python main.py")
    else:
        print("❌ 部分测试失败，请按照以上提示解决问题")
        print("\n常见解决方案:")
        print("   1. 重新安装 Basler Pylon SDK")
        print("   2. 运行: pip install pypylon")
        print("   3. 检查网络连接和IP配置")
        print("   4. 确保相机已连接并上电")

    print("="*60)

    return all_passed

def main():
    """主测试流程"""
    print_header("Basler Pylon SDK 配置验证工具")
    print("此工具将验证 Pylon SDK 的完整配置状态")

    # 确保日志目录存在
    Path("logs").mkdir(exist_ok=True)

    try:
        # 执行所有测试
        results = []

        # 测试1: pypylon 导入
        results.append(test_pypylon_import())

        # 测试2: Pylon SDK 核心功能
        results.append(test_pylon_sdk())

        # 测试3: 相机检测
        results.append(test_camera_detection())

        # 测试4: 相机连接和采集（只有检测到相机才执行）
        if results[2]:  # 如果检测到相机
            results.append(test_camera_connection())
        else:
            results.append(False)

        # 测试5: 安装路径检查
        results.append(check_pylon_installation())

        # 网络配置检查（不影响总体结果）
        test_network_config()

        # 生成报告
        success = generate_report(results)

        return 0 if success else 1

    except KeyboardInterrupt:
        print("\n\n⏹️  测试被用户中断")
        return 1

    except Exception as e:
        print(f"\n❌ 测试过程发生异常: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())