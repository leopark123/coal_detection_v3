# 翻车机积煤检测系统 V3.0

基于计算机视觉的工业级积煤检测系统，用于煤矿翻车机房格栅积煤实时检测，与 PLC 安全连锁。

## 系统概述

- **多机多漏斗架构**：一台服务器管理 N 台翻车机 × M 个漏斗，动态增减
- **PLC 触发采集**：翻车机回位 → PLC 延时 → PLC 发采集指令 → 服务器采集 → 投票判定 → 结果写回 PLC
- **安全连锁**：检测结果直接控制翻车机允许/禁止翻转，宁可漏报不可误报
- **Web 监控**：实时视频推流 + 状态展示 + 在线管理

## 硬件环境

| 设备 | 型号 | IP | 说明 |
|------|------|-----|------|
| 工控机 | Windows 10 Pro | 192.168.1.10 | Python 3.10+，运行检测服务 |
| 相机 | Basler acA1600-60gm | 192.168.1.12 | Mono8 灰度, 1600x1200, GigE |
| PLC | AB 1769-L16ER/B B1B | 192.168.1.19 | CompactLogix, Ethernet/IP |
| 网络 | 千兆交换机 | — | 相机/PLC/工控机互联 |

## 快速开始

```powershell
# 1. 安装依赖
pip install -r requirements.txt
pip install pypylon    # Basler 相机驱动
pip install pycomm3    # AB PLC 通信

# 2. 开发模式（无硬件）
set COAL_ENV=DEV
python -m uvicorn web.unified_app:app --host 0.0.0.0 --port 8080

# 3. 生产模式（连接真实硬件）
python -m uvicorn web.unified_app:app --host 0.0.0.0 --port 8080

# 4. 浏览器访问
# http://localhost:8080
```

## 采集时序（PLC 控制）

```
翻车机翻转 → 回到原位 → PLC 延时(可调) → PLC 发采集指令 → 服务器采集 → 投票判定 → 结果写 PLC
                                                                              ↓
                                                                    回位信号消失 → PLC 停止指令 → 服务器停止采集
```

**PLC 负责**：延时控制、发出采集/停止指令
**服务器负责**：收到指令就采集/停止，不做时间判断

### PLC 梯形图逻辑

```
Rung 0: NEQ IPC_Heartbeat HB_Last → MOV + RES HB_Timer     # 心跳变化检测
Rung 1: TON HB_Timer 2000ms                                  # 心跳超时 2 秒
Rung 2: IPC_Online + XIO HB_Timer.DN → Vision_Alive          # 视觉系统存活
Rung 3: XIO Vision_Alive → Fault_Light                       # 故障报警灯
Rung 4: Vision_Enable 并联:
        支路1: XIO Vision_Enable → Allow_Tip                  # 视觉停用 → 直接允许翻车
        支路2: Vision_Alive + Vision_CanTip + Vision_ResultValid + EQU FaultCode=0 → Allow_Tip
Rung 5: EQU FaultCode=4 → Manual_Confirm_Light               # 需人工确认灯
Rung 6: Tipper_InPosition + Vision_Enable + EQU CaptureState=0 → TON 延时
Rung 7: Delay.DN + EQU CaptureCmd=0 → MOV 1 → PLC_CaptureCmd
Rung 8: EQU CaptureState=2 → MOV 0 → PLC_CaptureCmd + RES Timer
Rung 9: XIO Tipper_InPosition → MOV 0 → PLC_CaptureCmd + RES Timer  # 回位消失立即停止
```

## PLC 点位表

### 视觉系统标签（服务器写入）

