# 缺失文件清单

## 🔴 高优先级（影响系统运行）
- [ ] `algo/ecc_aligner.py` - ECC配准算法
  - 影响：生产模式下图像配准失败
  - 风险等级：HIGH

## 🟡 中优先级（影响功能完整性）
- [ ] `plc/communicator.py` - PLC通信抽象层
  - 影响：PLC通信架构不完整
  - 风险等级：MEDIUM

- [ ] `plc/heartbeat.py` - 心跳机制
  - 影响：安全监控功能缺失
  - 风险等级：MEDIUM

## 📋 实现建议

### ECC配准算法模板：
```python
# algo/ecc_aligner.py
class ECCAligner:
    def __init__(self, config):
        self.config = config
        self.reference_small = None  # 降采样基准图
        self.warp_matrix = np.eye(2, 3, dtype=np.float32)

    def align(self, frame):
        # 1. 降采样（3072×2048 → 320×240）
        # 2. 小图算矩阵
        # 3. 缩放到原图尺寸
        # 4. 应用变换
        pass
```

### PLC心跳机制模板：
```python
# plc/heartbeat.py
class HeartbeatManager:
    def __init__(self, interval_ms=500):
        self.interval = interval_ms / 1000
        self.counter = 0

    def get_heartbeat(self):
        self.counter = (self.counter + 1) % 65536
        return self.counter
```