# CLAUDE.md - 翻车机积煤检测系统 V3.0 开发规范

> 本文件是 Claude Code 的项目上下文文件，定义了项目的技术规范、开发流程和代码标准。
> Claude Code 会在每次会话开始时自动读取此文件。

---

## 一、项目概述

### 1.1 项目信息

| 项目名称 | 翻车机积煤检测系统 |
|----------|-------------------|
| 版本 | V3.0 |
| 类型 | 工业视觉检测系统 |
| 环境 | 煤矿翻车机房（防爆、高粉尘） |
| 核心目标 | 实时检测格栅积煤，端到端延迟 < 100ms |

### 1.2 技术栈

```
语言：Python 3.10+
视觉：OpenCV 4.8+ (可选 CUDA)
通信：pycomm3 (AB PLC)
Web：FastAPI + WebSocket
日志：loguru
配置：PyYAML
```

### 1.3 核心架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    系统架构（生产模式）                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   海康相机 ──→ 双缓冲 ──→ 检测算法 ──→ 综合判定 ──→ PLC输出     │
│      ↓          ↓          ↓           ↓           ↓           │
│   GigE采集   SharedMem   ECC+CLAHE   三级置信度   心跳+结果     │
│                         格栅计数                                │
│                         面积检测                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、目录结构

```
coal_detection/
├── CLAUDE.md               # 本文件 - 项目规范
├── main.py                 # 主程序入口
├── requirements.txt        # 依赖清单
├── pytest.ini              # pytest 配置
├── start_dev.bat           # 开发模式启动脚本
├── start_web.bat           # Web 界面启动脚本
├── start_web_local.bat     # 本地 Web 启动脚本
│
├── config/
│   ├── __init__.py
│   ├── config.py           # 配置类（DEV_MODE 开关）
│   ├── config_dev.yaml     # 开发环境配置
│   ├── config_prod.yaml    # 生产环境配置
│   ├── grid_baseline.yaml  # 格栅 ROI 标定数据（占位模板）
│   ├── grid_baseline.json  # 格栅标定数据（实际标定，140 cells）
│   ├── grid_manual.yaml    # GridEditorToolKit 产出（10×13，125 ROIs）
│   ├── grid_precise.yaml   # 精确标定（10×13，125 ROIs）
│   ├── grid_corrected.yaml # 修正版（12×9，108 ROIs）
│   ├── grid_dev_corrected.yaml  # 开发分辨率修正版
│   ├── single_grid_config.yaml  # 单格栅检测参数
│   └── archive/            # 归档的旧配置文件
│
├── core/                   # 核心引擎（生产模式）
│   ├── __init__.py
│   ├── double_buffer.py    # 双缓冲共享内存
│   ├── frame_state.py      # 跨进程状态管理
│   ├── capture_process.py  # 采集进程
│   └── detect_process.py   # 检测进程
│
├── drivers/                # 硬件驱动
│   ├── __init__.py
│   ├── factory.py          # 驱动工厂
│   ├── mock_drivers.py     # Mock 驱动（开发用）
│   └── hikvision_camera.py # 海康相机驱动（占位，待接入 SDK）
│
├── algo/                   # 检测算法
│   ├── __init__.py
│   ├── detector.py         # 主检测器（含 ECC 配准逻辑）
│   ├── grid_counter.py     # 格栅计数
│   ├── coal_detector.py    # 积煤面积检测
│   ├── judge.py            # 综合判定
│   ├── device_detector.py  # 设备级检测（多格栅）
│   └── single_grid_detector.py  # 单格栅检测
│
├── plc/                    # PLC 通信
│   ├── __init__.py
│   └── allen_bradley.py    # AB PLC 实现（含心跳逻辑）
│
├── web/                    # Web 界面
│   ├── __init__.py
│   ├── app.py              # FastAPI 主应用
│   ├── common.py           # 共享工具（静态挂载、模板等）
│   ├── device_app.py       # 设备级检测页面
│   ├── single_grid_app.py  # 单格栅检测页面
│   ├── static/             # 静态资源（自动创建）
│   └── templates/          # 页面模板（内联 CSS/JS）
│
├── tools/                  # 工具脚本（格栅标定、检测调试等）
│   ├── generate_test_images.py
│   ├── grid_calibrator.py
│   ├── performance_profiler.py
│   └── ...                 # 其他标定/检测工具
│
├── scripts/                # 归档的调试/启动脚本
│   ├── fixes/              # 配置修复脚本
│   ├── grid_editors/       # 格栅编辑器启动脚本
│   ├── tests/              # 根目录迁移的测试脚本
│   └── web_variants/       # Web 启动变体
│
├── tests/                  # 测试
│   ├── __init__.py
│   ├── test_detector.py    # 算法单元测试
│   ├── test_integration.py # 集成测试
│   ├── test_performance.py # 性能测试
│   ├── test_config_env.py  # 配置环境测试
│   ├── test_web_routes_contract.py  # Web API 契约测试
│   ├── test_web_common.py  # Web 工具测试
│   └── mock_data/          # 测试图片
│       ├── clean/
│       ├── coal_light/
│       ├── coal_heavy/
│       └── edge_cases/
│
├── GridEditorToolKit/      # 格栅编辑器工具包
│
├── handoff/                # AI 交接文档
│
├── logs/                   # 日志目录
│   └── images/             # 报警图像存档（~74000 张，21GB）
│
└── docs/                   # 文档
    ├── 开发详细方案.md
    └── ...                 # 方案文档、使用指南等
```

