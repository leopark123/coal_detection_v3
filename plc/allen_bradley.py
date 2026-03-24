"""
翻车机积煤检测系统 V3.0 - Allen Bradley PLC 通信

功能：
1. 连接 Allen Bradley (Rockwell) PLC
2. 读写检测结果到 PLC 点位
3. 心跳监控和故障报告
4. 断线重连机制

目标 PLC 型号：
- CompactLogix 1769-L16ER/B B1B（Ethernet/IP, 192.168.1.19）

依赖：
- pycomm3: pip install pycomm3

点位表（5 个标签，最小化通信量）：
- Vision_CanTip:      BOOL - 可翻转（无积煤=True, 有积煤=False）
- Vision_FaultCode:   DINT - 故障码（0=正常, 1=相机故障, 2=PLC通信, 3=画质问题, 4=低置信度需人工）
- Vision_ResultValid: BOOL - 结果可信（高/中置信度=True, 低置信度=False）
- IPC_Heartbeat:      DINT - 心跳递增值（500ms 周期）
- IPC_Online:         BOOL - 视觉系统在线
"""

import time
import socket
from typing import Optional, Dict, Any
from loguru import logger

try:
    from pycomm3 import LogixDriver
    PYCOMM3_AVAILABLE = True
except ImportError:
    LogixDriver = None
    PYCOMM3_AVAILABLE = False
    logger.warning("pycomm3 未安装，Allen Bradley PLC 功能不可用")


