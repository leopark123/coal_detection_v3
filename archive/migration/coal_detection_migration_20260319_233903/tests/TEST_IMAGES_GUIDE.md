# 测试图片配置说明

## 添加新测试图片的步骤：

### 1. 将图片复制到对应目录：
- tests/test_images/              # 通用测试图片
- tests/test_images/normal/       # 正常状态（无积煤）
- tests/test_images/coal_light/   # 轻度积煤
- tests/test_images/coal_heavy/   # 重度积煤
- tests/test_images/edge_cases/   # 边缘情况
- tests/test_images/lighting/     # 不同光照

### 2. 支持的图片格式：
- .png (推荐)
- .jpg/.jpeg
- .bmp

### 3. 图片要求：
- 分辨率: 建议与标注图片一致 (462x603)
- 包含: 125个格栅口的完整图像
- 质量: 清晰，对比度适中

### 4. 启动检测：
```bash
# 使用多图片模式（循环检测所有图片）
python start_device1_detection.py --images tests/test_images

# 使用单图片模式（只检测标注图片）
python start_device1_detection.py --images tests/sample_only
```

### 5. 图片分类建议：

#### normal/ (正常状态)
- 无积煤或极少积煤
- 格栅清洁可见
- 光照良好

#### coal_light/ (轻度积煤)
- 少量格栅有积煤 (< 5%)
- 积煤厚度较薄
- 大部分格栅仍可见

#### coal_heavy/ (重度积煤)
- 大量格栅有积煤 (> 10%)
- 积煤厚度较厚
- 部分格栅完全被遮挡

#### edge_cases/ (边缘情况)
- 阴影干扰
- 锈斑、污渍
- 异物遮挡
- 部分设备故障

#### lighting/ (不同光照)
- 强光照射
- 光照不足
- 不均匀照明
- 阴天/晴天差异

### 6. 测试流程：
1. 添加新图片到对应目录
2. 运行: python manage_test_images.py --list
3. 启动检测: python start_device1_detection.py --images tests/test_images
4. 观察检测效果，记录准确率
5. 根据结果调整检测参数
