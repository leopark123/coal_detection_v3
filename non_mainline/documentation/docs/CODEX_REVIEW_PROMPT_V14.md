# CODEX 审查提示词 V14 — 翻车机积煤检测系统 V3.0

> 第十四轮审查。发现总览页"采集中"按钮点击后可能停止采集，需验证鉴权链路完整性。

---

## 审查提示词

```
你是工业安全系统代码审查员。第十四轮审查，聚焦视觉启停按钮的鉴权和前端行为。

背景：总览页每台翻车机卡片右下角有"● 采集中"/"○ 已停用"按钮，点击会调用
/api/machine/{id}/vision/disable 或 /api/machine/{id}/vision/enable。
这是安全关键操作——停用视觉采集后 PLC 强制 Allow_Tip=1（允许翻车），
等于绕过了积煤检测直接放行。

═══════════════════════════════════════════
一、后端鉴权验证
═══════════════════════════════════════════

1. **API 是否需要管理员鉴权？**
   - 文件：web/unified_app.py api_vision_enable 和 api_vision_disable
   - 验证：是否有 Depends(verify_admin) 或 x_admin_token 参数
   - 验证：verify_admin 的实现（web/admin_api.py）
   - 验证：不传 token 时是否返回 401

2. **verify_admin 的默认值行为**
   - 文件：web/admin_api.py verify_admin()
   - 代码：x_admin_token: Optional[str] = Header(None)
   - 验证：不传 X-Admin-Token header 时，x_admin_token=None
   - 验证：None != ADMIN_TOKEN → 应该 raise HTTPException(401)
   - 验证：这个 401 是否确实会阻止操作执行

═══════════════════════════════════════════
二、前端按钮行为
═══════════════════════════════════════════

3. **toggleVision 函数是否传了 admin token？**
   - 文件：web/templates/overview.html toggleVision()
   - 验证：fetch 调用是否包含 headers: { 'X-Admin-Token': token }
   - 如果没有 → 后端会返回 401
   - 前端是否正确处理 401？

4. **401 响应的前端处理**
   - toggleVision 的 .then(r => r.json()) 对 401 会怎样？
   - FastAPI 401 返回 {"detail": "未授权"}
   - 前端检查 d.error，但 401 的字段是 d.detail
   - 验证：是否会静默吞掉 401 错误（不提示用户）

5. **按钮状态是否会被错误翻转？**
   - 按钮显示状态从哪里读取？（WebSocket overview 数据的 vision_enabled）
   - 如果 API 返回 401，后端 vision_enabled 不变
   - 下次 WebSocket 推送（2秒后）是否会恢复按钮状态
   - 是否有瞬间"看起来停用了但实际没停"的误导

6. **machine_detail.html 的启停按钮**
   - 文件：web/templates/machine_detail.html
   - 也有类似的 toggleVision 按钮
   - 是否也没传 token？行为是否一致？

═══════════════════════════════════════════
三、安全影响评估
═══════════════════════════════════════════

7. **如果不传 token 确实能停用采集**
   - 任何能访问 Web 页面的人都能停用视觉检测
   - 停用后 PLC Allow_Tip 强制=1 → 翻车机不受视觉系统保护
   - 这是否是安全漏洞？

8. **如果 401 确实拦住了**
   - 按钮点击无效，用户没有提示 → UX 问题
   - 应该提示"需要管理员权限"或隐藏按钮

9. **state_manager.set_vision_enabled 的 PLC 写入**
   - 停用时会写 Vision_Enable=False + Vision_CanTip=True
   - 如果 PLC 写入失败会回滚内存状态
   - 验证：401 时是否根本不会走到 set_vision_enabled

═══════════════════════════════════════════
四、修复建议评估
═══════════════════════════════════════════

10. **方案 A：前端传 token**
    - 从 sessionStorage 获取 token（设置页登录后存储）
    - 没有 token 时提示"请先在设置页登录"
    - 优点：安全，符合现有鉴权体系
    - 缺点：每次要先登录设置页

11. **方案 B：按钮需要二次确认密码**
    - 点击按钮 → 弹出密码输入框 → 验证后执行
    - 优点：不依赖 sessionStorage，一次性鉴权
    - 缺点：每次都要输密码

12. **方案 C：去掉鉴权，但加二次确认**
    - 去掉 Depends(verify_admin)
    - 保留 confirm 对话框（已有）
    - 优点：操作简便
    - 缺点：任何人都能操作

13. **方案 D：按钮只在登录后显示**
    - 未登录时不渲染启停按钮
    - 优点：简洁
    - 缺点：总览页无法快速操作

═══════════════════════════════════════════
五、安全连锁回归
═══════════════════════════════════════════

14. can_tip 公式不变
15. Vision_Enable=False 时 PLC Allow_Tip 强制=1（设计如此）
16. 心跳、检测、重连机制不受影响

═══════════════════════════════════════════
输出格式
═══════════════════════════════════════════

对每项标注 PASS / FAIL / WARNING。

最终回答：
1. 当前代码是否存在"未鉴权就能停用采集"的安全漏洞？
2. 如果是漏洞，推荐哪种修复方案（A/B/C/D）？
3. 如果不是漏洞（401 确实拦住了），前端 UX 应该怎么改？
```

---

## 涉及文件

| 文件 | 关键代码 |
|------|----------|
| web/unified_app.py:467,479 | api_vision_enable/disable + Depends(verify_admin) |
| web/admin_api.py:50 | verify_admin(x_admin_token=Header(None)) |
| web/templates/overview.html:511 | toggleVision() fetch 无 token |
| web/templates/machine_detail.html | toggleVision() 类似实现 |
| web/state_manager.py:456 | set_vision_enabled() PLC 写入+回滚 |

## 累计修复：58 项 + 待确认本项
