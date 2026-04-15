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

点位表（6 个标签）：
- Vision_CanTip:      BOOL - 可翻转（无积煤=True, 有积煤=False）
- Vision_FaultCode:   DINT - 故障码（0=正常, 1=相机故障, 2=PLC通信, 3=画质问题, 4=低置信度需人工）
- Vision_ResultValid: BOOL - 结果可信（高/中置信度=True, 低置信度=False）
- IPC_Heartbeat:      DINT - 心跳递增值（500ms 周期）
- IPC_Online:         BOOL - 视觉系统在线
- Vision_Enable:      BOOL - 视觉采集启用（True=采集中, False=停用，PLC侧Allow_Tip强制=1）
"""

import time
import threading
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
        self._heartbeat_value_lock = threading.Lock()  # 保护 heartbeat_value 读-改-写

        # PLC 读写锁（pycomm3 不是线程安全的）
        self._io_lock = threading.Lock()
        self._io_lock_timeout = 5.0  # 锁等待超时（秒），防止死锁

        # 状态变化回调（供 state_manager 记录故障事件）
        self.on_status_change: Optional[callable] = None
        self._was_connected: bool = False  # 上次状态（用于边沿检测，避免重复回调）

        # 重连管理
        self._reconnect_lock = threading.Lock()
        self._reconnect_interval = 5.0  # 重连间隔（秒）
        self._max_reconnect_interval = 60.0  # 最大重连间隔
        self._current_reconnect_interval = self._reconnect_interval
        self._consecutive_failures = 0
        self._max_consecutive_failures = 3  # 连续失败次数后标记断连

        # 心跳后台线程
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop_event = threading.Event()

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

            # 用线程包装连接，防止 TCP 长时间挂起（10 秒超时）
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

            def _do_connect():
                plc_obj = LogixDriver(
                    self.plc_ip, init_tags=True, init_program_tags=True
                )
                return plc_obj, plc_obj.open()

            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(_do_connect)
                    self.plc, result = future.result(timeout=10)
            except FutureTimeout:
                logger.error(f"[AllenBradleyPLC] 连接超时(10s): {self.plc_ip}")
                self.last_error = "连接超时"
                self.is_connected = False
                return False

            if result:
                self.is_connected = True
                self._was_connected = True
                self.connection_start_time = time.time()
                self._consecutive_failures = 0
                self._current_reconnect_interval = self._reconnect_interval
                logger.info(f"[AllenBradleyPLC] 连接成功")

                # 写入系统在线信号
                self.write("IPC_Online", True)

                # 启动心跳后台线程
                self._start_heartbeat_thread()

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

            # 执行写入（加锁防并发，带超时防死锁）
            if not self._io_lock.acquire(timeout=self._io_lock_timeout):
                logger.warning(f"[AllenBradleyPLC] 写入 {tag} 获取锁超时，跳过")
                return False
            try:
                result = self.plc.write(tag, value)
            finally:
                self._io_lock.release()

            if result.error:
                logger.error(f"[AllenBradleyPLC] 写入失败 {tag}: {result.error}")

                # 如果是通信错误，标记断连
                if "timeout" in str(result.error).lower() or "connection" in str(result.error).lower():
                    self.is_connected = False
                    self._notify_disconnect(f"写入 {tag} 失败: {result.error}")

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

            # 网络错误时累计失败计数
            if "timeout" in error_msg.lower() or "socket" in error_msg.lower():
                self._consecutive_failures += 1
                if self._consecutive_failures >= self._max_consecutive_failures:
                    self.is_connected = False
                    self._notify_disconnect(f"写入异常累计{self._consecutive_failures}次: {error_msg}")

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
            if not self._io_lock.acquire(timeout=self._io_lock_timeout):
                logger.warning(f"[AllenBradleyPLC] 读取 {tag} 获取锁超时，跳过")
                return None
            try:
                result = self.plc.read(tag)
            finally:
                self._io_lock.release()

            if result.error:
                logger.error(f"[AllenBradleyPLC] 读取失败 {tag}: {result.error}")

                # 通信错误时标记断连
                if "timeout" in str(result.error).lower():
                    self.is_connected = False
                    self._notify_disconnect(f"读取 {tag} 失败: {result.error}")

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
                self._notify_disconnect(f"读取异常: {error_msg}")

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
            # pycomm3 支持批量写入（加锁防并发，带超时）
            if not self._io_lock.acquire(timeout=self._io_lock_timeout):
                logger.warning("[AllenBradleyPLC] 批量写入获取锁超时，跳过")
                return False
            try:
                results = self.plc.write(*list(tag_values.items()))
            finally:
                self._io_lock.release()

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
        """
        [已废弃] 心跳由后台线程 _heartbeat_loop 独立管理。

        保留此方法仅为兼容旧代码（detect_process.py），
        但不再递增心跳值，避免双重递增竞态。
        """
        return True

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
        # 可翻转 = 明确无积煤(False) 且 不需人工确认 且 无故障（安全连锁核心信号）
        # ★ coal_present=None(不确定) 时 can_tip=False（安全优先）
        can_tip = (coal_present is False) and (not need_manual) and (fault_code == 0)
        # 结果可信 = 高或中置信度 且 无故障 且 检测结果明确
        result_valid = (confidence in ("HIGH", "MEDIUM")) and (fault_code == 0) and (coal_present is not None)

        tag_values = {
            "Vision_CanTip": can_tip,
            "Vision_FaultCode": fault_code,
            "Vision_ResultValid": result_valid,
        }

        # 心跳由独立后台线程管理（_heartbeat_loop），这里不再重复递增
        # 避免双重递增导致心跳跳号

        # 批量写入检测结果
        success = self.batch_write(tag_values)

        if success:
            logger.info(
                f"[AllenBradleyPLC] 检测结果已发送 - "
                f"可翻转:{can_tip}, 结果可信:{result_valid}, "
                f"置信度:{confidence}, 故障码:{fault_code}"
            )
        else:
            logger.error("[AllenBradleyPLC] 检测结果发送失败")

    def set_vision_enable(self, enabled: bool) -> bool:
        """
        设置视觉采集启用/停用

        停用时 PLC 梯形图中 Vision_Enable=0 → Allow_Tip 强制=1（允许翻车）
        启用时恢复正常检测逻辑

        Args:
            enabled: True=启用采集, False=停用采集
        """
        success = self.write("Vision_Enable", enabled)
        if success:
            if not enabled:
                # 停用时：强制可翻转 + 清除故障码 + 结果有效
                self.write("Vision_CanTip", True)
                self.write("Vision_FaultCode", 0)
                self.write("Vision_ResultValid", True)
            logger.info(f"[AllenBradleyPLC] Vision_Enable = {enabled}")
        return success

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
            if not self._io_lock.acquire(timeout=self._io_lock_timeout):
                logger.warning("[AllenBradleyPLC] 连接检查获取锁超时")
                return False
            try:
                result = self.plc.read("IPC_Heartbeat")
            finally:
                self._io_lock.release()

            if result.error:
                logger.warning(f"[AllenBradleyPLC] 连接检查失败: {result.error}")
                self.is_connected = False
                self._notify_disconnect(f"连接检查失败: {result.error}")
                return False
            else:
                return True

        except Exception as e:
            logger.warning(f"[AllenBradleyPLC] 连接检查异常: {e}")
            self.is_connected = False
            self._notify_disconnect(f"连接检查异常: {e}")
            return False

    def reconnect(self) -> bool:
        """
        重新连接 PLC（线程安全，带指数退避）

        Returns:
            是否重连成功
        """
        with self._reconnect_lock:
            logger.info(f"[AllenBradleyPLC] 尝试重新连接（间隔 {self._current_reconnect_interval:.0f}s）...")

            # 先停止心跳线程
            self._stop_heartbeat_thread()

            # 先关闭现有连接
            self._close_plc_connection()

            # 等待（指数退避）
            time.sleep(min(self._current_reconnect_interval, 2.0))

            # 重新连接
            success = self.connect()

            if success:
                self._current_reconnect_interval = self._reconnect_interval
                logger.info("[AllenBradleyPLC] 重连成功")
            else:
                # 指数退避
                self._current_reconnect_interval = min(
                    self._current_reconnect_interval * 1.5,
                    self._max_reconnect_interval
                )
                logger.warning(
                    f"[AllenBradleyPLC] 重连失败，下次间隔 {self._current_reconnect_interval:.0f}s"
                )

            return success

    def _start_heartbeat_thread(self):
        """启动心跳后台线程（独立于检测周期）"""
        self._stop_heartbeat_thread()
        self._heartbeat_stop_event.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="plc-heartbeat"
        )
        self._heartbeat_thread.start()
        logger.debug("[AllenBradleyPLC] 心跳线程已启动")

    def _stop_heartbeat_thread(self):
        """停止心跳后台线程"""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_stop_event.set()
            self._heartbeat_thread.join(timeout=3.0)
            self._heartbeat_thread = None

    def _heartbeat_loop(self):
        """
        心跳后台循环

        独立线程保证 500ms 间隔心跳，不受检测周期影响。
        连续失败超过阈值时触发自动重连。
        """
        interval_s = self.heartbeat_interval / 1000.0
        while not self._heartbeat_stop_event.is_set():
            if self.is_connected:
                with self._heartbeat_value_lock:
                    self.heartbeat_value = (self.heartbeat_value + 1) % 65536
                    hb_val = self.heartbeat_value
                try:
                    if not self._io_lock.acquire(timeout=2.0):
                        logger.debug("[AllenBradleyPLC] 心跳获取锁超时，跳过本次")
                        self._heartbeat_stop_event.wait(interval_s)
                        continue
                    try:
                        result = self.plc.write("IPC_Heartbeat", hb_val)
                        # 心跳成功时顺带刷新 IPC_Online=True（同一把锁内）
                        # 防止 PLC 掉电重启后标签被清零而视觉侧不感知
                        if not result.error:
                            try:
                                self.plc.write("IPC_Online", True)
                            except Exception:
                                pass  # 不影响心跳主逻辑
                    finally:
                        self._io_lock.release()
                    if result.error:
                        self._consecutive_failures += 1
                        logger.debug(f"[AllenBradleyPLC] 心跳写入失败: {result.error}")
                    else:
                        self._consecutive_failures = 0
                        self.heartbeat_count += 1
                        self.write_count += 1
                        self.last_heartbeat_time = time.time()
                except Exception as e:
                    self._consecutive_failures += 1
                    logger.debug(f"[AllenBradleyPLC] 心跳异常: {e}")

                # 连续失败 → 标记断连，尝试重连（不调用 reconnect 避免死锁）
                if self._consecutive_failures >= self._max_consecutive_failures:
                    logger.warning(
                        f"[AllenBradleyPLC] 连续 {self._consecutive_failures} 次心跳失败，标记断连"
                    )
                    self.is_connected = False
                    self._consecutive_failures = 0
                    self._notify_disconnect(f"心跳连续{self._max_consecutive_failures}次失败")
                    # 等待后直接重建连接（不能调 reconnect，会死锁 join 自己）
                    self._heartbeat_stop_event.wait(self._current_reconnect_interval)
                    if not self._heartbeat_stop_event.is_set():
                        self._try_reconnect_inline()
                    continue

            else:
                # 断连状态，等待重连间隔后尝试
                self._heartbeat_stop_event.wait(self._current_reconnect_interval)
                if not self._heartbeat_stop_event.is_set():
                    self._try_reconnect_inline()
                continue

            self._heartbeat_stop_event.wait(interval_s)

        logger.debug("[AllenBradleyPLC] 心跳线程已退出")

    def _try_reconnect_inline(self):
        """
        在心跳线程内重连（不停止心跳线程，避免死锁）

        与 reconnect() 的区别：不调用 _stop_heartbeat_thread()
        必须同时持有 _reconnect_lock 和 _io_lock 来替换 self.plc
        """
        with self._reconnect_lock:
            logger.info(f"[AllenBradleyPLC] 心跳线程内重连...")
            # 持有 _io_lock 期间关闭旧连接并替换对象，防止其他线程用旧引用
            if not self._io_lock.acquire(timeout=self._io_lock_timeout):
                logger.warning("[AllenBradleyPLC] 重连获取锁超时，放弃本次重连")
                return
            try:
                self._close_plc_connection()
            finally:
                self._io_lock.release()
            time.sleep(1.0)

            try:
                # 用线程包装连接，避免修改全局 socket.setdefaulttimeout
                # （全局修改会影响相机、WebSocket 等其他网络连接）
                from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

                def _do_connect():
                    plc_obj = LogixDriver(
                        self.plc_ip, init_tags=True, init_program_tags=True
                    )
                    return plc_obj, plc_obj.open()

                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(_do_connect)
                    try:
                        new_plc, result = future.result(timeout=10)
                    except (FutureTimeout, Exception) as e:
                        logger.warning(f"[AllenBradleyPLC] 重连超时(10s): {e}")
                        new_plc = None
                        result = None
                if result:
                    # 在 _io_lock 下替换 plc 引用（带超时）
                    if not self._io_lock.acquire(timeout=self._io_lock_timeout):
                        logger.warning("[AllenBradleyPLC] 替换 PLC 引用获取锁超时")
                        try:
                            new_plc.close()
                        except Exception:
                            pass
                        return
                    try:
                        self.plc = new_plc
                    finally:
                        self._io_lock.release()
                    self.is_connected = True
                    self._consecutive_failures = 0
                    self._current_reconnect_interval = self._reconnect_interval
                    self.write("IPC_Online", True)
                    logger.info("[AllenBradleyPLC] 心跳线程内重连成功")
                    self._notify_connect()  # _notify_connect 内部设 _was_connected=True
                else:
                    self._current_reconnect_interval = min(
                        self._current_reconnect_interval * 1.5,
                        self._max_reconnect_interval
                    )
                    logger.warning(f"[AllenBradleyPLC] 重连失败，下次间隔 {self._current_reconnect_interval:.0f}s")
            except Exception as e:
                logger.error(f"[AllenBradleyPLC] 重连异常: {e}")
                self._current_reconnect_interval = min(
                    self._current_reconnect_interval * 1.5,
                    self._max_reconnect_interval
                )

    def _notify_disconnect(self, reason: str = "通信失败"):
        """通知状态变化（边沿触发，只在 connected→disconnected 时回调一次）"""
        if self._was_connected and not self.is_connected:
            self._was_connected = False
            if self.on_status_change:
                try:
                    self.on_status_change("disconnected", reason)
                except Exception:
                    pass

    def _notify_connect(self):
        """通知重连成功（边沿触发）"""
        if not self._was_connected and self.is_connected:
            self._was_connected = True
            if self.on_status_change:
                try:
                    self.on_status_change("connected", "PLC 重连成功")
                except Exception:
                    pass

    def _close_plc_connection(self):
        """内部：仅关闭 PLC 网络连接，不发送离线信号"""
        try:
            if self.plc:
                self.plc.close()
        except Exception:
            pass
        self.is_connected = False

    def close(self):
        """关闭 PLC 连接"""
        # 先停心跳线程
        self._stop_heartbeat_thread()

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
            except Exception as e:
                logger.debug(f"[AllenBradleyPLC] 获取控制器信息失败: {e}")

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