| 标签 | 类型 | 说明 |
|------|------|------|
| Vision_CanTip | BOOL | 可翻转（无积煤=True，**安全连锁核心信号**） |
| Vision_FaultCode | DINT | 故障码（0=正常, 1=相机, 2=PLC通信, 3=画质, 4=需人工） |
| Vision_ResultValid | BOOL | 结果可信（高/中置信度=True） |
| IPC_Heartbeat | DINT | 心跳递增值（500ms 周期） |
| IPC_Online | BOOL | 视觉系统在线 |
| Vision_Enable | BOOL | 视觉采集启用（停用时 PLC 强制 Allow_Tip=1） |
| Vision_CaptureState | DINT | 采集状态（0=空闲, 1=采集中, 2=判定完成） |

### PLC 控制标签（PLC 写入）

| 标签 | 类型 | 说明 |
|------|------|------|
| PLC_CaptureCmd | DINT | 采集指令（0=空闲, 1=开始采集） |
| Tipper_InPosition | BOOL | 翻车机回位信号 |

### PLC 内部标签

| 标签 | 类型 | 说明 |
|------|------|------|
| HB_Last | DINT | 上次心跳值 |
| HB_Timer | TIMER | 心跳超时计时器 |
| Vision_Alive | BOOL | 视觉系统存活 |
| Allow_Tip | BOOL | 允许翻车（最终输出） |
| Fault_Light | BOOL | 故障指示灯 |
| Manual_Confirm_Light | BOOL | 需人工确认指示灯 |
| Capture_Delay_Timer | TIMER | 采集延时计时器 |

## 检测算法

### 双因素检测

| 因素 | 方法 | 输出 |
|------|------|------|
| 格栅孔计数 | 二值化 + 轮廓面积 | 格栅可见率 (0~1) |
| 积煤面积 | HSV 分割 + 掩码统计 | 覆盖率 (0~1) |

### 三级置信度判定

| 置信度 | 条件 | 动作 |
|--------|------|------|
| HIGH | 两指标一致 | 直接输出 |
| MEDIUM | 单指标明显异常 | 直接输出 |
| LOW | 指标矛盾 | 需人工确认，FaultCode=4 |

### 处理流程

```
原始帧 → 质量自检 → ECC配准(降采样320x240) → CLAHE增强 → 双因素检测 → 综合判定
```

## Web 界面

| 页面 | URL | 功能 |
|------|-----|------|
| 总览 | / | 所有翻车机卡片、实时时钟、采集状态、报警统计、启停按钮 |
| 翻车机详情 | /machine/{id} | 多路视频网格、PLC 状态、启停按钮 |
| 漏斗详情 | /machine/{id}/funnel/{id} | 大图视频、检测结果、采集窗口时间线、设备状态 |
| 管理设置 | /settings | 增删翻车机/漏斗、修改参数（密码保护） |

### 视觉启停控制

UI 上的启停按钮与 PLC 互锁：
- **采集中**：Vision_Enable=1，PLC 正常检测逻辑
- **已停用**：Vision_Enable=0，PLC 强制 Allow_Tip=1（允许翻车），心跳继续

## 多机配置

编辑 `config/devices.yaml`：

```yaml
machines:
  - id: machine-1
    name: 1#翻车机
    plc_ip: 192.168.1.19
    funnels:
      - id: funnel-1
        name: 1#漏斗
        camera_ip: 192.168.1.12
        pixel_format: mono       # mono=灰度, color=彩色（将来切换）
        grid_count: 125
        capture_vote_threshold: 0.6
```

也可通过设置页在线增删，自动持久化。

## 项目结构

