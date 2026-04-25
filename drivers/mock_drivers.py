"""
翻车机积煤检测系统 V3.0 - Mock 驱动

用途：开发阶段模拟真实硬件

特性：
1. MockCamera: 循环播放本地图片，支持故障注入和时间戳水印
2. MockPLC: 打印日志，支持模拟延迟和断连
"""

import cv2
import numpy as np
import time
import random
from pathlib import Path
from loguru import logger


class MockCamera:
    """
    模拟相机
    
    功能：
    1. 循环播放本地图片/视频
    2. 添加时间戳水印（让每帧像素不同，ECC 能正常工作）
    3. 故障注入（模拟掉线）
    4. 添加随机微小抖动（模拟震动）
    """
    
    def __init__(self, config):
        self.config = config
        self.source_dir = Path(config.MOCK_SOURCE_DIR)
        self.width = config.frame_width
        self.height = config.frame_height
        
        # 加载图片列表
        self.files = []
        for ext in ["*.jpg", "*.png", "*.bmp"]:
            self.files.extend(sorted(self.source_dir.glob(f"**/{ext}")))
        
        self.idx = 0
        self.frame_count = 0
        self.is_connected = True
        
        # 故障注入配置
        self.enable_fault = config.MOCK_ENABLE_FAULT_INJECTION
        self.fail_rate = config.MOCK_CAMERA_FAIL_RATE
        
        if self.files:
            logger.info(f"[MockCamera] 加载了 {len(self.files)} 张测试图片")
            logger.info(f"[MockCamera] 源目录: {self.source_dir}")
            for i, file in enumerate(self.files):
                logger.info(f"[MockCamera] 图片{i+1}: {file}")
        else:
            logger.warning(f"[MockCamera] 未找到图片，将使用随机噪声")
            logger.warning(f"[MockCamera] 源目录: {self.source_dir}")
    
    def grab(self) -> np.ndarray:
        """
        获取一帧图像
        
        Returns:
            BGR 图像
            
        Raises:
            ConnectionError: 模拟相机掉线
        """
        self.frame_count += 1
        
        # ═══════════════════════════════════════════════════════════
        # 故障注入：模拟相机掉线
        # ═══════════════════════════════════════════════════════════
        if self.enable_fault and random.random() < self.fail_rate:
            self.is_connected = False
            logger.error("[MockCamera] 模拟故障：相机连接丢失！")
            raise ConnectionError("Camera connection lost (simulated)")
        
        self.is_connected = True
        
        # ═══════════════════════════════════════════════════════════
        # 读取图像
        # ═══════════════════════════════════════════════════════════
        if not self.files:
            # 生成随机噪声图
            frame = np.random.randint(
                0, 255, (self.height, self.width, 3), dtype=np.uint8
            )
        else:
            # 专门检测单张标注图片模式
            if len(self.files) == 1:
                # 只有一张图片，固定读取（不循环索引）
                path = self.files[0]
                frame = cv2.imread(str(path))
                # 不递增索引，始终读取同一张图片
            else:
                # 原有的循环读取逻辑
                path = self.files[self.idx]
                frame = cv2.imread(str(path))
                self.idx = (self.idx + 1) % len(self.files)
            
            if frame is None:
                logger.warning(f"[MockCamera] 无法读取: {path}")
                frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            
            # 调整分辨率
            frame = cv2.resize(frame, (self.width, self.height))
        
        # ═══════════════════════════════════════════════════════════
        # 添加时间戳水印（让每帧像素不同）
        # ═══════════════════════════════════════════════════════════
        frame = self._add_timestamp(frame)
        
        # ═══════════════════════════════════════════════════════════
        # 添加随机微小抖动（模拟翻车机震动）
        # ═══════════════════════════════════════════════════════════
        frame = self._add_jitter(frame)
        
        # ═══════════════════════════════════════════════════════════
        # 添加传感器噪声（模拟相机底噪）- By Gemini
        # ═══════════════════════════════════════════════════════════
        frame = self._add_sensor_noise(frame)
        
        return frame
    
    def _add_timestamp(self, frame: np.ndarray) -> np.ndarray:
        """
        添加时间戳水印
        
        目的：
        1. 让每帧像素不同，ECC 差分算法能正常工作
        2. 方便调试时确认帧的时序
        """
        timestamp = time.strftime("%H:%M:%S") + f".{int(time.time()*1000)%1000:03d}"
        text = f"#{self.frame_count:06d} | {timestamp}"
        
        # 半透明背景
        overlay = frame.copy()
        cv2.rectangle(overlay, (5, 5), (350, 35), (0, 0, 0), -1)
        frame = cv2.addWeighted(overlay, 0.5, frame, 0.5, 0)
        
        # 白色文字
        cv2.putText(
            frame, text, (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2
        )
        
        return frame
    
    def _add_jitter(self, frame: np.ndarray) -> np.ndarray:
        """
        添加随机微小位移（模拟震动）
        
        目的：模拟翻车机工作时的微小抖动
        """
        # 随机位移 ±3 像素
        dx = random.randint(-3, 3)
        dy = random.randint(-3, 3)
        
        if dx == 0 and dy == 0:
            return frame
        
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        frame = cv2.warpAffine(
            frame, M, (self.width, self.height),
            borderMode=cv2.BORDER_REPLICATE
        )
        
        return frame
    
    def _add_sensor_noise(self, frame: np.ndarray) -> np.ndarray:
        """
        添加高斯噪声（模拟相机传感器底噪）
        
        目的：
        1. 模拟真实相机的传感器噪声
        2. 防止算法对像素值过于敏感（阈值设得太死）
        3. 让每帧图像都有微小差异，更接近真实
        
        By Gemini 建议
        """
        # 生成高斯噪声（均值0，标准差5）
        noise = np.random.normal(0, 5, frame.shape).astype(np.int16)
        
        # 叠加噪声并裁剪到有效范围
        noisy_frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        
        return noisy_frame
    
    def reconnect(self) -> bool:
        """模拟重连"""
        logger.info("[MockCamera] 尝试重连...")
        time.sleep(0.5)  # 模拟重连耗时
        self.is_connected = True
        logger.info("[MockCamera] 重连成功")
        return True
    
    def release(self):
        """释放资源"""
        logger.info(f"[MockCamera] 释放，共处理 {self.frame_count} 帧")


class MockPLC:
    """
    模拟 PLC
    
    功能：
    1. 记录写入的点位值
    2. 打印关键信号变化
    3. 故障注入（模拟通信延迟和断连）
    """
    
    def __init__(self, config):
        self.config = config
        self.tags = {}
        self.heartbeat_count = 0
        self.is_connected = True
        self.on_status_change = None  # 与 AllenBradleyPLC 接口一致
        self.write_count = 0
        
        # 故障注入配置
        self.enable_fault = config.MOCK_ENABLE_FAULT_INJECTION
        self.max_delay = config.MOCK_PLC_DELAY_MAX
        
        logger.info("[MockPLC] 初始化完成")
    
    def write(self, tag: str, value) -> bool:
        """
        写入点位
        
        Args:
            tag: 点位名称
            value: 值
            
        Returns:
            是否成功
        """
        self.write_count += 1
        
        # ═══════════════════════════════════════════════════════════
        # 故障注入：模拟通信延迟
        # ═══════════════════════════════════════════════════════════
        if self.enable_fault:
            delay = random.uniform(0.01, self.max_delay)
            if delay > 0.1:
                logger.warning(f"[MockPLC] 通信延迟: {delay*1000:.0f}ms")
            time.sleep(delay)
        
        # 存储值
        old_value = self.tags.get(tag)
        self.tags[tag] = value
        
        # ═══════════════════════════════════════════════════════════
        # 打印关键信号变化
        # ═══════════════════════════════════════════════════════════
        if "Coal" in tag or "Alarm" in tag:
            if old_value != value:
                logger.info(f"[MockPLC] 📡 {tag} = {value}")
        elif "Heartbeat" in tag:
            self.heartbeat_count += 1
            if self.heartbeat_count % 20 == 0:
                logger.debug(f"[MockPLC] 💓 心跳 #{value}")
        elif "Fault" in tag and value != 0:
            logger.warning(f"[MockPLC] ⚠️ 故障码: {tag} = {value}")
        
        return True
    
    def read(self, tag: str):
        """
        读取点位
        
        Args:
            tag: 点位名称
            
        Returns:
            点位值，不存在返回 0
        """
        # 故障注入：模拟读取延迟
        if self.enable_fault:
            time.sleep(random.uniform(0.005, 0.02))
        
        return self.tags.get(tag, 0)
    
    def check_connection(self) -> bool:
        """检查连接状态"""
        return self.is_connected
    
    def set_vision_enable(self, enabled: bool) -> bool:
        """设置视觉采集启用/停用"""
        self.write("Vision_Enable", enabled)
        if not enabled:
            self.write("Vision_CanTip", True)
            self.write("Vision_FaultCode", 0)
            self.write("Vision_ResultValid", True)
        logger.info(f"[MockPLC] Vision_Enable = {enabled}")
        return True

    def close(self):
        """关闭连接"""
        logger.info(f"[MockPLC] 关闭，共写入 {self.write_count} 次")
