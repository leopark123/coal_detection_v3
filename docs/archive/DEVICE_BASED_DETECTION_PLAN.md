# 设备级格栅检测方案

## 🎯 需求澄清

### 实际架构
```
设备1 (Device-1) ── 包含N个格栅口
设备2 (Device-2) ── 包含N个格栅口
设备3 (Device-3) ── 包含N个格栅口
设备4 (Device-4) ── 包含N个格栅口
设备5 (Device-5) ── 包含N个格栅口
```

### 开发策略
1. **阶段1**: 完成设备1的完整检测系统
2. **阶段2**: 将设备1的方案复制到设备2-5

## 📊 格栅分配方案

假设125个格栅口按设备分配：

### 方案A：均匀分配
```
设备1: 格栅口 1-25   (25个)
设备2: 格栅口 26-50  (25个)
设备3: 格栅口 51-75  (25个)
设备4: 格栅口 76-100 (25个)
设备5: 格栅口 101-125(25个)
```

### 方案B：区域分配
```
设备1: 左上区域格栅口
设备2: 右上区域格栅口
设备3: 中央区域格栅口
设备4: 左下区域格栅口
设备5: 右下区域格栅口
```

## 🔧 技术架构

### 单设备检测系统
```python
class DeviceDetector:
    """设备级检测器"""

    def __init__(self, device_id: str, device_grids: List[GridROI]):
        self.device_id = device_id
        self.device_grids = device_grids  # 该设备的所有格栅口

    def detect_device(self, frame) -> DeviceResult:
        """检测整个设备的状态"""
        # 检测设备内所有格栅口
        # 汇总设备级结果
        pass
```

### 设备级结果
```python
class DeviceResult:
    device_id: str
    total_grids: int
    visible_grids: int
    coal_grids: int
    device_has_coal: bool
    device_confidence: str
    alert_level: str  # NORMAL/WARNING/CRITICAL
    grid_details: List[GridInfo]
```

## 🚀 实施步骤

### Step 1: 确定设备1的格栅分配
- 从125个格栅中选择设备1负责的格栅口
- 建议：格栅口0-24（共25个）

### Step 2: 创建设备1检测器
```python
# 设备1检测器
device1_grids = grid_rois[0:25]  # 前25个格栅口
device1_detector = DeviceDetector("device-1", device1_grids)
```

### Step 3: 设备1完整测试
- 检测设备1的25个格栅口
- 验证设备级判断逻辑
- 确保性能达标

### Step 4: 复制到其他设备
```python
# 复制到设备2-5
device2_detector = DeviceDetector("device-2", grid_rois[25:50])
device3_detector = DeviceDetector("device-3", grid_rois[50:75])
device4_detector = DeviceDetector("device-4", grid_rois[75:100])
device5_detector = DeviceDetector("device-5", grid_rois[100:125])
```

## 🎛️ Web界面设计

### 设备选择界面
```html
<div class="device-selector">
    <button data-device="device-1">设备1 (格栅1-25)</button>
    <button data-device="device-2">设备2 (格栅26-50)</button>
    <button data-device="device-3">设备3 (格栅51-75)</button>
    <button data-device="device-4">设备4 (格栅76-100)</button>
    <button data-device="device-5">设备5 (格栅101-125)</button>
</div>
```

### 设备状态显示
```html
<div class="device-status">
    <h2>设备1状态</h2>
    <div class="device-overview">
        <span>总格栅: 25</span>
        <span>可见格栅: 23</span>
        <span>积煤格栅: 2</span>
        <span class="alert-critical">需要清理</span>
    </div>
</div>
```

## 📈 设备级判断逻辑

```python
def judge_device_status(grid_results: List[GridInfo]) -> DeviceStatus:
    """设备级积煤判断"""
    total = len(grid_results)
    coal_count = sum(1 for g in grid_results if g.has_coal)
    coal_ratio = coal_count / total

    # 设备级判断
    if coal_ratio >= 0.3:  # 30%以上格栅有煤
        return DeviceStatus.CRITICAL
    elif coal_ratio >= 0.2:  # 20%以上格栅有煤
        return DeviceStatus.WARNING
    elif coal_ratio >= 0.1:  # 10%以上格栅有煤
        return DeviceStatus.ATTENTION
    else:
        return DeviceStatus.NORMAL
```

## 🔄 复制推广策略

### 配置模板化
```yaml
# config/device_template.yaml
device_template:
  detection_params:
    grid_visible_threshold: 0.85
    coal_coverage_threshold: 0.05
    confidence_thresholds:
      high: 0.95
      medium: 0.80
      low: 0.50

  alert_rules:
    critical_threshold: 0.3
    warning_threshold: 0.2
    attention_threshold: 0.1
```

### 一键部署脚本
```python
def deploy_to_device(template_config, target_device_id, grid_range):
    """一键部署到目标设备"""
    # 复制配置
    # 分配格栅口
    # 创建检测器
    # 启动服务
```

## ⚡ 性能目标

### 单设备性能
- **检测延迟**: < 500ms (25个格栅口)
- **设备判断**: < 100ms
- **Web刷新**: 1-2秒间隔

### 5设备并行
- **总体延迟**: < 1秒
- **并发处理**: 支持5设备同时检测
- **资源占用**: < 2GB内存