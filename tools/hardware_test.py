"""
翻车机积煤检测系统 V3.0 - 硬件连接测试

测试项目：
1. 网络连通性（ping）
2. Basler 相机连接 + 采集测试
3. AB PLC 连接 + 读写测试

使用方法：
    python tools/hardware_test.py
    python tools/hardware_test.py --config config/config_prod.yaml
"""

import sys
import time
import socket
import argparse
from pathlib import Path

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config


def print_header(title: str):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(name: str, ok: bool, detail: str = ""):
    icon = "[PASS]" if ok else "[FAIL]"
    msg = f"  {icon} {name}"
    if detail:
        msg += f" - {detail}"
    print(msg)


def test_ping(ip: str, port: int = None, timeout: float = 3.0) -> bool:
    """TCP 连通性测试（比 ICMP ping 更可靠）"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        # GigE Vision 默认端口 3956，Ethernet/IP 默认端口 44818
        test_port = port or 3956
        result = sock.connect_ex((ip, test_port))
        sock.close()
        return result == 0
    except Exception:
        return False


def test_icmp_ping(ip: str) -> bool:
    """ICMP ping 测试"""
    import subprocess
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", "2000", ip],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def test_camera(config: Config) -> bool:
    """测试 Basler 相机连接和采集"""
    print_header("Basler 相机测试")
    print(f"  目标: {config.CAMERA_IP}")
    print(f"  像素格式: {config.CAMERA_PIXEL_FORMAT}")
    print(f"  分辨率: {config.FRAME_WIDTH}x{config.FRAME_HEIGHT}")
    print()

    all_ok = True

    # 1. 网络连通性
    ping_ok = test_icmp_ping(config.CAMERA_IP)
    print_result("ICMP Ping", ping_ok, config.CAMERA_IP)
    if not ping_ok:
        print("  [INFO] ICMP 不通不一定代表相机故障（可能禁用了 ICMP）")

    # 2. GigE Vision 端口
    gige_ok = test_ping(config.CAMERA_IP, port=3956)
    print_result("GigE Vision 端口 (3956)", gige_ok)
    all_ok = all_ok and (ping_ok or gige_ok)

    if not ping_ok and not gige_ok:
        print("  [ERROR] 网络不通，跳过驱动测试")
        return False

    # 3. pypylon SDK
    try:
        from pypylon import pylon
        print_result("pypylon SDK", True, pylon.__version__ if hasattr(pylon, '__version__') else "已安装")
    except ImportError:
        print_result("pypylon SDK", False, "未安装，请运行: pip install pypylon")
        return False

    # 4. 枚举设备
    try:
        tlf = pylon.TlFactory.GetInstance()
        devices = tlf.EnumerateDevices()
        print_result("设备枚举", len(devices) > 0, f"发现 {len(devices)} 台设备")

        if not devices:
            print("  [ERROR] 未发现任何 Basler 相机")
            return False

        # 列出所有设备
        target_found = False
        for i, dev in enumerate(devices):
            ip = dev.GetIpAddress() if hasattr(dev, 'GetIpAddress') else "N/A"
            model = dev.GetModelName()
            sn = dev.GetSerialNumber()
            marker = " <-- 目标" if ip == config.CAMERA_IP else ""
            print(f"    设备[{i}]: {model}, IP={ip}, SN={sn}{marker}")
            if ip == config.CAMERA_IP:
                target_found = True

        print_result("目标相机匹配", target_found, f"IP={config.CAMERA_IP}")
        if not target_found:
            print(f"  [WARN] 未找到 IP={config.CAMERA_IP} 的设备，将使用第一台")

    except Exception as e:
        print_result("设备枚举", False, str(e))
        return False

    # 5. 连接 + 采集测试
    try:
        from drivers.basler_camera import BaslerCamera
        camera = BaslerCamera(config)
        print_result("相机连接", camera.is_connected)

        if camera.is_connected:
            # 采集 3 帧测试
            frames_ok = 0
            for i in range(3):
                try:
                    frame = camera.grab()
                    if frame is not None and frame.shape[:2] == (config.frame_height, config.frame_width):
                        frames_ok += 1
                except Exception as e:
                    print(f"    帧[{i}] 采集失败: {e}")

            print_result("图像采集", frames_ok == 3, f"{frames_ok}/3 帧成功, shape={frame.shape}")

            # 获取相机信息
            info = camera.get_camera_info()
            if info.get("device_model"):
                print(f"    型号: {info['device_model']}")
            if info.get("serial_number"):
                print(f"    序列号: {info['serial_number']}")

            camera.release()
            all_ok = all_ok and (frames_ok == 3)
        else:
            all_ok = False

    except ImportError as e:
        print_result("相机驱动", False, str(e))
        all_ok = False
    except Exception as e:
        print_result("相机连接", False, str(e))
        all_ok = False

    return all_ok


def test_plc(config: Config) -> bool:
    """测试 AB PLC 连接和读写"""
    print_header("AB PLC 测试")
    print(f"  目标: {config.PLC_IP}")
    print(f"  型号: CompactLogix 1769-L16ER/B B1B")
    print()

    all_ok = True

    # 1. 网络连通性
    ping_ok = test_icmp_ping(config.PLC_IP)
    print_result("ICMP Ping", ping_ok, config.PLC_IP)

    # 2. Ethernet/IP 端口 (44818)
    eip_ok = test_ping(config.PLC_IP, port=44818)
    print_result("Ethernet/IP 端口 (44818)", eip_ok)
    all_ok = all_ok and (ping_ok or eip_ok)

    if not ping_ok and not eip_ok:
        print("  [ERROR] 网络不通，跳过驱动测试")
        return False

    # 3. pycomm3 SDK
    try:
        from pycomm3 import LogixDriver
        import pycomm3
        version = getattr(pycomm3, '__version__', '已安装')
        print_result("pycomm3 SDK", True, version)
    except ImportError:
        print_result("pycomm3 SDK", False, "未安装，请运行: pip install pycomm3")
        return False

    # 4. PLC 连接
    plc = None
    try:
        plc = LogixDriver(config.PLC_IP, init_tags=True, init_program_tags=True)
        plc.open()
        print_result("PLC 连接", True)

        # 获取控制器信息
        try:
            info = plc.info
            if info:
                print(f"    产品名称: {info.get('product_name', 'N/A')}")
                print(f"    产品类型: {info.get('product_type', 'N/A')}")
                print(f"    固件版本: {info.get('revision', {}).get('major', '?')}.{info.get('revision', {}).get('minor', '?')}")
                print(f"    序列号: {info.get('serial', 'N/A')}")
        except Exception:
            pass

    except Exception as e:
        print_result("PLC 连接", False, str(e))
        return False

    # 5. 读写测试 - 心跳点位
    try:
        result = plc.read("IPC_Heartbeat")
        if result.error:
            print_result("读取心跳点位", False, str(result.error))
            print("  [INFO] 点位可能未在 PLC 程序中定义，请检查 PLC 程序")
            all_ok = False
        else:
            print_result("读取心跳点位", True, f"当前值={result.value}")

            # 写入测试值
            test_val = (int(result.value or 0) + 1) % 65536
            write_result = plc.write("IPC_Heartbeat", test_val)
            if write_result.error:
                print_result("写入心跳点位", False, str(write_result.error))
                all_ok = False
            else:
                verify = plc.read("IPC_Heartbeat")
                write_ok = not verify.error and verify.value == test_val
                print_result("写入心跳点位", write_ok, f"写入={test_val}, 回读={verify.value}")
                all_ok = all_ok and write_ok

    except Exception as e:
        print_result("点位读写", False, str(e))
        all_ok = False

    # 6. 检查所有必需点位
    required_tags = [
        "Vision_CanTip",
        "Vision_FaultCode",
        "Vision_ResultValid",
        "IPC_Heartbeat",
        "IPC_Online",
    ]

    print()
    print("  点位表检查:")
    tags_ok = 0
    for tag in required_tags:
        try:
            result = plc.read(tag)
            ok = not result.error
            print_result(f"  {tag}", ok, f"值={result.value}" if ok else str(result.error))
            if ok:
                tags_ok += 1
        except Exception as e:
            print_result(f"  {tag}", False, str(e))

    print(f"\n  点位可用: {tags_ok}/{len(required_tags)}")
    all_ok = all_ok and (tags_ok == len(required_tags))

    # 关闭连接
    if plc:
        try:
            plc.close()
        except Exception:
            pass

    return all_ok


def test_network_overview(config: Config):
    """网络概览"""
    print_header("网络概览")
    print(f"  本机 IP: 192.168.1.10")
    print(f"  相机 IP: {config.CAMERA_IP}")
    print(f"  PLC  IP: {config.PLC_IP}")


def main():
    parser = argparse.ArgumentParser(description="硬件连接测试")
    parser.add_argument("--config", type=str, default=None, help="配置文件路径")
    parser.add_argument("--camera-only", action="store_true", help="只测试相机")
    parser.add_argument("--plc-only", action="store_true", help="只测试 PLC")
    args = parser.parse_args()

    # 加载配置（强制生产模式）
    if args.config:
        config = Config.from_yaml(args.config)
    else:
        config = Config()
    config.DEV_MODE = False

    print()
    print("*" * 60)
    print("  翻车机积煤检测系统 V3.0 - 硬件连接测试")
    print("*" * 60)

    test_network_overview(config)

    results = {}

    if not args.plc_only:
        results["camera"] = test_camera(config)

    if not args.camera_only:
        results["plc"] = test_plc(config)

    # 汇总
    print_header("测试汇总")
    all_passed = True
    for name, ok in results.items():
        label = {"camera": "Basler 相机", "plc": "AB PLC"}[name]
        print_result(label, ok)
        if not ok:
            all_passed = False

    print()
    if all_passed:
        print("  >>> 全部通过，硬件就绪 <<<")
    else:
        print("  >>> 存在故障项，请排查后重试 <<<")
    print()

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
