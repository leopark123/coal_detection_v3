"""
翻车机积煤检测系统 V3.0 - 测试图片生成工具

用途：在没有真实现场图片时，生成模拟测试图片

运行：python tools/generate_test_images.py
"""

import cv2
import numpy as np
from pathlib import Path
import random


def generate_base_grid(width: int, height: int) -> np.ndarray:
    """
    生成基础格栅图像
    
    灰色底板 + 黑色格栅孔（4行 x 6列）
    """
    # 灰色底板
    img = np.full((height, width, 3), 160, dtype=np.uint8)
    
    # 添加一些纹理（模拟金属表面）
    noise = np.random.randint(-10, 10, (height, width), dtype=np.int16)
    for c in range(3):
        img[:, :, c] = np.clip(img[:, :, c].astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    # 格栅孔参数
    rows, cols = 4, 6
    margin_x = width * 0.1
    margin_y = height * 0.15
    spacing_x = (width - 2 * margin_x) / (cols - 1)
    spacing_y = (height - 2 * margin_y) / (rows - 1)
    hole_w = int(width * 0.08)
    hole_h = int(height * 0.10)
    
    # 绘制格栅孔（黑色/深灰色，模拟透光）
    for row in range(rows):
        for col in range(cols):
            cx = int(margin_x + col * spacing_x)
            cy = int(margin_y + row * spacing_y)
            x1, y1 = cx - hole_w // 2, cy - hole_h // 2
            x2, y2 = cx + hole_w // 2, cy + hole_h // 2
            
            # 孔的颜色（深灰到黑色随机）
            hole_color = random.randint(20, 40)
            cv2.rectangle(img, (x1, y1), (x2, y2), (hole_color,) * 3, -1)
            
            # 添加孔的边框（模拟格栅边缘）
            cv2.rectangle(img, (x1, y1), (x2, y2), (100, 100, 100), 2)
    
    return img


def add_coal_layer(img: np.ndarray, coverage: float, pattern: str = "random") -> np.ndarray:
    """
    添加积煤层
    
    Args:
        img: 原始图像
        coverage: 覆盖率 (0.0 ~ 1.0)
        pattern: 积煤模式 ("random", "left", "bottom", "center")
    """
    result = img.copy()
    h, w = img.shape[:2]
    
    # 煤的颜色（深灰到黑色）
    coal_color = (random.randint(10, 30),) * 3
    
    if pattern == "left":
        # 左侧积煤
        coal_w = int(w * coverage * 1.5)
        cv2.rectangle(result, (0, 0), (coal_w, h), coal_color, -1)
        
    elif pattern == "bottom":
        # 底部积煤
        coal_h = int(h * coverage * 1.5)
        cv2.rectangle(result, (0, h - coal_h), (w, h), coal_color, -1)
        
    elif pattern == "center":
        # 中心积煤
        cx, cy = w // 2, h // 2
        radius = int(min(w, h) * coverage)
        cv2.circle(result, (cx, cy), radius, coal_color, -1)
        
    else:
        # 随机积煤
        num_blobs = int(coverage * 20)
        for _ in range(num_blobs):
            x = random.randint(0, w - 1)
            y = random.randint(0, h - 1)
            radius = random.randint(30, 100)
            cv2.circle(result, (x, y), radius, coal_color, -1)
    
    # 添加边缘模糊，让积煤看起来更自然
    result = cv2.GaussianBlur(result, (5, 5), 0)
    
    return result


def add_shadow(img: np.ndarray, direction: str = "diagonal") -> np.ndarray:
    """添加阴影"""
    result = img.copy()
    h, w = img.shape[:2]
    
    # 创建阴影遮罩
    shadow = np.zeros((h, w), dtype=np.float32)
    
    if direction == "diagonal":
        for i in range(h):
            for j in range(w):
                shadow[i, j] = (i + j) / (h + w)
    elif direction == "horizontal":
        for j in range(w):
            shadow[:, j] = j / w
    else:
        for i in range(h):
            shadow[i, :] = i / h
    
    # 应用阴影
    shadow = (shadow * 80).astype(np.uint8)
    for c in range(3):
        result[:, :, c] = np.clip(
            result[:, :, c].astype(np.int16) - shadow, 0, 255
        ).astype(np.uint8)
    
    return result


def add_rust(img: np.ndarray, intensity: float = 0.3) -> np.ndarray:
    """添加锈斑"""
    result = img.copy()
    h, w = img.shape[:2]
    
    # 锈斑颜色（橙红色）
    rust_colors = [
        (30, 60, 120),   # BGR 深锈色
        (40, 80, 150),   # BGR 浅锈色
        (20, 50, 100),   # BGR 暗锈色
    ]
    
    num_spots = int(intensity * 30)
    for _ in range(num_spots):
        x = random.randint(0, w - 1)
        y = random.randint(0, h - 1)
        radius = random.randint(10, 50)
        color = random.choice(rust_colors)
        
        # 半透明叠加
        overlay = result.copy()
        cv2.circle(overlay, (x, y), radius, color, -1)
        result = cv2.addWeighted(overlay, 0.5, result, 0.5, 0)
    
    return result


def add_dust(img: np.ndarray, intensity: float = 0.3) -> np.ndarray:
    """添加灰尘/模糊效果"""
    result = img.copy()
    
    # 添加高斯模糊
    blur_size = int(intensity * 20) * 2 + 1
    result = cv2.GaussianBlur(result, (blur_size, blur_size), 0)
    
    # 添加亮度降低
    result = (result * (1 - intensity * 0.3)).astype(np.uint8)
    
    return result


def generate_test_images():
    """生成所有测试图片"""
    
    output_base = Path("tests/mock_data")
    output_base.mkdir(parents=True, exist_ok=True)
    
    # 图像尺寸
    w, h = 1024, 768
    
    print("=" * 50)
    print("  翻车机积煤检测系统 - 测试图片生成工具")
    print("=" * 50)
    
    # ═══════════════════════════════════════════════════════════════
    # 1. 干净格栅（无积煤）
    # ═══════════════════════════════════════════════════════════════
    clean_dir = output_base / "clean"
    clean_dir.mkdir(exist_ok=True)
    
    for i in range(5):
        img = generate_base_grid(w, h)
        cv2.imwrite(str(clean_dir / f"clean_{i+1:02d}.jpg"), img)
        print(f"  [OK] clean/clean_{i+1:02d}.jpg")
    
    # ═══════════════════════════════════════════════════════════════
    # 2. 薄层积煤
    # ═══════════════════════════════════════════════════════════════
    light_dir = output_base / "coal_light"
    light_dir.mkdir(exist_ok=True)
    
    for i, pattern in enumerate(["random", "left", "bottom"]):
        img = generate_base_grid(w, h)
        img = add_coal_layer(img, 0.15, pattern)
        cv2.imwrite(str(light_dir / f"light_{i+1:02d}_{pattern}.jpg"), img)
        print(f"  [OK] coal_light/light_{i+1:02d}_{pattern}.jpg")
    
    # ═══════════════════════════════════════════════════════════════
    # 3. 严重积煤
    # ═══════════════════════════════════════════════════════════════
    heavy_dir = output_base / "coal_heavy"
    heavy_dir.mkdir(exist_ok=True)
    
    for i, coverage in enumerate([0.4, 0.6, 0.8]):
        img = generate_base_grid(w, h)
        img = add_coal_layer(img, coverage, "random")
        cv2.imwrite(str(heavy_dir / f"heavy_{i+1:02d}_cov{int(coverage*100)}.jpg"), img)
        print(f"  [OK] coal_heavy/heavy_{i+1:02d}_cov{int(coverage*100)}.jpg")
    
    # ═══════════════════════════════════════════════════════════════
    # 4. 边界情况
    # ═══════════════════════════════════════════════════════════════
    edge_dir = output_base / "edge_cases"
    edge_dir.mkdir(exist_ok=True)
    
    # 阴影
    img = generate_base_grid(w, h)
    img = add_shadow(img, "diagonal")
    cv2.imwrite(str(edge_dir / "edge_shadow.jpg"), img)
    print(f"  [OK] edge_cases/edge_shadow.jpg")
    
    # 锈斑
    img = generate_base_grid(w, h)
    img = add_rust(img, 0.5)
    cv2.imwrite(str(edge_dir / "edge_rust.jpg"), img)
    print(f"  [OK] edge_cases/edge_rust.jpg")
    
    # 积灰/模糊
    img = generate_base_grid(w, h)
    img = add_dust(img, 0.4)
    cv2.imwrite(str(edge_dir / "edge_dust.jpg"), img)
    print(f"  [OK] edge_cases/edge_dust.jpg")
    
    # 过暗
    img = generate_base_grid(w, h)
    img = (img * 0.2).astype(np.uint8)
    cv2.imwrite(str(edge_dir / "edge_dark.jpg"), img)
    print(f"  [OK] edge_cases/edge_dark.jpg")
    
    # 过曝
    img = generate_base_grid(w, h)
    img = np.clip(img.astype(np.int16) + 150, 0, 255).astype(np.uint8)
    cv2.imwrite(str(edge_dir / "edge_overexposed.jpg"), img)
    print(f"  [OK] edge_cases/edge_overexposed.jpg")
    
    # 阴影 + 积煤（容易误判的情况）
    img = generate_base_grid(w, h)
    img = add_shadow(img, "horizontal")
    img = add_coal_layer(img, 0.1, "center")
    cv2.imwrite(str(edge_dir / "edge_shadow_coal.jpg"), img)
    print(f"  [OK] edge_cases/edge_shadow_coal.jpg")
    
    # ═══════════════════════════════════════════════════════════════
    # 5. 基准图（用于 ECC 配准）
    # ═══════════════════════════════════════════════════════════════
    config_dir = Path("config")
    config_dir.mkdir(exist_ok=True)
    
    img = generate_base_grid(w, h)
    cv2.imwrite(str(config_dir / "reference.jpg"), img)
    print(f"  [OK] config/reference.jpg (基准图)")
    
    print("=" * 50)
    print(f"  生成完成！共创建 {17} 张测试图片")
    print(f"  保存目录: {output_base.absolute()}")
    print("=" * 50)


if __name__ == "__main__":
    generate_test_images()
