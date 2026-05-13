# Allen Bradley PLC 点位表配置
## CompactLogix 1769-L16ER

### 创建用户自定义数据类型(UDT)

#### 1. Detection 数据类型
在 RSLogix 5000 中创建名为 `Detection` 的 UDT：

| 成员名称 | 数据类型 | 描述 |
|----------|----------|------|
| CoalPresent | BOOL | 积煤检测结果 |
| Confidence | STRING | 置信度等级 ("HIGH", "MEDIUM", "LOW") |
| NeedManualConfirm | BOOL | 需人工确认标志 |
| VisionHeartbeat | INT | 视觉系统心跳递增值 |
| FaultCode | INT | 故障码 (0=正常, 1=相机故障, 2=通信故障, 3=画面质量问题, 4=低置信度) |
| SystemReady | BOOL | 视觉系统就绪标志 |
| GridVisibleRatio | REAL | 格栅可见比例 (0.0-1.0) |
| CoalCoverageRatio | REAL | 积煤覆盖比例 (0.0-1.0) |
| ConfidenceScore | REAL | 置信度分数 (0.0-1.0) |
| LastUpdateTime | STRING | 最后更新时间戳 |

#### 2. 在主程序中声明变量

```ladder
// 主程序标签页
Detection: Detection  // 使用自定义 Detection 数据类型
```

### RSLogix 5000 配置步骤

1. **创建新项目**
   - 控制器类型：1769-L16ER
   - 修订版本：选择最新版本
   - 项目名称：CoalDetectionSystem

2. **网络配置**
   - PLC IP: 192.168.1.200
   - 子网掩码: 255.255.255.0
   - 网关: 192.168.1.1

3. **创建UDT**
   - 右键"数据类型" → "新建数据类型"
   - 名称：Detection
   - 添加上述成员

4. **创建标签**
   - 在"控制器标签"中创建：Detection 变量

5. **添加监控逻辑**
   ```ladder
   // 心跳超时检测 (2秒内无更新则报警)
   TON(Timer, EN:=TRUE, PT:=T#2s, Q=>HeartbeatTimeout);

   // 积煤报警输出
   AlarmOutput := Detection.CoalPresent AND (Detection.Confidence <> 'LOW');

   // 系统故障指示
   SystemFault := (Detection.FaultCode <> 0) OR HeartbeatTimeout;
   ```

### 测试点位

在 RSLogix 5000 中可以手动修改这些值进行测试：
- Detection.SystemReady = TRUE
- Detection.CoalPresent = FALSE
- Detection.Confidence = "HIGH"
- Detection.VisionHeartbeat = 递增测试

### 导出配置

完成配置后，导出项目文件：
- 文件 → 导出 → L5X格式
- 保存为：CoalDetectionSystem.L5X