# Allen Bradley PLC 点位表配置

## 硬件信息

| 项目 | 值 |
|------|-----|
| PLC 型号 | CompactLogix 1769-L16ER/B B1B |
| 固件版本 | 36.11 |
| IP 地址 | 192.168.1.19 |
| 编程软件 | RSLogix 5000 (Studio 5000 Logix Designer) |
| 通信驱动 | RSLinx Classic / FactoryTalk Linx |
| 通信协议 | Ethernet/IP (pycomm3) |

## 标签总览

共 19 个标签，分为三组：

### 一、服务器写入标签（视觉系统 → PLC）

| 标签名 | 类型 | 说明 | 安全等级 |
|--------|------|------|----------|
| `Vision_CanTip` | BOOL | **安全连锁核心信号**：无积煤=True（允许翻车）。仅当 `coal_present is False` 且 `need_manual=False` 且 `fault_code=0` 时为 True | **CRITICAL** |
| `Vision_FaultCode` | DINT | 故障码：0=正常, 1=相机故障, 2=PLC通信故障, 3=画质问题（全黑/过曝/模糊）, 4=低置信度需人工确认 | **CRITICAL** |
| `Vision_ResultValid` | BOOL | 检测结果可信：高/中置信度 且 无故障 且 结果明确 = True | HIGH |
| `IPC_Heartbeat` | DINT | 心跳递增值（500ms 周期，线程安全加锁递增，0~65535 循环） | **CRITICAL** |
| `IPC_Online` | BOOL | 视觉系统在线（启动=True, 关闭=False） | HIGH |
| `Vision_Enable` | BOOL | 视觉采集启用（UI 控制，停用时 PLC 强制 Allow_Tip=1） | HIGH |
| `Vision_CaptureState` | DINT | 采集状态：0=空闲, 1=采集中, 2=判定完成 | MEDIUM |

### 二、PLC 写入标签（PLC → 服务器）

| 标签名 | 类型 | 说明 |
|--------|------|------|
| `PLC_CaptureCmd` | DINT | 采集指令：0=空闲, 1=开始采集 |
| `Tipper_InPosition` | BOOL | 翻车机回位信号（到位=True, 翻转中=False） |

### 三、PLC 内部标签（PLC 梯形图使用）

| 标签名 | 类型 | 说明 |
|--------|------|------|
| `HB_Last` | DINT | 上次心跳值（与 IPC_Heartbeat 比较检测变化） |
| `HB_Timer` | TIMER | 心跳超时计时器（Preset=2000ms） |
| `Vision_Alive` | BOOL | 视觉系统存活（IPC_Online=1 且 心跳未超时） |
| `Allow_Tip` | BOOL | **允许翻车（最终输出，接翻车机控制回路）** |
| `Fault_Light` | BOOL | 故障指示灯输出 |
| `Manual_Confirm_Light` | BOOL | 需人工确认指示灯（FaultCode=4 时亮） |
| `Capture_Delay_Timer` | TIMER | 采集延时计时器（翻车机回位后延时 N 秒） |
| `Sim_Enable` | BOOL | 模拟测试开关（手动启停） |
| `Sim_Timer` | TIMER | 模拟周期计时器（60 秒一循环） |

## RSLogix 5000 创建步骤

### 1. 创建标签

在 **Controller Tags** 中逐个创建上述所有标签。**不使用 UDT**，全部扁平标签，便于 pycomm3 直接读写。

### 2. 梯形图逻辑（10 个 Rung）

```
Rung 0: 心跳变化检测
  NEQ IPC_Heartbeat HB_Last → MOV IPC_Heartbeat → HB_Last + RES HB_Timer

Rung 1: 心跳超时计时（2 秒）
  TON HB_Timer, Preset=2000

Rung 2: 视觉系统存活判断
  XIC IPC_Online + XIO HB_Timer.DN → OTE Vision_Alive

Rung 3: 故障报警
  XIO Vision_Alive → OTE Fault_Light

Rung 4: 允许翻车（并联两条支路）
  支路1: XIO Vision_Enable → OTE Allow_Tip  (视觉停用 → 直接允许)
  支路2: XIC Vision_Alive + XIC Vision_CanTip + XIC Vision_ResultValid
         + EQU Vision_FaultCode 0 → OTE Allow_Tip

Rung 5: 需人工确认
  EQU Vision_FaultCode 4 → OTE Manual_Confirm_Light

Rung 6: 采集延时触发
  XIC Tipper_InPosition + XIC Vision_Enable + EQU Vision_CaptureState 0
  → TON Capture_Delay_Timer (Preset 可调，当前 10000ms)

Rung 7: 发出采集指令
  XIC Capture_Delay_Timer.DN + EQU PLC_CaptureCmd 0
  → MOV 1 → PLC_CaptureCmd

Rung 8: 采集完成复位
  EQU Vision_CaptureState 2
  → MOV 0 → PLC_CaptureCmd + RES Capture_Delay_Timer

Rung 9: 回位消失立即停止
  XIO Tipper_InPosition
  → MOV 0 → PLC_CaptureCmd + RES Capture_Delay_Timer
```

### 3. 模拟测试逻辑（可选）

```
Rung 10: 模拟周期计时（60 秒）
  XIC Sim_Enable → TON Sim_Timer, Preset=60000

Rung 11: 前 20 秒回位信号=1
  XIC Sim_Enable + GEQ Sim_Timer.ACC 0 + LEQ Sim_Timer.ACC 20000
  → OTE Tipper_InPosition

Rung 12: 计时器到期复位
  XIC Sim_Timer.DN → RES Sim_Timer
```

## 安全信号逻辑

### Vision_CanTip 判定（服务器侧代码）

```python
# 仅当明确无积煤 且 不需人工确认 且 无故障时才允许翻车
# coal_present=None（不确定）时 can_tip=False（安全优先）
can_tip = (coal_present is False) and (not need_manual) and (fault_code == 0)
```

### Allow_Tip 判定（PLC 侧梯形图）

```
Allow_Tip = (Vision_Enable=0)  # 视觉停用，直接允许
          OR (Vision_Alive AND Vision_CanTip AND Vision_ResultValid AND FaultCode=0)
```

## 故障码定义

| 代码 | 含义 | 触发条件 | PLC 行为 |
|------|------|----------|----------|
| 0 | 正常 | 检测成功，结果明确 | Allow_Tip 按检测结果 |
| 1 | 相机故障 | 相机断连/采集失败 | Fault_Light=1, Allow_Tip=0 |
| 2 | PLC 通信故障 | PLC 读写失败 | Fault_Light=1 |
| 3 | 画质问题 | 画面全黑(mean<15)/过曝(mean>240)/模糊 | Fault_Light=1, Allow_Tip=0 |
| 4 | 低置信度 | 检测指标矛盾，需人工确认 | Manual_Confirm_Light=1, Allow_Tip=0 |

## 采集时序

```
翻车机翻转 → 回到原位(Tipper_InPosition=1)
  → PLC 延时(Capture_Delay_Timer)
    → PLC 写 PLC_CaptureCmd=1
      → 服务器写 Vision_CaptureState=1，开始采集
        → 连续采集，多帧投票
          → 服务器写检测结果 + Vision_CaptureState=2
            → PLC 读到 State=2，写 PLC_CaptureCmd=0
              → 服务器写 Vision_CaptureState=0，回到空闲

回位信号消失(Tipper_InPosition=0):
  → PLC 立即写 PLC_CaptureCmd=0 (Rung 9)
    → 服务器停止采集，汇总已有帧判定
```
