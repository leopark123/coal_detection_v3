# CODEX 审查提示词 V13 — 翻车机积煤检测系统 V3.0

> 第十三轮审查。新增左侧可收起导航栏。请验证实现质量和安全性。

---

## 审查提示词

```
你是工业安全系统代码审查员。第十三轮审查，聚焦新增的侧边栏导航。

本轮新增 3 个文件 + 修改 4 个模板，实现全局可收起侧边栏导航。

═══════════════════════════════════════════
一、新增文件审查
═══════════════════════════════════════════

### 1. web/static/css/sidebar.css
- 验证：.sidebar 收起 48px，展开 220px，transition 动画
- 验证：.sidebar-text 收起时 opacity:0，展开时 opacity:1
- 验证：.app-layout margin-left 跟随侧边栏宽度
- 验证：响应式 768px 断点处理（移动端收起+遮罩）
- 验证：tooltip 只在收起模式显示（:not(.expanded)::after）
- 验证：z-index 层级是否合理（sidebar:200 vs header:100）

### 2. web/static/js/sidebar.js
- XSS 安全：escSidebar() 是否对所有动态内容转义
- XSS 安全：设备树中 m.id/f.id 是否直接拼进 onclick/href？
  如果是 → 检查 ID 是否经过后端 _validate_id 白名单校验
- localStorage 使用是否安全（sidebar_expanded 键）
- fetch('/api/overview') 失败时是否安全降级（.catch）
- fetch('/api/health') 失败时是否安全降级
- setInterval 5秒刷新是否合理（不会刷屏日志）
- 设备树 innerHTML 插入是否有 XSS 风险
- 当前页高亮逻辑是否覆盖所有 4 个页面路由

### 3. web/templates/partials/sidebar.html
- Jinja2 include 是否正确
- CSS/JS 引用路径是否正确
- HTML 结构是否语义化
- onclick 绑定是否安全

═══════════════════════════════════════════
二、模板修改审查
═══════════════════════════════════════════

### 4. 4 个模板的 include + app-layout 包裹
- 文件：overview.html, machine_detail.html, funnel_detail.html, settings.html
- 验证：{% include 'partials/sidebar.html' %} 在 <body> 之后
- 验证：<div class="app-layout"> 包裹所有原有内容
- 验证：</div> 在 </body> 之前正确闭合
- 验证：原有功能不受影响（WebSocket、检测、故障面板等）

### 5. settings.html 特殊处理
- settings.html 原本有自己的设备树侧边栏（300px）
- 验证：全局侧边栏和设置页自有侧边栏是否冲突
- 验证：CSS 类名是否冲突（两个都叫 .sidebar？）

═══════════════════════════════════════════
三、功能验证
═══════════════════════════════════════════

### 6. 收起/展开
- 收起：48px 宽，只显示图标
- 展开：220px 宽，显示图标+文字+设备树
- 点击 ☰ 切换
- localStorage 记住状态

### 7. 设备树
- 从 /api/overview 加载翻车机→漏斗层级
- 翻车机名+PLC 状态点（绿/红）
- 漏斗名+相机状态点（绿/红/灰）
- 点击跳转到对应详情页
- 5 秒自动刷新

### 8. 当前页高亮
- / → 总览高亮
- /machine/* → 设备高亮 + 设备树自动展开
- /settings → 设置高亮
- 对应漏斗链接也高亮

### 9. 系统状态（底部）
- 运行时长
- 内存占用
- 状态点（绿=ok，红=degraded）

═══════════════════════════════════════════
四、安全回归
═══════════════════════════════════════════

### 10. 核心检测链路不受影响
- 后台 worker 仍独立运行
- PLC 通信不受 UI 变化影响
- WebSocket 推流不受影响
- can_tip 公式不变

### 11. API 安全
- /api/overview 和 /api/health 是只读接口，无鉴权（符合设计）
- 侧边栏不调用任何写操作 API

═══════════════════════════════════════════
输出格式
═══════════════════════════════════════════

对每项标注 PASS / FAIL / WARNING。

重点关注：
- 第 2 项 XSS 安全（设备树 innerHTML 中的 ID 拼接）
- 第 5 项 CSS 类名冲突（settings.html 两个 .sidebar）
```

---

## 新增文件清单

| 文件 | 行数 | 用途 |
|------|------|------|
| web/static/css/sidebar.css | ~160 | 侧边栏样式+动画+响应式 |
| web/static/js/sidebar.js | ~120 | 展开/收起+设备树+高亮+状态 |
| web/templates/partials/sidebar.html | ~40 | 侧边栏 HTML 片段 |

## 修改文件

| 文件 | 改动 |
|------|------|
| overview.html | +include +app-layout |
| machine_detail.html | +include +app-layout |
| funnel_detail.html | +include +app-layout |
| settings.html | +include +app-layout |

## 累计修复：58 项 + 侧边栏导航