---

## 三、开发模式（DEV_MODE）

### 3.1 虚实分离架构

项目支持**开发模式**和**生产模式**无缝切换：

```python
# 模式切换方式（优先级从高到低）：
# 1. 命令行参数 --dev
# 2. 环境变量 COAL_ENV=DEV
# 3. 配置文件中的 DEV_MODE
# 4. 默认值 False（生产模式，安全起见）
```

### 3.2 模式对比

| 特性 | 开发模式 (DEV) | 生产模式 (PROD) |
|------|----------------|-----------------|
| 相机 | MockCamera | HikvisionCamera |
| PLC | MockPLC | AllenBradleyPLC |
| 分辨率 | 1024×768 | 3072×2048 |
| 帧率 | 1 FPS | 10 FPS |
| ECC 配准 | 禁用 | 启用 |
| CUDA | 禁用 | 启用 |
| 双缓冲 | 禁用 | 启用 |
| 进程模式 | 单进程 | 多进程 |

### 3.3 环境变量配置

```powershell
# Windows 开发环境
set COAL_ENV=DEV

# Linux 生产环境（不设置或设为 PROD）
export COAL_ENV=PROD
```

### 3.4 Mock 驱动特性

MockCamera 会自动添加：
- **高斯噪声**：模拟相机传感器底噪
- **时间戳水印**：让每帧像素不同
- **随机抖动**：模拟翻车机震动
- **故障注入**：模拟掉线（1% 概率）

---

## 四、检测算法规范

### 4.1 处理流程

```
原始帧 → 质量自检 → ECC配准 → CLAHE增强 → 双因素检测 → 综合判定 → 多帧投票
                                              ↓
                                    ┌─────────┴─────────┐
                                    ↓                   ↓
                              格栅孔计数           积煤面积检测
                              (结构特征)           (颜色特征)
```

### 4.2 双因素检测

| 因素 | 方法 | 输出 |
|------|------|------|
| **格栅孔计数** | 二值化 + 轮廓面积 | 格栅可见率 (0~1) |
| **积煤面积** | HSV 分割 + 掩码统计 | 覆盖率 (0~1) |

### 4.3 三级置信度判定

```python
def judge(grid_ratio: float, coverage: float) -> tuple:
    """
    综合判定逻辑
    
    Returns:
        (是否有煤, 置信度, 置信度分数, 是否需人工确认)
    """
    # ═══ 高置信度：两个指标一致 ═══
    if grid_ratio < 0.70 and coverage > 0.15:
        return True, "HIGH", 0.95, False
    
    if grid_ratio > 0.95 and coverage < 0.03:
        return False, "HIGH", 0.95, False
    
    # ═══ 中置信度：单指标明显异常 ═══
    if grid_ratio < 0.60:
        return True, "MEDIUM", 0.80, False
    
    if coverage > 0.25:
        return True, "MEDIUM", 0.75, False
    
    # ═══ 低置信度：指标矛盾，需人工确认 ═══
    if grid_ratio < 0.80 and coverage < 0.05:
        # 可能是阴影或异物遮挡
        return None, "LOW", 0.50, True
    
    if grid_ratio > 0.90 and coverage > 0.12:
        # 可能是锈斑或污渍
        return None, "LOW", 0.50, True
    
    # ═══ 预警区间 ═══
    if grid_ratio < 0.90 or coverage > 0.05:
        return False, "WARNING", 0.60, False
    
    return False, "NORMAL", 0.90, False
```