```
coal_detection/
├── start_unified.py              # 开发模式入口（→ web.unified_app）
├── start_production.bat          # 生产模式入口（看门狗自重启）
├── config/
│   ├── config.py                 # 配置类（DEV/PROD 模式切换）
│   ├── devices.yaml              # 多翻车机拓扑配置
│   └── devices_config.py         # 拓扑配置加载器
├── core/
│   └── capture_window.py         # PLC 触发采集窗口状态机
├── drivers/
│   ├── factory.py                # 驱动工厂（自动选 Mock/真实）
│   ├── basler_camera.py          # Basler GigE 相机驱动
│   └── mock_drivers.py           # Mock 驱动（开发用）
├── algo/
│   ├── detector.py               # 主检测算法（ECC+CLAHE+双因素）
│   ├── device_detector.py        # 设备级检测（多格栅聚合）
│   └── judge.py                  # 三级置信度判定
├── plc/
│   └── allen_bradley.py          # AB PLC 通信（9标签协议，线程安全）
├── web/
│   ├── unified_app.py            # 统一 Web 应用（FastAPI，唯一入口）
│   ├── state_manager.py          # 中央状态管理器
│   ├── admin_api.py              # 管理员 API（鉴权+限流）
│   ├── archive_worker.py         # 异步归档 Worker（V3.0.12+）
│   ├── archive_janitor.py        # 归档清理守护线程（V3.0.12+）
│   ├── common.py                 # WebSocket 推流（异步非阻塞）
│   ├── templates/                # 页面模板（总览/机器/漏斗/设置）
│   └── static/                   # 浅色主题 + 可收起侧边栏
├── tools/
│   ├── hardware_test.py          # 硬件连接测试
│   └── integration_test_hw.py    # 联调测试
├── tests/                        # 测试用例
├── logs/                         # 日志和报警图像
└── non_mainline/                 # 非主线内容统一归档
    ├── history/
    │   ├── scripts/legacy/       # 旧 main.py 双进程架构（已归档）
    │   └── archive/              # 更早期实验/迁移/标定历史
    ├── documentation/
    │   ├── docs/                 # 方案、部署、审查文档
    │   └── handoff/              # AI 交接与台账
    └── artifacts/
        └── root_cache/           # 根目录缓存/覆盖率等运行产物
```

## 开发模式 vs 生产模式

| 特性 | DEV | PROD |
|------|-----|------|
| 相机 | MockCamera（噪声+时间戳） | BaslerCamera（GigE 实机） |
| PLC | MockPLC（内存模拟） | AllenBradleyPLC（Ethernet/IP） |
| 分辨率 | 1024x768 | 1600x1200 |
| 帧率 | 1 FPS | 5.5 FPS |
| ECC 配准 | 禁用 | 启用 |

切换方式：环境变量 `COAL_ENV=DEV` 或命令行 `--dev`

## 测试

```powershell
pytest tests/ -v
# 当前: 137 passed, 9 skipped, 0 failed（含 30 项归档模块测试）
```

## 报警图像归档（V3.0.12+）

每个采集窗口结束后，`CaptureWindowController` 按策略挑选**一张代表帧**入队，
`ArchiveWorker` 独立线程异步落盘；`ArchiveJanitor` 按 retention_days + 磁盘水位定时清理。

- 报警帧（`ALARM_*`）永不丢失：队列满时淘汰非报警帧
- 故障帧（`FAULT_*`）：`fault_code != 0` 的非报警窗口
- 正常帧（`NORMAL_*`）：可通过 `archive_save_normal` 关闭
- 清理策略：超过 `archive_retention_days` 按日期删，磁盘超过 `archive_disk_warning_pct` 降级删最旧 10%
- 观测端点：`GET /api/archive/stats`（queue_depth / saved / dropped / io_errors / p50_p95 / disk_usage）

配置示例（`config/config_prod.yaml`）：

```yaml
archive_enable: true
archive_queue_max: 200
archive_retention_days: 30
archive_disk_warning_pct: 85.0
archive_save_normal: true
archive_jpeg_quality: 85
archive_janitor_interval_s: 3600
```

30 漏斗规模下每天约 43200 张 × 200KB ≈ 8.6GB，30 天 retention ≈ 258GB。

## 相机 I/O 线缆（Hirose 6-pin）

