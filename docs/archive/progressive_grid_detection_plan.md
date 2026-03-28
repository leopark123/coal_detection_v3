# 渐进式格栅检测扩展方案

## 一、现状分析

### 当前系统状态
- ✅ **125个格栅ROI已加载** (从GridEditorToolKit标注)
- ✅ **检测算法完整** (格栅计数 + 积煤面积)
- ✅ **Web界面就绪** (实时检测展示)
- ✅ **配置系统完善** (支持动态ROI管理)

### 业务需求
- 🎯 **每个设备5个格栅** (设备级管理)
- 🎯 **单格栅先验证** (确保准确率)
- 🎯 **逐步扩展部署** (降低风险)

## 二、分阶段实施方案

### 阶段1：单格栅检测验证 (1-2周)

#### 1.1 创建单格栅检测模式
```python
class SingleGridDetector(CoalDetector):
    """单格栅检测器 - 用于算法验证"""

    def __init__(self, config, target_grid_id: int = 0):
        super().__init__(config)
        # 只保留指定的一个格栅
        self.target_grid_id = target_grid_id
        self.single_grid_roi = self.grid_rois[target_grid_id:target_grid_id+1]
        self.grid_rois = self.single_grid_roi
```

#### 1.2 验证指标体系
- **准确率**: > 95% (与人工标注对比)
- **召回率**: > 90% (不漏检积煤)
- **精确率**: > 98% (减少误报)
- **处理时延**: < 50ms/格栅

#### 1.3 参数调优
- 格栅阈值优化
- 积煤颜色范围调整
- 噪声滤波参数
- ECC配准精度

### 阶段2：设备级扩展 (2-3周)

#### 2.1 设备格栅分组
```python
class DeviceGridManager:
    """设备格栅管理器"""

    def __init__(self, device_id: str):
        self.device_id = device_id
        self.device_grids = self._load_device_grids()

    def _load_device_grids(self) -> List[GridROI]:
        """加载设备的5个格栅"""
        # 从配置文件读取设备格栅映射
        return [
            self.all_grids[i] for i in self.device_grid_indices[self.device_id]
        ]
```

#### 2.2 设备检测器
```python
class DeviceDetector(CoalDetector):
    """设备级检测器 - 管理5个格栅"""

    def __init__(self, config, device_id: str):
        super().__init__(config)
        self.device_manager = DeviceGridManager(device_id)
        self.grid_rois = self.device_manager.device_grids

    def detect_device_status(self, frame) -> DeviceDetectionResult:
        """设备级检测"""
        result = self.detect(frame)

        # 设备级判断逻辑
        device_status = self._judge_device_coal_status(result)

        return DeviceDetectionResult(
            device_id=self.device_manager.device_id,
            grid_results=result.grid_details,
            device_has_coal=device_status.has_coal,
            device_confidence=device_status.confidence,
            alert_level=device_status.alert_level
        )
```

#### 2.3 设备级判断策略
```python
def _judge_device_coal_status(self, result) -> DeviceStatus:
    """设备级积煤判断"""
    coal_grids = sum(1 for g in result.grid_details if g.has_coal)
    total_grids = len(result.grid_details)

    # 设备级判断逻辑
    if coal_grids >= 3:  # 5个格栅中3个以上有煤
        return DeviceStatus.CRITICAL
    elif coal_grids >= 2:
        return DeviceStatus.WARNING
    elif coal_grids >= 1:
        return DeviceStatus.ATTENTION
    else:
        return DeviceStatus.NORMAL
```

### 阶段3：生产级部署 (3-4周)

#### 3.1 多设备管理
```python
class ProductionDetectionSystem:
    """生产级检测系统"""

    def __init__(self, config):
        self.devices = {}
        self.load_device_configs()

    def add_device(self, device_id: str, camera_config: dict):
        """添加设备"""
        self.devices[device_id] = {
            'detector': DeviceDetector(config, device_id),
            'camera': create_camera(camera_config),
            'last_result': None,
            'status': 'ready'
        }

    async def detect_all_devices(self):
        """并行检测所有设备"""
        tasks = []
        for device_id, device_info in self.devices.items():
            task = self._detect_single_device(device_id)
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        return results
```

