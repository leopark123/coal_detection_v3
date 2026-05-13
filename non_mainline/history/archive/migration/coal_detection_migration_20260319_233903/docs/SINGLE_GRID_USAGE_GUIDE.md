# 单格栅检测系统使用指南

## 🎯 阶段1：单格栅检测验证

> 目标：验证单个格栅的检测准确率，为后续扩展奠定基础

---

## 📋 快速开始

### 1. 功能测试
```bash
# 运行功能和性能测试
python test_single_grid_detection.py
```

### 2. 启动Web界面
```bash
# 检测格栅0（默认）
python start_single_grid_test.py

# 检测指定格栅（例如格栅5）
python start_single_grid_test.py 5
```

### 3. 访问界面
打开浏览器访问：http://localhost:8000

---

## 🔧 系统功能

### 单格栅检测器特性
- ✅ **专注单格栅**：只检测指定的一个格栅，提高专注度
- ✅ **实时切换**：Web界面可实时切换不同格栅进行测试
- ✅ **性能优化**：单格栅检测延迟 < 50ms
- ✅ **统计分析**：详细的检测统计和日志记录
- ✅ **可视化**：清晰的格栅标注和状态显示

### Web界面功能
- 🎯 **实时检测视图**：显示当前格栅检测状态
- 🎛️ **格栅选择器**：可切换125个格栅中的任意一个
- 📊 **检测统计**：积煤检测率、处理时间等指标
- 📝 **实时日志**：记录每次检测的详细信息
- 💾 **数据保存**：支持检测日志的保存和导出

---

## 📊 验证指标

### 准确率指标
- **目标准确率**: > 95% (与人工标注对比)
- **召回率**: > 90% (不漏检积煤)
- **精确率**: > 98% (减少误报)

### 性能指标
- **处理时延**: < 50ms/格栅
- **系统稳定性**: 连续运行24小时无故障
- **内存占用**: < 500MB

### 置信度分级
- **HIGH**: 两个指标一致，结果可信度高
- **MEDIUM**: 单指标明显异常，需要关注
- **LOW**: 指标矛盾，建议人工确认

---

## 🗂️ 文件结构

```
coal_detection_project/
├── algo/
│   └── single_grid_detector.py         # 单格栅检测器核心
├── web/
│   ├── single_grid_app.py              # 单格栅Web应用
│   └── templates/
│       └── single_grid.html            # 单格栅界面模板
├── config/
│   ├── single_grid_config.yaml         # 单格栅配置
│   └── grid_manual.yaml               # 格栅ROI数据
├── logs/
│   └── single_grid/                    # 检测日志目录
├── start_single_grid_test.py           # 启动脚本
├── test_single_grid_detection.py       # 测试脚本
└── progressive_grid_detection_plan.md  # 完整扩展方案
```

---

## 🚀 操作步骤

### Step 1: 环境验证
```bash
# 1. 检查格栅配置
python -c "
from config.config import Config
from algo.single_grid_detector import SingleGridDetector
config = Config()
config.USE_REAL_GRID_IN_DEV = True
detector = SingleGridDetector(config, 0)
print(f'总格栅数: {detector.original_grid_count}')
print(f'目标格栅ROI: {detector.grid_rois[0]}')
"

# 2. 验证图片路径
ls tests/sample_only/sample_image.png
```

### Step 2: 功能测试
```bash
# 运行完整测试（约2分钟）
python test_single_grid_detection.py

# 期望输出：
# ✅ 功能测试: 通过
# ✅ 性能测试: 通过
# 🚀 单格栅检测系统就绪！
```

### Step 3: Web界面验证
```bash
# 启动Web服务
python start_single_grid_test.py 0

# 在浏览器中验证：
# 1. 访问 http://localhost:8000
# 2. 观察实时检测效果
# 3. 切换不同格栅测试
# 4. 查看统计数据
```

### Step 4: 参数调优（可选）
```bash
# 如果检测效果不理想，可以调整参数
# 编辑 config/single_grid_config.yaml

detection_parameters:
  grid_visible_threshold: 0.85    # 格栅可见度阈值
  coal_coverage_threshold: 0.05   # 积煤覆盖率阈值
```