| 线色 | 功能 | 当前状态 |
|------|------|----------|
| 白 | Line1 输入（外部触发） | 暂不接，预留硬触发 |
| 绿 | Line1 GND | 暂不接 |
| 黄 | Line2 输出（曝光信号，可触发补光灯） | 暂不接 |
| 蓝 | Line2 GND | 暂不接 |
| 裸线 | 屏蔽接地 | 建议接 PE 地排 |

## 安全原则

**宁可漏报，不可误报**。误报积煤 → 翻车机急停 → 煤车倾倒卡死设备。

- 画质自检失败（全黑/过曝/模糊）→ `FaultCode=3`, `CanTip=False`（不允许翻车）
- 检测结果不确定（`has_coal=None`）→ `CanTip=False`（安全优先）
- 心跳 500ms 必须递增，PLC 校验视觉系统存活
- 故障必须报（相机掉线、PLC 断连、画质异常、低置信度）
- 视觉停用时 PLC 强制允许翻车
- 视觉启停 API 需管理员鉴权
- PLC 读写加锁（`_io_lock`），心跳值递增加锁（`_heartbeat_value_lock`）
- 相机连续 30 次采集失败自动释放线程
- ECC 配准漂移量超限自动重置
- PLC 重连时加 10 秒超时，防止 TCP 挂死

## 已修复的安全漏洞

| 编号 | 严重度 | 问题 | 修复 |
|------|--------|------|------|
| C1 | CRITICAL | DetectionResult 继承 dict 但底层为空，len()/keys() 静默返回空 | 移除 dict 继承，纯 dataclass + dict-like 方法 |
| C2 | CRITICAL | 心跳值两个线程同时递增无锁 | 新增 _heartbeat_value_lock |
| C3 | CRITICAL | coal_present=None 时 not None=True → 允许翻车 | 改为 coal_present is False 严格判断 |
| C4 | CRITICAL | detect_frame 和 camera.grab 共用线程池导致饥饿 | 三个独立线程池 + 超时保护 |
| C5 | CRITICAL | 画质失败时 DeviceDetector 丢失 quality_ok → 允许翻车 | quality_ok/fault_code 传递 |
| C6 | CRITICAL | 没人看页面时不执行 PLC 触发检测 | 后台 worker 线程独立于 WebSocket |
| H1-H13 | HIGH | 13 项（详见整改文档） | 全部修复 |
| M1-M8 | MEDIUM | 8 项（详见整改文档） | 全部修复 |

共修复 **65 个安全漏洞**（经 15 轮 CODEX 审查迭代）。

包括：pypylon 枚举冲突崩溃根因、PLC 断连边沿通知、ID 白名单校验、
相机自动重连（永不放弃）、故障事件 9 条路径闭环、
PLC 断网后采集停滞修复（State 重置+异步重试）等。

详细清单见 `non_mainline/documentation/docs/整改记录与已知限制.md`。
CODEX 审查提示词见 `non_mainline/documentation/docs/CODEX_FINAL_REVIEW.md`。

## 稳定性验证

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 连续运行 | 每 2 小时崩溃 | 49.4 小时无崩溃 |
| 内存 | 持续增长 | 177-198MB 稳定 |
| 线程 | 可能泄漏 | 63-69 稳定 |
| 采集周期 | — | 2710+ 次正常循环 |
| 测试 | — | 137 passed, 9 skipped, 0 failed |

## 文档

| 文档 | 位置 |
|------|------|
| 项目规范 | CLAUDE.md |
| 项目分析报告 | non_mainline/documentation/docs/project_analysis_report_v3.0.docx |
| 部署报告 | non_mainline/documentation/docs/翻车机积煤检测系统_部署报告_V3.0.docx |
| 整改记录 | non_mainline/documentation/docs/整改记录与已知限制.md |
| PLC 点位表 | non_mainline/documentation/docs/PLC点位表配置.md |
| CODEX 审查 | non_mainline/documentation/docs/CODEX_FINAL_REVIEW.md |

## License

Proprietary - 内部项目