### 4.4 多帧投票

```python
# 投票窗口：5 帧
# 阈值：3 帧一致才输出结果
# 作用：抗单帧噪声，提高稳定性
```

---

## 五、安全规范（★ 关键）

### 5.1 安全红线

> ⚠️ **本系统直接关联翻车机安全连锁，任何改动都要考虑"如果这里出错，翻车机会怎样"**

| 红线 | 说明 |
|------|------|
| **宁可漏报，不可误报** | 误报积煤 → 翻车机急停 → 煤车倾倒卡死设备 |
| **采集永不停** | 采集进程永不阻塞，跟不上就跳帧 |
| **心跳必须有** | 500ms 心跳递增，PLC 校验视觉系统存活 |
| **故障必须报** | 相机掉线、PLC 断连、低置信度都要输出故障码 |

### 5.2 故障码定义

```python
FAULT_NONE = 0           # 正常
FAULT_CAMERA_FAIL = 1    # 相机故障
FAULT_PLC_COMM = 2       # PLC 通信故障
FAULT_QUALITY_FAIL = 3   # 画面质量问题
FAULT_LOW_CONFIDENCE = 4 # 低置信度，需人工确认
```

### 5.3 PLC 点位表

| 点位名称 | 类型 | 方向 | 说明 |
|----------|------|------|------|
| Detection.CoalPresent | BOOL | 写 | 积煤检测结果 |
| Detection.Confidence | STRING | 写 | 置信度等级 |
| Detection.NeedManualConfirm | BOOL | 写 | 需人工确认 |
| Detection.VisionHeartbeat | INT | 写 | 心跳递增值 |
| Detection.FaultCode | INT | 写 | 故障码 |
| Detection.SystemReady | BOOL | 写 | 系统就绪 |

---

## 六、性能规范（★ 关键）

### 6.1 硬性指标

| 指标 | 要求 | 说明 |
|------|------|------|
| 单帧处理延迟 | **≤ 80ms** | 从读取帧到输出结果 |
| 端到端延迟 | **≤ 150ms** | 从采集到 PLC 写入完成 |
| 跳帧率 | **≤ 10%** | 超过说明算法需要裁剪 |
| 心跳间隔 | **500ms ± 50ms** | PLC 校验用 |

### 6.2 禁止的慢操作

```python
# ❌ 绝对禁止
cv2.erode(img, np.ones((15, 15)))      # 大核形态学操作
cv2.findTransformECC(..., iterations=50)  # ECC迭代次数>15
process(original_4k_image)              # 直接处理原始大图
with open("log.txt", "a") as f: ...     # 主循环中磁盘I/O
result = plc.read(tag)                  # 同步等待PLC响应
clahe = cv2.createCLAHE(...)            # 每帧重建对象

# ✅ 正确做法
cv2.erode(img, np.ones((5, 5)))         # 小核
cv2.findTransformECC(..., iterations=5)  # 减少迭代
process(cv2.resize(img, (960, 540)))    # 先降采样
logger.info(...)                        # 用loguru异步日志
plc_queue.put_nowait(result)            # 异步写入
self.clahe.apply(l)                     # 复用预创建对象
```

### 6.3 必须的优化

```python
class OptimizedDetector:
    def __init__(self):
        # 1. 预创建对象（只创建一次）
        self.clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        
        # 2. 预加载基准图像
        self.reference_small = cv2.resize(reference, (320, 240))
        self.reference_gray = cv2.cvtColor(self.reference_small, cv2.COLOR_BGR2GRAY)
        
        # 3. 预计算掩码
        self.grid_mask = self._create_grid_mask()
        
        # 4. ECC参数（减少迭代）
        self.ecc_criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 5, 0.01)
        
        # 5. 预热（让JIT/缓存生效）
        self._warmup()
```

### 6.4 ECC 降采样配准

