#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
启动设备1检测系统

设备1: 125个格栅口的完整检测
"""

import os
import sys
import uvicorn
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

def setup_device1_environment(
    images_dir: str = "tests/sample_only",
    device_id: str = "device-1",
    use_real_grid: bool = True,
):
    """设置设备1检测环境"""
    print("=" * 60)
    print("  设备1检测系统启动")
    print("=" * 60)

    # 设置环境变量
    os.environ['COAL_ENV'] = 'DEV'
    os.environ['USE_REAL_GRID_IN_DEV'] = 'True' if use_real_grid else 'False'
    os.environ['MOCK_SOURCE_DIR'] = images_dir
    os.environ['DEVICE_ID'] = device_id

    print(f"[INFO] 设备ID: {device_id}")
    print(f"[INFO] 格栅口数量: 125个")
    print(f"[INFO] 图片目录: {images_dir}")
    print(f"[INFO] 检测模式: 设备级完整检测")
    print(f"[INFO] 真实格栅: {'启用' if use_real_grid else '禁用'}")

    # 检查图片目录
    from pathlib import Path
    img_path = Path(images_dir)
    if not img_path.exists():
        print(f"[ERROR] 图片目录不存在: {images_dir}")
        return False

    # 统计图片数量
    images = []
    for ext in ["*.png", "*.jpg", "*.jpeg", "*.bmp"]:
        images.extend(img_path.glob(ext))
        images.extend(img_path.glob(f"**/{ext}"))  # 包含子目录

    print(f"[INFO] 找到图片: {len(images)} 张")
    if len(images) == 0:
        print(f"[ERROR] 图片目录中没有找到图片文件")
        return False

    # 验证环境
    try:
        from config.config import Config
        from algo.device_detector import DeviceDetector

        config = Config()
        config.USE_REAL_GRID_IN_DEV = use_real_grid
        config.MOCK_SOURCE_DIR = images_dir

        # 测试创建检测器
        detector = DeviceDetector(config, device_id=device_id, grid_count=125)

        print(f"[SUCCESS] 设备1检测器初始化成功")
        print(f"[INFO] 实际格栅数量: {len(detector.device_grids)}")
        print(f"[INFO] 设备ID: {detector.device_id}")

        return True

    except Exception as e:
        print(f"[ERROR] 初始化失败: {e}")
        return False

if __name__ == "__main__":
    import argparse

    # 解析命令行参数
    parser = argparse.ArgumentParser(description="设备1检测系统")
    parser.add_argument("--images", default="tests/sample_only",
                       help="图片目录路径 (默认: tests/sample_only)")
    parser.add_argument("--port", type=int, default=8002,
                       help="Web端口 (默认: 8002)")
    parser.add_argument("--device-id", default=os.getenv("DEVICE_ID", "device-1"),
                       help="设备ID (默认: device-1)")
    parser.add_argument("--use-real-grid", dest="use_real_grid", action="store_true",
                       default=True, help="启用真实格栅配置 (默认: 启用)")
    parser.add_argument("--no-real-grid", dest="use_real_grid", action="store_false",
                       help="禁用真实格栅配置，改用模拟格栅")

    args = parser.parse_args()

    # 设置环境
    if not setup_device1_environment(
        images_dir=args.images,
        device_id=args.device_id,
        use_real_grid=args.use_real_grid,
    ):
        print("[ERROR] 环境设置失败")
        sys.exit(1)

    print(f"\n[INFO] 启动设备1检测Web界面...")
    print(f"[INFO] 访问地址: http://localhost:{args.port}")
    print(f"[INFO] 检测内容: 一张图像中的125个格栅口状态")
    print(f"[INFO] 按 Ctrl+C 停止")
    print("=" * 60)

    # 启动Web服务
    try:
        uvicorn.run(
            "web.device_app:app",
            host="0.0.0.0",
            port=args.port,
            reload=False,
            log_level="info"
        )
    except KeyboardInterrupt:
        print(f"\n[INFO] 设备1检测服务已停止")
    except Exception as e:
        print(f"[ERROR] 启动失败: {e}")