## 三、配置文件设计

### 3.1 设备格栅映射配置
```yaml
# config/device_grid_mapping.yaml
devices:
  device_001:
    name: "1号翻车机"
    grid_indices: [0, 1, 2, 3, 4]    # 对应125个格栅中的前5个
    camera_ip: "192.168.1.101"
    plc_address: "192.168.1.201"

  device_002:
    name: "2号翻车机"
    grid_indices: [5, 6, 7, 8, 9]    # 对应125个格栅中的6-10个
    camera_ip: "192.168.1.102"
    plc_address: "192.168.1.202"

# ... 可扩展到25个设备 (125个格栅 ÷ 5个/设备)
```

### 3.2 检测模式配置
```yaml
# config/detection_modes.yaml
detection_modes:
  single_grid:
    enabled: true
    target_grid_id: 0
    verification_mode: true

  device_level:
    enabled: false
    target_device: "device_001"

  production:
    enabled: false
    all_devices: true
```

## 四、Web界面适配

### 4.1 模式切换界面
```html
<!-- 检测模式选择 -->
<div class="mode-selector">
    <button id="single-mode" class="mode-btn">单格栅验证</button>
    <button id="device-mode" class="mode-btn">设备级检测</button>
    <button id="production-mode" class="mode-btn">生产模式</button>
</div>
```

### 4.2 设备级视图
```html
<!-- 设备状态总览 -->
<div class="device-overview">
    <div class="device-card" data-device="device_001">
        <h3>1号翻车机</h3>
        <div class="device-status status-normal">正常</div>
        <div class="grid-status">
            <span class="grid-indicator grid-normal"></span>
            <span class="grid-indicator grid-normal"></span>
            <span class="grid-indicator grid-warning"></span>
            <span class="grid-indicator grid-normal"></span>
            <span class="grid-indicator grid-normal"></span>
        </div>
    </div>
</div>
```

## 五、实施时间表

### Week 1: 单格栅模式开发
- [ ] 创建SingleGridDetector类
- [ ] 实现格栅选择功能
- [ ] 添加验证指标统计
- [ ] 完善Web界面单格栅模式

### Week 2: 单格栅验证调优
- [ ] 收集测试数据
- [ ] 调优检测参数
- [ ] 验证准确率指标
- [ ] 记录最优参数组合

### Week 3: 设备级扩展开发
- [ ] 创建DeviceGridManager
- [ ] 实现DeviceDetector
- [ ] 设计设备级判断逻辑
- [ ] 配置文件系统

### Week 4: 设备级测试
- [ ] 5格栅联合检测测试
- [ ] 设备级判断逻辑验证
- [ ] 性能压力测试
- [ ] Web界面设备视图

### Week 5-6: 生产级准备
- [ ] 多设备管理系统
- [ ] 并行检测优化
- [ ] 监控告警系统
- [ ] 部署文档编写

## 六、风险控制

### 6.1 技术风险
- **性能风险**: 5格栅检测时延控制在250ms内
- **准确率风险**: 单格栅验证通过后再扩展
- **稳定性风险**: 渐进式部署，支持回退

### 6.2 质量保证
- **单元测试**: 每个检测模式独立测试
- **集成测试**: 设备级联合测试
- **性能测试**: 并发检测压力测试
- **回归测试**: 参数调整后验证

## 七、成功标准

### 7.1 阶段1成功标准
- 单格栅检测准确率 > 95%
- 处理时延 < 50ms
- 误报率 < 2%

### 7.2 阶段2成功标准
- 5格栅设备检测稳定运行
- 设备级判断逻辑合理
- 处理时延 < 250ms

### 7.3 阶段3成功标准
- 支持多设备并行检测
- 系统可用性 > 99.9%
- 支持生产级监控告警