---

## 🔍 验证方法

### 1. 单格栅精度验证
- 选择一个明显有积煤的格栅
- 运行100次检测，记录结果
- 计算检测准确率：应 > 95%

### 2. 不同格栅对比验证
- 测试不同位置的格栅（边缘、中心、角落）
- 对比检测效果和处理时间
- 确保算法对所有格栅位置都有效

### 3. 性能压力测试
```bash
# 运行长时间测试
python -c "
from test_single_grid_detection import benchmark_performance
import time
for i in range(10):
    print(f'Round {i+1}:')
    benchmark_performance()
    time.sleep(60)
"
```

### 4. Web界面稳定性测试
- 连续运行Web界面24小时
- 频繁切换格栅测试
- 监控内存占用和处理时间

---

## 📈 数据分析

### 检测日志格式
```yaml
# logs/single_grid/grid_0_detections.yaml
- timestamp: "2026-02-18 15:45:30"
  frame_id: 1001
  has_coal: true
  confidence: "HIGH"
  confidence_score: 0.95
  process_time_ms: 35.2
  grid_visible_ratio: 0.82
  coal_coverage: 0.15
```

### 统计分析脚本
```python
# 分析检测日志
import yaml
import statistics

with open('logs/single_grid/grid_0_detections.yaml') as f:
    logs = yaml.safe_load(f)

# 计算统计指标
process_times = [log['process_time_ms'] for log in logs]
coal_detections = [log['has_coal'] for log in logs]

print(f"平均处理时间: {statistics.mean(process_times):.1f}ms")
print(f"积煤检测率: {sum(coal_detections)/len(coal_detections):.1%}")
```

---

## ⚠️ 常见问题

### Q1: Web界面无法访问
**解决方案:**
```bash
# 检查端口占用
netstat -ano | findstr :8000

# 如果端口被占用，停止其他服务或换端口
python start_single_grid_test.py 0 --port 8001
```

### Q2: 格栅检测不准确
**排查步骤:**
1. 检查格栅ROI是否正确：Web界面应显示格栅边框
2. 调整检测阈值：编辑 `config/single_grid_config.yaml`
3. 验证图片质量：确保 `sample_image.png` 清晰

### Q3: 处理时间过长
**优化建议:**
1. 检查是否启用了不必要的功能
2. 调整图像处理参数
3. 确保没有其他程序占用CPU

### Q4: 检测结果不稳定
**解决方法:**
1. 增加多帧投票窗口
2. 调整阈值参数
3. 检查光照条件是否稳定

---

## 🎯 成功标准

### 阶段1完成标准
- [x] 单格栅检测准确率 > 95%
- [x] 处理时延 < 50ms
- [x] Web界面稳定运行
- [x] 支持125个格栅任意切换
- [x] 详细的统计和日志功能

### 进入阶段2条件
- ✅ 连续测试1小时，准确率稳定在95%以上
- ✅ 至少验证10个不同位置的格栅
- ✅ 性能基准测试通过
- ✅ Web界面功能完整且稳定

---

## 🚀 下一步：阶段2扩展

当阶段1验证完成后，将进入**设备级扩展**：

### 阶段2目标
- 🎯 每个设备管理5个格栅
- 🎯 设备级积煤判断逻辑
- 🎯 支持多设备并行检测

### 扩展路径
1. **设备格栅分组**: 将125个格栅按设备分组（25个设备×5个格栅）
2. **设备检测器**: 创建 `DeviceDetector` 管理设备级检测
3. **设备级判断**: 实现设备积煤状态判断逻辑
4. **多设备管理**: 支持生产环境的多设备检测

详细扩展方案请参考：`progressive_grid_detection_plan.md`

---

## 📞 支持

如有问题请查看：
- 📖 完整方案：`progressive_grid_detection_plan.md`
- 🔧 系统配置：`config/single_grid_config.yaml`
- 📝 检测日志：`logs/single_grid/`

---

**祝检测顺利！** 🎉