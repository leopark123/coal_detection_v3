#!/usr/bin/env python3
"""
翻车机积煤检测系统 V3.0 - 硬件连接测试工具

功能：
1. 测试 Basler 相机连接
2. 测试 Allen Bradley PLC 连接
3. 验证网络通信
4. 生成连接报告

使用方法：
    python tools/hardware_test.py
"""

import sys
import time
import socket
import subprocess
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from config.config import Config

def test_network_connectivity():
    """测试网络连通性"""
    print("\n🌐 测试网络连通性...")

    test_targets = [
        ("Basler相机", "192.168.1.100"),
        ("Allen Bradley PLC", "192.168.1.200")
    ]

    results = {}

    for name, ip in test_targets:
        try:
            # 使用 ping 测试
            result = subprocess.run(
                ["ping", "-n", "3", ip],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                print(f"  ✅ {name} ({ip}) - 网络连通")
                results[name] = True
            else:
                print(f"  ❌ {name} ({ip}) - 网络不通")
                results[name] = False

        except Exception as e:
            print(f"  ❌ {name} ({ip}) - 测试失败: {e}")
            results[name] = False

    return results

def test_basler_camera():
    """测试 Basler 相机连接"""
    print("\n📷 测试 Basler 相机连接...")

    try:
        from drivers.factory import create_camera

        # 创建生产模式配置
        config = Config()
        config.DEV_MODE = False

        # 创建相机实例
        camera = create_camera(config)

        # 测试连接
        if camera.is_connected:
            print("  ✅ 相机连接成功")

            # 获取相机信息
            info = camera.get_camera_info()
            print(f"    设备型号: {info.get('device_model', 'Unknown')}")
            print(f"    序列号: {info.get('serial_number', 'Unknown')}")
            print(f"    分辨率: {info.get('resolution', 'Unknown')}")

            # 测试采集一帧
            try:
                frame = camera.grab()
                print(f"    ✅ 采集测试成功，图像尺寸: {frame.shape}")

                # 保存测试图像
                import cv2
                test_img_path = "logs/hardware_test_camera.jpg"
                cv2.imwrite(test_img_path, frame)
                print(f"    📁 测试图像已保存: {test_img_path}")

                result = True

            except Exception as e:
                print(f"    ❌ 图像采集失败: {e}")
                result = False

            # 释放相机
            camera.release()

        else:
            print(f"  ❌ 相机连接失败: {camera.last_error}")
            result = False

    except ImportError as e:
        print(f"  ❌ pypylon 驱动未安装: {e}")
        result = False

    except Exception as e:
        print(f"  ❌ 相机测试异常: {e}")
        result = False

    return result

def test_allen_bradley_plc():
    """测试 Allen Bradley PLC 连接"""
    print("\n🔌 测试 Allen Bradley PLC 连接...")

    try:
        from plc.allen_bradley import AllenBradleyPLC

        # 创建生产模式配置
        config = Config()
        config.DEV_MODE = False

        # 创建 PLC 实例
        plc = AllenBradleyPLC(config)

        if plc.is_connected:
            print("  ✅ PLC 连接成功")

            # 获取 PLC 信息
            info = plc.get_plc_info()
            print(f"    PLC IP: {info.get('plc_ip')}")
            print(f"    控制器类型: {info.get('controller_type', 'Unknown')}")
            print(f"    产品名称: {info.get('product_name', 'Unknown')}")

            # 测试写入和读取
            try:
                # 写入测试值
                success = plc.write("Detection.SystemReady", True)
                if success:
                    print("    ✅ 写入测试成功")
                else:
                    print("    ❌ 写入测试失败")

                # 读取测试
                value = plc.read("Detection.SystemReady")
                if value is not None:
                    print(f"    ✅ 读取测试成功，值: {value}")
                else:
                    print("    ❌ 读取测试失败")

                # 心跳测试
                old_heartbeat = plc.heartbeat_value
                plc.update_heartbeat()
                if plc.heartbeat_value != old_heartbeat:
                    print(f"    ✅ 心跳测试成功，值: {plc.heartbeat_value}")
                else:
                    print("    ❌ 心跳测试失败")

                result = success and (value is not None)

            except Exception as e:
                print(f"    ❌ PLC 通信测试失败: {e}")
                result = False

            # 关闭连接
            plc.close()

        else:
            print(f"  ❌ PLC 连接失败: {plc.last_error}")
            result = False

    except ImportError as e:
        print(f"  ❌ pycomm3 驱动未安装: {e}")
        result = False

    except Exception as e:
        print(f"  ❌ PLC 测试异常: {e}")
        result = False

    return result

def generate_report(network_results, camera_result, plc_result):
    """生成测试报告"""
    print("\n📋 硬件连接测试报告")
    print("=" * 50)

    all_passed = True

    # 网络连通性
    print("\n🌐 网络连通性:")
    for device, status in network_results.items():
        status_icon = "✅" if status else "❌"
        print(f"  {status_icon} {device}")
        if not status:
            all_passed = False

    # 相机连接
    camera_icon = "✅" if camera_result else "❌"
    print(f"\n📷 Basler 相机: {camera_icon}")
    if not camera_result:
        all_passed = False

    # PLC 连接
    plc_icon = "✅" if plc_result else "❌"
    print(f"\n🔌 Allen Bradley PLC: {plc_icon}")
    if not plc_result:
        all_passed = False

    # 总结
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 所有硬件连接测试通过！系统可以启动。")
        print("\n下一步: 运行 python main.py 启动检测系统")
    else:
        print("⚠️  部分硬件连接测试失败，请检查:")
        print("  1. 网络线缆连接")
        print("  2. 设备IP地址配置")
        print("  3. 设备电源状态")
        print("  4. 驱动程序安装")

    return all_passed

def main():
    """主测试流程"""
    print("🔧 翻车机积煤检测系统 V3.0 - 硬件连接测试")
    print("=" * 50)

    # 确保日志目录存在
    Path("logs").mkdir(exist_ok=True)

    try:
        # 1. 网络连通性测试
        network_results = test_network_connectivity()

        # 2. 相机连接测试
        camera_result = test_basler_camera()

        # 3. PLC 连接测试
        plc_result = test_allen_bradley_plc()

        # 4. 生成报告
        all_passed = generate_report(network_results, camera_result, plc_result)

        # 5. 返回状态码
        sys.exit(0 if all_passed else 1)

    except KeyboardInterrupt:
        print("\n\n⏹️  测试被用户中断")
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ 测试过程发生异常: {e}")
        logger.exception("Hardware test failed")
        sys.exit(1)

if __name__ == "__main__":
    main()