```python
def fast_ecc_align(self, frame):
    """
    核心优化：小图算矩阵，大图应用
    耗时：从 30秒 → 15ms
    """
    # 1. 降采样（3072×2048 → 320×240）
    frame_small = cv2.resize(frame, (320, 240))
    frame_gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)
    
    # 2. 在小图上计算位移矩阵
    _, warp_matrix = cv2.findTransformECC(
        self.reference_gray, frame_gray,
        self.warp_matrix, cv2.MOTION_TRANSLATION, 
        self.ecc_criteria
    )
    
    # 3. ★ 关键：缩放平移量到原图尺寸
    warp_matrix[0, 2] *= (3072 / 320)  # scale_x
    warp_matrix[1, 2] *= (2048 / 240)  # scale_y
    
    # 4. 应用到大图
    return cv2.warpAffine(frame, warp_matrix, (3072, 2048))
```

### 6.5 时间分配预算

| 步骤 | 目标耗时 | 优化方法 |
|------|----------|----------|
| 图像拷贝 | 10-15ms | SharedMemory + copy |
| 画面自检 | 2-3ms | 简单统计量 |
| ECC配准 | 15-20ms | 降采样 + 5次迭代 |
| CLAHE增强 | 5-10ms | 预创建对象复用 |
| 格栅计数 | 5-8ms | 向量化 + 预计算掩码 |
| 积煤面积 | 3-5ms | numpy向量化 |
| 综合判定 | <1ms | 简单条件判断 |
| PLC写入 | 10ms | 异步队列 |
| **总计** | **~60ms** | ✅ |

---

## 七、双缓冲架构（生产模式）

### 7.1 架构原理

```
采集进程（永不阻塞）          检测进程（跟不上就跳帧）
    ↓                              ↓
写 Buffer A ←─┐              读 Buffer B（上一帧）
    ↓         │切换指针           ↓
写完，切换 ───┘              处理完成
    ↓                              ↓
写 Buffer B                   读 Buffer A（最新帧）
```

### 7.2 工业铁律

> **采集永不停。宁可检测进程漏掉几帧（跳帧），也不能让采集进程卡顿。**
> **最新的图像永远比旧图更有价值。**

### 7.3 核心代码模式

```python
# 采集进程：永不阻塞
def capture_loop():
    while True:
        idx = state.begin_write()          # 切换buffer
        np.copyto(buffer[idx], frame)       # 写入
        state.end_write(idx)               # 标记完成
        # 不等待检测进程！

# 检测进程：能跑多快跑多快
def detect_loop():
    while True:
        idx, frame_id = state.get_latest()
        if frame_id == last_id:
            continue  # 没新帧，跳过
        frame = buffer[idx].copy()         # 拷贝一份
        result = detector.detect(frame)
        # 跟不上就自动跳帧
```

---

## 八、代码规范

### 8.1 命名规范

```python
# 类名：PascalCase
class CoalDetector:
    pass

# 函数/方法：snake_case
def detect_coal_coverage():
    pass

# 常量：UPPER_SNAKE_CASE
MAX_ITERATIONS = 10

# 私有方法：前缀下划线
def _internal_process():
    pass
```

### 8.2 类型注解

```python
# 所有公开函数必须有类型注解
def detect(self, frame: np.ndarray, frame_id: int = 0) -> DetectionResult:
    """
    主检测入口
    
    Args:
        frame: BGR 图像，shape=(H, W, 3)
        frame_id: 帧号
        
    Returns:
        DetectionResult 检测结果
    """
    pass
```

### 8.3 文档字符串

```python
class CoalDetector:
    """
    积煤检测器
    
    功能：
    1. ECC 配准
    2. CLAHE 增强
    3. 格栅计数
    4. 积煤面积检测
    5. 综合判定
    
    Usage:
        detector = CoalDetector(config)
        result = detector.detect(frame)
    """
    pass
```

### 8.4 错误处理

```python
# 采集失败：重试 + 降级
try:
    frame = camera.grab()
except ConnectionError as e:
    logger.error(f"相机采集失败: {e}")
    if hasattr(camera, 'reconnect'):
        camera.reconnect()
    continue

# ECC 失败：降级处理
try:
    aligned = self._align_ecc(frame)
except cv2.error:
    logger.warning("ECC 配准失败，使用原图")
    self.warp_matrix = np.eye(2, 3, dtype=np.float32)
    aligned = frame
```