class AllenBradleyPLC:
    """
    Allen Bradley PLC 通信驱动

    使用 pycomm3 库进行 Ethernet/IP 通信
    """

    def __init__(self, config):
        self.config = config
        self.plc_ip = config.PLC_IP
        self.timeout_ms = config.PLC_TIMEOUT_MS
        self.heartbeat_interval = config.PLC_HEARTBEAT_INTERVAL_MS

        # 连接状态
        self.plc = None
        self.is_connected = False
        self.last_error = None

        # 统计信息
        self.write_count = 0
        self.read_count = 0
        self.heartbeat_count = 0
        self.connection_start_time = time.time()

        # 心跳管理
        self.last_heartbeat_time = time.time()
        self.heartbeat_value = 0

        # 检查依赖
        if not PYCOMM3_AVAILABLE:
            logger.error("[AllenBradleyPLC] pycomm3 未安装，请运行: pip install pycomm3")
            raise ImportError("pycomm3 library is required for Allen Bradley PLC communication")

        # 自动连接
        self.connect()

    def connect(self) -> bool:
        """
        连接 PLC

        Returns:
            是否连接成功
        """
        try:
            logger.info(f"[AllenBradleyPLC] 尝试连接: {self.plc_ip}")

            # 创建连接（init_tags 确保 CompactLogix 1769-L16ER 标签发现正确）
            self.plc = LogixDriver(
                self.plc_ip, init_tags=True, init_program_tags=True
            )

            # 测试连接
            result = self.plc.open()

            if result:
                self.is_connected = True
                self.connection_start_time = time.time()
                logger.info(f"[AllenBradleyPLC] 连接成功")

                # 写入系统在线信号
                self.write("IPC_Online", True)

                return True
            else:
                logger.error(f"[AllenBradleyPLC] 连接失败")
                return False

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[AllenBradleyPLC] 连接异常: {error_msg}")
            self.last_error = error_msg
            self.is_connected = False
            return False

    def write(self, tag: str, value: Any) -> bool:
        """
        写入 PLC 点位

        Args:
            tag: 点位名称 (如 "Detection.CoalPresent")
            value: 写入值

        Returns:
            是否写入成功
        """
        if not self.is_connected:
            logger.warning(f"[AllenBradleyPLC] PLC 未连接，无法写入 {tag}")
            return False

        try:
            # 处理字符串值的长度限制
            if isinstance(value, str) and len(value) > 82:
                value = value[:82]  # ControlLogix STRING 最大 82 字符

            # 执行写入
            result = self.plc.write(tag, value)

            if result.error:
                logger.error(f"[AllenBradleyPLC] 写入失败 {tag}: {result.error}")

                # 如果是通信错误，标记断连
                if "timeout" in str(result.error).lower() or "connection" in str(result.error).lower():
                    self.is_connected = False

                return False
            else:
                self.write_count += 1

                # 记录重要信号变化
                if tag == "Vision_CanTip":
                    logger.info(f"[AllenBradleyPLC] {tag} = {value}")
                elif tag == "IPC_Heartbeat":
                    self.heartbeat_count += 1
                    if self.heartbeat_count % 20 == 0:
                        logger.debug(f"[AllenBradleyPLC] 心跳 #{value}")
                elif tag == "Vision_FaultCode" and value != 0:
                    logger.warning(f"[AllenBradleyPLC] 故障码: {value}")

                return True

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[AllenBradleyPLC] 写入异常 {tag}: {error_msg}")
            self.last_error = error_msg

            # 网络错误时标记断连
            if "timeout" in error_msg.lower() or "socket" in error_msg.lower():
                self.is_connected = False

            return False

    def read(self, tag: str) -> Any:
        """
        读取 PLC 点位

        Args:
            tag: 点位名称

        Returns:
            点位值，读取失败返回 None
        """
        if not self.is_connected:
            logger.warning(f"[AllenBradleyPLC] PLC 未连接，无法读取 {tag}")
            return None

        try:
            result = self.plc.read(tag)

            if result.error:
                logger.error(f"[AllenBradleyPLC] 读取失败 {tag}: {result.error}")

                # 通信错误时标记断连
                if "timeout" in str(result.error).lower():
                    self.is_connected = False

                return None
            else:
                self.read_count += 1
                return result.value

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[AllenBradleyPLC] 读取异常 {tag}: {error_msg}")
            self.last_error = error_msg

            if "timeout" in error_msg.lower():
                self.is_connected = False

            return None

    def batch_write(self, tag_values: Dict[str, Any]) -> bool:
        """
        批量写入多个点位

        Args:
            tag_values: 点位-值字典

        Returns:
            是否全部写入成功
        """
        if not self.is_connected:
            logger.warning("[AllenBradleyPLC] PLC 未连接，无法批量写入")
            return False

        try:
            # pycomm3 支持批量写入
            results = self.plc.write(*list(tag_values.items()))

            success_count = 0
            for tag, result in zip(tag_values.keys(), results):
                if result.error:
                    logger.error(f"[AllenBradleyPLC] 批量写入失败 {tag}: {result.error}")
                else:
                    success_count += 1

            self.write_count += success_count

            return success_count == len(tag_values)

        except Exception as e:
            logger.error(f"[AllenBradleyPLC] 批量写入异常: {e}")
            self.last_error = str(e)
            return False

    def update_heartbeat(self):
        """更新心跳信号（500ms 周期）"""
        current_time = time.time()

        # 检查心跳间隔
        if (current_time - self.last_heartbeat_time) * 1000 >= self.heartbeat_interval:
            self.heartbeat_value = (self.heartbeat_value + 1) % 65536
            success = self.write("IPC_Heartbeat", self.heartbeat_value)

            if success:
                self.last_heartbeat_time = current_time

            return success

        return True  # 未到时间，不需要更新

    def send_detection_result(self, coal_present: bool, confidence: str,
                            need_manual: bool, fault_code: int = 0):
        """
        发送检测结果到 PLC（5 个标签，一次批量写入）

        Args:
            coal_present: 是否检测到积煤
            confidence: 置信度等级 ("HIGH", "MEDIUM", "LOW")
            need_manual: 是否需要人工确认
            fault_code: 故障码
        """
        # 可翻转 = 无积煤且不需人工确认（安全连锁核心信号）
        can_tip = (not coal_present) and (not need_manual)
        # 结果可信 = 高或中置信度
        result_valid = confidence in ("HIGH", "MEDIUM")

        tag_values = {
            "Vision_CanTip": can_tip,
            "Vision_FaultCode": fault_code,
            "Vision_ResultValid": result_valid,
        }

        # 先更新心跳
        self.update_heartbeat()

        # 批量写入检测结果
        success = self.batch_write(tag_values)

        if success:
            logger.info(f"[AllenBradleyPLC] 检测结果已发送 - 可翻转:{can_tip}, 故障码:{fault_code}")
        else:
            logger.error("[AllenBradleyPLC] 检测结果发送失败")

    def check_connection(self) -> bool:
        """
        检查连接状态

        Returns:
            是否连接正常
        """
        if not self.is_connected:
            return False

        try:
            # 尝试读取心跳标签来验证连接
            result = self.plc.read("IPC_Heartbeat")

            if result.error:
                logger.warning(f"[AllenBradleyPLC] 连接检查失败: {result.error}")
                self.is_connected = False
                return False
            else:
                return True

        except Exception as e:
            logger.warning(f"[AllenBradleyPLC] 连接检查异常: {e}")
            self.is_connected = False
            return False

    def reconnect(self) -> bool:
        """
        重新连接 PLC

        Returns:
            是否重连成功
        """
        logger.info("[AllenBradleyPLC] 尝试重新连接...")

        # 先关闭现有连接
        self.close()

        # 等待一下
        time.sleep(2.0)

        # 重新连接
        return self.connect()

    def close(self):
        """关闭 PLC 连接"""
        try:
            if self.plc and self.is_connected:
                # 发送系统离线信号
                self.write("IPC_Online", False)

                # 关闭连接
                self.plc.close()

            self.is_connected = False

            # 打印统计信息
            elapsed = time.time() - self.connection_start_time
            logger.info(f"[AllenBradleyPLC] 连接关闭 - 运行时间: {elapsed:.1f}s, "
                      f"写入: {self.write_count}, 读取: {self.read_count}, "
                      f"心跳: {self.heartbeat_count}")

        except Exception as e:
            logger.error(f"[AllenBradleyPLC] 关闭连接时异常: {e}")

    def get_plc_info(self) -> dict:
        """获取 PLC 信息"""
        info = {
            "plc_ip": self.plc_ip,
            "is_connected": self.is_connected,
            "write_count": self.write_count,
            "read_count": self.read_count,
            "heartbeat_count": self.heartbeat_count,
            "heartbeat_value": self.heartbeat_value,
            "last_error": self.last_error,
        }

        if self.plc and self.is_connected:
            try:
                # 获取 PLC 控制器信息
                controller_info = self.plc.get_controller_info()
                if controller_info:
                    info.update({
                        "controller_type": controller_info.get("product_type"),
                        "product_name": controller_info.get("product_name"),
                        "revision": controller_info.get("revision"),
                    })
            except:
                pass  # 忽略获取信息失败的错误

        return info

    def __del__(self):
        """析构函数"""
        self.close()


def test_allen_bradley():
    """测试 Allen Bradley PLC 通信"""
    from config.config import Config

    config = Config()
    config.DEV_MODE = False

    try:
        plc = AllenBradleyPLC(config)

        if plc.is_connected:
            print("PLC 连接成功！")

            # 测试心跳
            for i in range(5):
                plc.update_heartbeat()
                time.sleep(0.5)

            # 测试检测结果发送
            plc.send_detection_result(
                coal_present=False,
                confidence="HIGH",
                need_manual=False,
                fault_code=0
            )

            # 测试读取
            heartbeat = plc.read("IPC_Heartbeat")
            print(f"心跳值: {heartbeat}")

            info = plc.get_plc_info()
            print("PLC 信息:", info)

        else:
            print("PLC 连接失败")

    except Exception as e:
        print(f"测试失败: {e}")

    finally:
        if 'plc' in locals():
            plc.close()


if __name__ == "__main__":
    test_allen_bradley()