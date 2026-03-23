"""
翻车机积煤检测系统 V3.0 - Basler GigE 相机驱动

功能：
1. 连接 Basler GigE 工业相机
2. 高速图像采集（10 FPS，3072×2048）
3. 断线重连机制
4. 错误处理和故障报告

依赖：
- pypylon >= 3.0.0: pip install pypylon
"""

import numpy as np
import time
from typing import Optional
from loguru import logger

try:
    from pypylon import pylon
    PYPYLON_AVAILABLE = True
except ImportError:
    pylon = None
    PYPYLON_AVAILABLE = False


class BaslerCamera:
    """
    Basler GigE 工业相机驱动

    使用 pypylon SDK 进行 GigE Vision 通信。
    采集策略：GrabStrategy_LatestImageOnly（只取最新帧，符合"最新帧最有价值"原则）

    Usage:
        camera = BaslerCamera(config)
        frame = camera.grab()  # BGR ndarray
    """

    def __init__(self, config):
        if not PYPYLON_AVAILABLE:
            raise ImportError("pypylon 未安装，请运行: pip install pypylon")

        self.config = config
        self.camera_ip = config.CAMERA_IP
        self.timeout_ms = config.CAMERA_TIMEOUT_MS
        self.width = config.frame_width
        self.height = config.frame_height

        # 连接状态
        self.camera: Optional[pylon.InstantCamera] = None
        self.converter: Optional[pylon.ImageFormatConverter] = None
        self.is_connected = False
        self.frame_count = 0
        self.last_error: Optional[str] = None

        # 性能统计
        self.grab_start_time = time.time()
        self.total_frames = 0
        self.dropped_frames = 0

        # 初始化格式转换器（预创建，复用）
        self.converter = pylon.ImageFormatConverter()
        self.converter.OutputPixelFormat = pylon.PixelType_BGR8packed
        self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

        # 自动连接
        self.connect()

    def connect(self) -> bool:
        """
        连接相机

        通过 IP 地址匹配目标 Basler GigE 相机。

        Returns:
            是否连接成功
        """
        try:
            logger.info(f"[BaslerCamera] 尝试连接: {self.camera_ip}")

            tlf = pylon.TlFactory.GetInstance()

            # 枚举 GigE 设备
            devices = tlf.EnumerateDevices()
            if not devices:
                raise ConnectionError("未发现任何 Basler 相机")

            # 按 IP 匹配目标相机
            target_device = None
            for dev_info in devices:
                ip = dev_info.GetIpAddress() if hasattr(dev_info, 'GetIpAddress') else ""
                sn = dev_info.GetSerialNumber()
                logger.debug(f"[BaslerCamera] 发现设备: IP={ip}, SN={sn}")
                if ip == self.camera_ip:
                    target_device = dev_info
                    break

            if target_device is None:
                # 未按 IP 匹配到，使用第一台设备
                logger.warning(
                    f"[BaslerCamera] 未找到 IP={self.camera_ip} 的设备，使用第一台: "
                    f"{devices[0].GetSerialNumber()}"
                )
                target_device = devices[0]

            # 创建 InstantCamera
            self.camera = pylon.InstantCamera(tlf.CreateDevice(target_device))
            self.camera.Open()

            # 配置采集参数
            self._configure_camera()

            # 开始采集（LatestImageOnly：只保留最新帧）
            self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

            self.is_connected = True
            self.grab_start_time = time.time()
            logger.info(
                f"[BaslerCamera] 连接成功 - {target_device.GetModelName()}, "
                f"SN={target_device.GetSerialNumber()}"
            )
            return True

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[BaslerCamera] 连接失败: {error_msg}")
            self.last_error = error_msg
            self.is_connected = False
            return False

    def _configure_camera(self):
        """配置相机采集参数"""
        node_map = self.camera.GetNodeMap()

        # 分辨率
        try:
            node_map.GetNode("Width").SetValue(self.width)
            node_map.GetNode("Height").SetValue(self.height)
        except Exception:
            logger.warning("[BaslerCamera] 无法设置分辨率，使用相机默认值")

        # 帧率
        try:
            node_map.GetNode("AcquisitionFrameRateEnable").SetValue(True)
            node_map.GetNode("AcquisitionFrameRate").SetValue(self.config.TARGET_FPS)
        except Exception:
            logger.warning("[BaslerCamera] 无法设置帧率，使用相机默认值")

        # 曝光（连续模式，关闭自动曝光）
        try:
            node_map.GetNode("ExposureAuto").SetValue("Off")
            node_map.GetNode("ExposureTime").SetValue(5000.0)
        except Exception:
            logger.debug("[BaslerCamera] 曝光参数设置跳过")

        # GigE 网络包大小（提高传输效率）
        try:
            node_map.GetNode("GevSCPSPacketSize").SetValue(8192)
        except Exception:
            logger.debug("[BaslerCamera] 网络包大小设置跳过")

    def grab(self) -> np.ndarray:
        """
        获取一帧 BGR 图像

        Returns:
            BGR 图像, shape=(H, W, 3), dtype=uint8

        Raises:
            ConnectionError: 相机连接丢失或采集超时
        """
        if not self.is_connected or self.camera is None:
            raise ConnectionError("Camera not connected")

        try:
            grab_result = self.camera.RetrieveResult(
                self.timeout_ms, pylon.TimeoutHandling_ThrowException
            )

            if not grab_result.GrabSucceeded():
                error_code = grab_result.GetErrorCode()
                error_desc = grab_result.GetErrorDescription()
                grab_result.Release()
                raise RuntimeError(f"Grab failed: {error_code} - {error_desc}")

            # 转换为 BGR
            image = self.converter.Convert(grab_result)
            frame = image.GetArray().copy()
            grab_result.Release()

            # 确保分辨率正确
            if frame.shape[:2] != (self.height, self.width):
                import cv2
                frame = cv2.resize(frame, (self.width, self.height))

            self.frame_count += 1
            self.total_frames += 1
            return frame

        except pylon.TimeoutException:
            self.dropped_frames += 1
            raise ConnectionError("Camera grab timeout")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[BaslerCamera] 采集失败: {error_msg}")
            self.last_error = error_msg

            if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                self.is_connected = False
                raise ConnectionError(f"Camera grab failed: {error_msg}")

            raise

    def reconnect(self) -> bool:
        """
        断线重连

        Returns:
            是否重连成功
        """
        logger.info("[BaslerCamera] 尝试重新连接...")
        self.release()
        time.sleep(1.0)
        return self.connect()

    def release(self):
        """释放相机资源"""
        try:
            if self.camera is not None:
                if self.camera.IsGrabbing():
                    self.camera.StopGrabbing()
                if self.camera.IsOpen():
                    self.camera.Close()
                self.camera = None

            self.is_connected = False

            elapsed = time.time() - self.grab_start_time
            if elapsed > 0 and self.total_frames > 0:
                avg_fps = self.total_frames / elapsed
                logger.info(
                    f"[BaslerCamera] 释放 - 总帧数: {self.total_frames}, "
                    f"平均帧率: {avg_fps:.1f} FPS, 丢帧: {self.dropped_frames}"
                )

        except Exception as e:
            logger.error(f"[BaslerCamera] 释放资源时错误: {e}")

    def get_camera_info(self) -> dict:
        """获取相机信息"""
        info = {
            "model": "BaslerCamera",
            "ip": self.camera_ip,
            "resolution": f"{self.width}x{self.height}",
            "is_connected": self.is_connected,
            "frame_count": self.frame_count,
            "total_frames": self.total_frames,
            "dropped_frames": self.dropped_frames,
            "last_error": self.last_error,
        }

        if self.camera is not None and self.is_connected:
            try:
                dev_info = self.camera.GetDeviceInfo()
                info["device_model"] = dev_info.GetModelName()
                info["serial_number"] = dev_info.GetSerialNumber()
            except Exception:
                pass

        return info

    def __del__(self):
        """析构函数"""
        self.release()