---

## 九、测试规范

### 9.1 测试分类

| 类型 | 路径 | 说明 |
|------|------|------|
| 单元测试 | `tests/test_*.py` | 算法模块测试 |
| 集成测试 | `tests/test_integration.py` | 端到端流程测试 |
| 性能测试 | `tests/test_performance.py` | 延迟和吞吐量测试 |

### 9.2 测试图片要求

```
tests/mock_data/
├── clean/           # 无积煤（正常状态）
├── coal_light/      # 薄层积煤
├── coal_heavy/      # 严重积煤
└── edge_cases/      # 边界情况
    ├── shadow.jpg       # 阴影
    ├── rust.jpg         # 锈斑
    ├── dust.jpg         # 积灰
    ├── dark.jpg         # 光线不足
    └── overexposed.jpg  # 过曝
```

### 9.3 测试命令

```bash
# 运行所有测试
pytest tests/ -v

# 运行性能测试
pytest tests/test_performance.py -v

# 生成覆盖率报告
pytest tests/ --cov=algo --cov-report=html
```

---

## 十、Git 规范

### 10.1 分支策略

```
main          # 生产分支，只接受 PR
├── develop   # 开发分支
├── feature/* # 功能分支
├── bugfix/*  # 修复分支
└── release/* # 发布分支
```

### 10.2 提交信息格式

```
<type>(<scope>): <subject>

feat(algo): 添加 ECC 降采样优化
fix(plc): 修复心跳超时判断
perf(core): 优化双缓冲切换逻辑
docs(readme): 更新部署说明
test(detector): 添加边界情况测试
```

### 10.3 代码审查清单

- [ ] 类型注解完整
- [ ] 文档字符串完整
- [ ] 错误处理完整
- [ ] 没有阻塞操作
- [ ] 没有硬编码阈值
- [ ] 通过所有测试

---

## 十一、部署规范

### 11.1 开发环境部署

```powershell
# 1. 设置环境变量
set COAL_ENV=DEV

# 2. 安装依赖
pip install -r requirements.txt

# 3. 生成测试图片
python tools/generate_test_images.py

# 4. 运行
python main.py --dev
```

### 11.2 生产环境部署

```bash
# 1. 不设置 COAL_ENV（默认生产模式）

# 2. 安装生产依赖
pip install -r requirements.txt
pip install pycomm3  # PLC 通信

# 3. 安装海康 SDK
# 参考海康官方文档

# 4. 配置
cp config/config_prod.yaml config/config.yaml
# 编辑 PLC IP、相机 IP 等

# 5. 运行
python main.py --config config/config.yaml
```

### 11.3 健康检查

```bash
# 检查点位
# 1. 心跳递增正常（500ms）
# 2. 检测延迟 < 100ms
# 3. 跳帧率 < 10%
# 4. 无故障码
```

---

## 十二、常见问题

### Q1: 检测耗时过长（> 100ms）

**排查步骤**：
1. 检查是否启用了 CUDA
2. 检查 ECC 迭代次数是否过多
3. 检查是否在处理原图而非降采样图
4. 检查是否有阻塞的磁盘 I/O

### Q2: 误报率高

**排查步骤**：
1. 检查阈值设置是否合理
2. 检查是否有锈斑干扰（需启用锈色过滤）
3. 检查光照是否稳定
4. 增加多帧投票窗口

### Q3: 相机采集失败

**排查步骤**：
1. 检查网线连接
2. 检查 IP 配置
3. 检查海康 SDK 是否正确安装
4. 检查是否有其他程序占用相机

### Q4: PLC 心跳超时

**排查步骤**：
1. 检查网络连接
2. 检查 PLC IP 配置
3. 检查检测进程是否卡死
4. 检查 CPU 占用是否过高

---

## 十三、联系方式

- 技术支持：[内部联系方式]
- 文档更新：提交 PR 到 docs/ 目录
- Bug 反馈：提交 Issue

---

**最后提醒**：本系统直接关联翻车机安全连锁，任何改动都要考虑"如果这里出错，翻车机会怎样"。宁可漏报（人工确认），不可误报（积煤被翻倒卡住设备）。
