"""
翻车机积煤检测系统 V3.0 - 驱动工厂

根据配置自动选择 Mock 或真实驱动
"""

from loguru import logger


def create_camera(config):
    """
    创建相机实例
    
    Args:
        config: 配置对象
        
    Returns:
        相机实例（MockCamera 或 BaslerCamera）
    """
    if config.DEV_MODE:
        from .mock_drivers import MockCamera
        logger.info("📷 使用 MockCamera（开发模式）")
        return MockCamera(config)
    else:
        # 生产环境：使用 Basler GigE 相机
        try:
            from .basler_camera import BaslerCamera
            logger.info("📷 使用 BaslerCamera（生产模式）")
            return BaslerCamera(config)
        except ImportError:
            logger.error("pypylon 未安装，回退到 MockCamera")
            from .mock_drivers import MockCamera
            return MockCamera(config)


def create_plc(config):
    """
    创建 PLC 通信实例
    
    Args:
        config: 配置对象
        
    Returns:
        PLC 实例（MockPLC 或 AllenBradleyPLC）
    """
    if config.DEV_MODE:
        from .mock_drivers import MockPLC
        logger.info("🔌 使用 MockPLC（开发模式）")
        return MockPLC(config)
    else:
        # 生产环境：使用真实 PLC
        try:
            from plc.allen_bradley import AllenBradleyPLC
            logger.info("🔌 使用 AllenBradleyPLC（生产模式）")
            return AllenBradleyPLC(config)
        except ImportError:
            logger.error("pycomm3 未安装，回退到 MockPLC")
            from .mock_drivers import MockPLC
            return MockPLC(config)


def create_image_saver(config):
    """创建图像保存器"""
    from .mock_drivers import ImageSaver
    return ImageSaver(config)
