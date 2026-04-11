"""生成项目最终全面总结 Word 文档（中文）"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn


def setup(doc):
    s = doc.styles['Normal']
    s.font.name = 'Microsoft YaHei'
    s.font.size = Pt(10.5)
    s.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
    for i in range(1, 4):
        h = doc.styles[f'Heading {i}']
        h.font.name = 'Microsoft YaHei'
        h.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
        h.font.color.rgb = RGBColor(0x1A, 0x3C, 0x6E)


def T(doc, headers, rows):
    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
    t.style = 'Light Grid Accent 1'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]
        c.text = h
        for r in c.paragraphs[0].runs:
            r.bold = True
            r.font.size = Pt(9)
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            t.rows[ri + 1].cells[ci].text = str(val)
    doc.add_paragraph()


def B(doc, text):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = True
    return p


def R(doc, text):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = True
    r.font.color.rgb = RGBColor(0xC0, 0, 0)
    return p


def main():
    doc = Document()
    setup(doc)

    # ════════════════════════ 封面 ════════════════════════
    for _ in range(4):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run('翻车机积煤检测系统 V3.0')
    r.font.size = Pt(28)
    r.bold = True
    r.font.color.rgb = RGBColor(0x1A, 0x3C, 0x6E)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run('项目最终总结报告')
    r.font.size = Pt(20)
    r.font.color.rgb = RGBColor(0x44, 0x72, 0xC4)

    doc.add_paragraph()
    info = [
        '编写日期: 2026-04-09',
        '项目类型: 工业视觉安全连锁系统',
        '适用场景: 煤矿翻车机房格栅积煤实时检测',
        '用途: 上线评审 / 技术交接 / 项目复盘',
    ]
    for line in info:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run(line).font.size = Pt(11)

    doc.add_page_break()

    # ════════════════════════ 目录 ════════════════════════
    doc.add_heading('目录', 1)
    toc = [
        '一、项目概述', '二、系统架构', '三、硬件环境', '四、PLC 配置',
        '五、检测算法', '六、采集时序', '七、安全连锁设计',
        '八、Web 管理界面', '九、故障报警系统', '十、异常恢复机制',
        '十一、代码质量', '十二、稳定性验证', '十三、安全漏洞修复记录',
        '十四、已知限制', '十五、部署运维', '十六、下一步路线图',
        '十七、经验教训', '十八、项目评价',
    ]
    for item in toc:
        doc.add_paragraph(item, style='List Number')
    doc.add_page_break()

    # ════════════════════════ 一、项目概述 ════════════════════════
    doc.add_heading('一、项目概述', 1)
    doc.add_paragraph(
        '本系统是一套基于计算机视觉的工业安全连锁系统，部署于煤矿翻车机房。'
        '通过工业相机实时拍摄格栅画面，自动检测积煤覆盖情况，将结果写入 PLC，'
        '与翻车机安全连锁联动，控制翻车机的允许/禁止翻转。'
    )
    R(doc, '核心原则：宁可漏报，不可误报。误报积煤→翻车机急停→煤车倾倒卡死设备。')

    doc.add_heading('1.1 核心指标', 2)
    T(doc, ['指标', '数值'],
      [['Python 代码', '42 个文件, 12,245 行'],
       ['HTML 模板', '6 个文件, 2,205 行'],
       ['CSS + JS', '245 + 76 行'],
       ['测试用例', '119 个函数, 116 passed'],
       ['安全修复', '55 项（10 轮 CODEX 审查）'],
       ['连续运行', '49.4+ 小时无崩溃'],
       ['PLC 集成', '19 标签 + 10 Rung 梯形图'],
       ['采集周期', '103,000+ 帧检测'],
       ['文档', '10+ 份技术文档 + 10 份 CODEX 提示词']])

    doc.add_page_break()

    # ════════════════════════ 二、系统架构 ════════════════════════
    doc.add_heading('二、系统架构', 1)
    doc.add_heading('2.1 三级层次', 2)
    T(doc, ['层级', '组件', '数量', '说明'],
      [['服务器', 'StateManager', '1', '中央状态管理器，管理所有翻车机'],
       ['翻车机', 'MachineState + PLC', 'N 台', '每台独立 PLC，可动态增减'],
       ['漏斗', 'FunnelState + Camera + Detector', 'M/台', '每漏斗独立相机和检测器']])

    doc.add_heading('2.2 线程模型', 2)
    T(doc, ['线程/池', 'Workers', '职责', '超时'],
      [['主线程(asyncio)', '1', 'FastAPI 事件循环', '—'],
       ['_grab_executor', '4', 'camera.grab()', '10 秒'],
       ['_detect_executor', '8', 'detect_frame()', '10 秒'],
       ['bg-detect-*', '每漏斗 1', '后台检测 worker（独立于 WebSocket）', '—'],
       ['plc-heartbeat', '每 PLC 1', '500ms 心跳递增', '2 秒锁超时'],
       ['PLC _io_lock', '—', '所有 PLC 读写互斥', '5 秒']])

    doc.add_heading('2.3 核心设计决策', 2)
    T(doc, ['决策', '原因', '效果'],
      [['后台 worker 独立于 WebSocket', '没人看页面时也要检测', '24×7 检测不间断'],
       ['PLC 控制采集时序', '时间判断应由 PLC 完成', '职责清晰，可靠性高'],
       ['三个独立线程池', '避免互相阻塞（C4 根因）', '49h 无崩溃'],
       ['_ever_connected 隔离', '不存在的相机不枚举 GigE', '消除 pypylon 冲突'],
       ['YOLO + CV 双模式预留', '深度学习 + 传统方法互补', '未来准确性提升']])

    doc.add_page_break()

    # ════════════════════════ 三、硬件环境 ════════════════════════
    doc.add_heading('三、硬件环境', 1)
    T(doc, ['设备', '型号', 'IP', '说明'],
      [['工控机', 'Windows 10 Pro', '192.168.1.10', '运行检测服务'],
       ['工业相机', 'Basler acA1600-60gm', '192.168.1.12', 'Mono8 灰度, 1600x1200, GigE'],
       ['PLC', 'AB 1769-L16ER/B B1B', '192.168.1.19', 'CompactLogix, 固件 36.11'],
       ['交换机', '千兆工业交换机', '—', '相机/PLC/工控机互联'],
       ['补光灯', '未安装', '—', '阻塞检测准确性验证']])

    doc.add_heading('3.1 相机参数', 2)
    T(doc, ['参数', '值'],
      [['传感器', 'e2v EV76C570 CMOS, 1/1.8 英寸'],
       ['分辨率', '1600x1200 (200 万像素)'],
       ['帧率', '5.5 FPS (GigE 带宽限制)'],
       ['像素格式', 'Mono8 → BGR (驱动层转换)'],
       ['GigE 心跳超时', '3000ms (崩溃后 3 秒释放)'],
       ['帧率节点', 'AcquisitionFrameRateAbs (旧版 SFNC)']])

    doc.add_heading('3.2 I/O 线缆 (Hirose 6-pin)', 2)
    T(doc, ['线色', 'Pin', '功能', '状态'],
      [['已接', 'Pin1+6', '电源 +12V/GND', '已接通'],
       ['白', 'Pin2', 'Line1 输入(触发)', '预留'],
       ['绿', 'Pin5', 'I/O GND', '预留'],
       ['黄', 'Pin4', 'Line2 输出(曝光)', '可接补光灯'],
       ['蓝', 'Pin3', 'Line2 GND', '预留'],
       ['裸线', 'Shield', '屏蔽接地', '建议接 PE']])

    doc.add_page_break()

    # ════════════════════════ 四、PLC 配置 ════════════════════════
    doc.add_heading('四、PLC 配置（19 个标签 + 10 个 Rung）', 1)
    doc.add_heading('4.1 服务器写入标签（7 个）', 2)
    T(doc, ['标签', '类型', '说明'],
      [['Vision_CanTip', 'BOOL', '安全连锁核心：无积煤=True'],
       ['Vision_FaultCode', 'DINT', '0 正常/1 相机/2 PLC/3 画质/4 需人工'],
       ['Vision_ResultValid', 'BOOL', '结果可信（高/中置信度且无故障）'],
       ['IPC_Heartbeat', 'DINT', '心跳递增（500ms, 0~65535 循环）'],
       ['IPC_Online', 'BOOL', '视觉系统在线'],
       ['Vision_Enable', 'BOOL', '采集启用（停用时 Allow_Tip 强制=1）'],
       ['Vision_CaptureState', 'DINT', '0 空闲/1 采集中/2 完成']])

    doc.add_heading('4.2 PLC 写入标签（2 个）', 2)
    T(doc, ['标签', '类型', '说明'],
      [['PLC_CaptureCmd', 'DINT', '采集指令（0 空闲/1 采集）'],
       ['Tipper_InPosition', 'BOOL', '翻车机回位信号']])

    doc.add_heading('4.3 梯形图逻辑（10 个 Rung）', 2)
    rungs = [
        'Rung 0: 心跳检测 NEQ→MOV+RES',
        'Rung 1: 超时计时 TON 2000ms',
        'Rung 2: 存活判断 Online+XIO Timer.DN→Alive',
        'Rung 3: 故障灯 XIO Alive→Fault_Light',
        'Rung 4: 允许翻车(并联) Enable=0→Allow; Alive+CanTip+Valid+Fault=0→Allow',
        'Rung 5: 人工确认 Fault=4→Manual_Light',
        'Rung 6: 延时触发 Tipper+Enable+State=0→TON',
        'Rung 7: 采集指令 Delay.DN→MOV 1→Cmd',
        'Rung 8: 完成复位 State=2→MOV 0→Cmd+RES',
        'Rung 9: 回位消失 XIO Tipper→MOV 0→Cmd+RES',
    ]
    for r in rungs:
        doc.add_paragraph(r, style='List Number')

    doc.add_page_break()

    # ════════════════════════ 五、检测算法 ════════════════════════
    doc.add_heading('五、检测算法', 1)
    doc.add_paragraph('处理流程：原始帧 → 画质智能自检 → ECC 配准(320x240) → CLAHE 增强 → 双因素检测 → 综合判定')

    doc.add_heading('5.1 画质智能自检', 2)
    doc.add_paragraph('不使用全局亮度一刀切，分区评估 + 对比度 + 自适应模糊阈值：')
    T(doc, ['检查项', '方法', '拒绝条件'],
      [['绝对黑', '全局 mean + std', 'mean<5 且 std<3'],
       ['过曝', '全局 mean', 'mean>240'],
       ['格栅区域暗', 'ROI mean + std', 'roi_mean<8 且 roi_std<5'],
       ['模糊', 'Laplacian + 自适应阈值', 'laplacian<阈值 且 std<8']])

    doc.add_heading('5.2 双因素检测', 2)
    T(doc, ['因素', '方法', '输出'],
      [['格栅孔计数', '二值化 + 轮廓面积', '格栅可见率 (0~1)'],
       ['积煤面积', 'HSV 分割 + 掩码统计', '覆盖率 (0~1)']])

    doc.add_heading('5.3 三级置信度', 2)
    T(doc, ['置信度', '条件', '动作'],
      [['HIGH', '两指标一致', '直接输出'],
       ['MEDIUM', '单指标明显异常', '直接输出'],
       ['LOW', '指标矛盾', '需人工确认(FaultCode=4)']])

    doc.add_heading('5.4 性能', 2)
    T(doc, ['指标', '实测'],
      [['单帧处理', '~51ms'],
       ['帧间隔', '~270ms (3.7 FPS)'],
       ['每窗口帧数', '61-64 帧']])

    doc.add_page_break()

    # ════════════════════════ 六、采集时序 ════════════════════════
    doc.add_heading('六、采集时序（PLC 控制）', 1)
    doc.add_paragraph('采集时序完全由 PLC 控制，服务器只负责检测：')
    steps = [
        '翻车机翻转完成，回到原位（Tipper_InPosition=1）',
        'PLC 延时等待（可调，当前 10 秒）',
        'PLC 发出采集指令（PLC_CaptureCmd=1）',
        '服务器写 CaptureState=1，后台 worker 开始连续采集',
        '每帧：画质自检 → 检测 → 喂入窗口控制器',
        'PLC 停止指令（回位消失或采集完成）→ 窗口投票判定',
        '投票：故障帧排除，有效帧 >50% 才可信',
        '结果写 PLC（CanTip / FaultCode / ResultValid）',
        'PLC 根据结果决定 Allow_Tip',
    ]
    for s in steps:
        doc.add_paragraph(s, style='List Number')

    doc.add_heading('6.1 窗口内投票规则', 2)
    T(doc, ['场景', '处理'],
      [['故障帧(画质不合格)', '排除，不参与投票'],
       ['有效帧 <50%', '整个窗口不可信(LOW, fault_code)'],
       ['有效帧投票', 'alarm_ratio >= 0.6 → 报警'],
       ['零帧超时(60秒)', 'fail-safe 写 PLC(fault_code=3)']])

    doc.add_page_break()

    # ════════════════════════ 七、安全连锁设计 ════════════════════════
    doc.add_heading('七、安全连锁设计', 1)
    doc.add_heading('7.1 Allow_Tip 完整链路', 2)
    T(doc, ['步骤', '组件', '安全保护'],
      [['1.抓帧', 'BaslerCamera', '未匹配 IP 拒绝连接'],
       ['2.画质检', 'detector._check_quality', '分区+对比度+自适应'],
       ['3.检测', 'device_detector', '异常 fail-safe(fault_code=3)'],
       ['4.投票', 'capture_window', '故障帧排除+零帧 fail-safe'],
       ['5.写PLC', 'allen_bradley', 'can_tip 三重条件'],
       ['6.PLC判', '梯形图 Rung4', 'Alive+CanTip+Valid+Fault=0'],
       ['7.停用', 'Vision_Enable=False', 'PLC 强制 Allow_Tip=1']])

    doc.add_heading('7.2 核心公式', 2)
    doc.add_paragraph('can_tip = (coal_present is False) and (not need_manual) and (fault_code == 0)')
    doc.add_paragraph('result_valid = confidence in ("HIGH","MEDIUM") and (fault_code == 0) and (coal_present is not None)')
    doc.add_paragraph('Allow_Tip = Vision_Enable=0 OR (Alive AND CanTip AND Valid AND Fault=0)')
    doc.add_paragraph()
    B(doc, '任一条件不满足 → 禁止翻车。服务器判定 + PLC 梯形图双重保护。')

    doc.add_page_break()

    # ════════════════════════ 八、Web 管理界面 ════════════════════════
    doc.add_heading('八、Web 管理界面', 1)
    T(doc, ['页面', 'URL', '功能'],
      [['总览', '/', '翻车机卡片+视频缩略图+故障横幅+启停按钮'],
       ['翻车机详情', '/machine/{id}', '多路视频网格+PLC 状态'],
       ['漏斗详情', '/machine/{id}/funnel/{id}', '大图视频+检测叠加+格栅热力图'],
       ['管理设置', '/settings', '增删翻车机/漏斗+阈值调节（密码保护）'],
       ['健康检查', '/api/health', '内存/线程/PLC/相机状态(JSON)'],
       ['故障详情', '/api/faults/all', '全部故障+系统状态+事件日志']])

    doc.add_heading('8.1 UI 特性', 2)
    doc.add_paragraph('浅色简洁主题（白卡片+灰底+圆角）', style='List Bullet')
    doc.add_paragraph('视频缩略图嵌入总览卡片（每 3 秒刷新）', style='List Bullet')
    doc.add_paragraph('增量 DOM 更新（无闪烁）', style='List Bullet')
    doc.add_paragraph('故障横幅点击展开详情面板', style='List Bullet')
    doc.add_paragraph('WebSocket 自动重连（指数退避）', style='List Bullet')

    doc.add_page_break()

    # ════════════════════════ 九、故障报警系统 ════════════════════════
    doc.add_heading('九、故障报警系统', 1)
    doc.add_heading('9.1 故障信息展示', 2)
    doc.add_paragraph('总览页红色横幅显示当前故障摘要，点击展开详情面板：')
    T(doc, ['信息', '展示位置'],
      [['相机状态(connected/disconnected/not_available)', '故障卡片'],
       ['PLC 状态(online/offline)', '故障卡片'],
       ['具体错误信息', '故障卡片'],
       ['断开时长', '故障卡片'],
       ['重连次数和阶段(快速/慢速)', '故障卡片'],
       ['系统运行时长/内存/线程/采集帧数', '系统状态栏'],
       ['最近 20 条故障事件(时间+设备+消息)', '事件日志']])

    doc.add_heading('9.2 故障事件覆盖（9 条路径闭环）', 2)
    T(doc, ['事件', '类型', '记录位置'],
      [['相机断开', 'camera', 'state_manager._bg_detection_loop'],
       ['相机从未连接(IP不存在)', 'camera', '同上'],
       ['相机重连成功', 'camera_ok', '同上'],
       ['PLC 初始化成功', 'plc_ok', 'state_manager.initialize'],
       ['PLC 初始化失败', 'plc', '同上'],
       ['PLC 运行时断连', 'plc', 'allen_bradley._notify_disconnect→回调'],
       ['PLC 运行时重连', 'plc_ok', 'allen_bradley._notify_connect→回调'],
       ['PLC 动态新增成功', 'plc_ok', 'state_manager.add_machine'],
       ['PLC 动态新增失败', 'plc', '同上']])

    doc.add_page_break()

    # ════════════════════════ 十、异常恢复机制 ════════════════════════
    doc.add_heading('十、异常恢复机制', 1)
    T(doc, ['场景', '恢复方式', '恢复时间'],
      [['相机断电后上电', '自动重连(快速 5 次→慢速永不放弃)', '<30 秒'],
       ['更换同型号同 IP 相机', '自动连接(只匹配 IP)', '<30 秒'],
       ['PLC 网络中断', '心跳线程自动重连(指数退避)', '~6 秒'],
       ['工控机断电重启', '看门狗自动启动服务', '~10 秒'],
       ['服务崩溃', '看门狗 5 秒后重启', '~8 秒'],
       ['不存在的相机(IP 错误)', '不重连(不干扰其他相机)', '立即标记 not_available']])

    doc.add_heading('10.1 相机重连策略', 2)
    doc.add_paragraph('_ever_connected=True（曾连过）→ 快速 5 次(10秒) → 慢速(60秒)永不放弃')
    doc.add_paragraph('_ever_connected=False（从未连过）→ 不重连，状态 not_available，不干扰其他相机')

    doc.add_heading('10.2 PLC 边沿通知', 2)
    doc.add_paragraph('_notify_disconnect / _notify_connect 边沿触发，只在状态变化时回调一次')
    doc.add_paragraph('覆盖路径：write/read/check_connection/heartbeat 所有断连 + reconnect 成功')

    doc.add_page_break()

    # ════════════════════════ 十一、代码质量 ════════════════════════
    doc.add_heading('十一、代码质量', 1)
    doc.add_heading('11.1 代码统计', 2)
    T(doc, ['目录', '文件', '行数', '职责'],
      [['algo/', '7', '1,569', '检测算法'],
       ['core/', '6', '2,156', '采集控制+双缓冲'],
       ['drivers/', '4', '891', '相机+Mock 驱动'],
       ['plc/', '2', '690', 'PLC 通信'],
       ['web/', '8', '2,936', 'Web 应用+状态管理'],
       ['config/', '3', '460', '配置管理'],
       ['tools/', '7+', '1,663+', '运维/生成工具'],
       ['tests/', '11', '1,880', '测试'],
       ['合计', '42+', '12,245+', '—']])

    doc.add_heading('11.2 测试覆盖', 2)
    T(doc, ['类型', '文件数', '函数数'],
      [['算法单元', '1', '20'],
       ['集成测试', '1', '20'],
       ['性能测试', '1', '12'],
       ['Web 契约', '1', '3'],
       ['Web 通用', '1', '9'],
       ['配置加载', '2', '13'],
       ['状态管理', '1', '13'],
       ['管理 API', '1', '18'],
       ['统一路由', '1', '11'],
       ['合计', '10', '119 (116 passed)']])

    doc.add_heading('11.3 ID 安全校验', 2)
    doc.add_paragraph('所有 machine_id / funnel_id 在 YAML 加载和 API 创建时经过正则校验：^[A-Za-z0-9_-]+$')

    doc.add_page_break()

    # ════════════════════════ 十二、稳定性验证 ════════════════════════
    doc.add_heading('十二、稳定性验证', 1)
    T(doc, ['指标', '修复前', '修复后'],
      [['连续运行', '每 2 小时崩溃', '49.4+ 小时无崩溃'],
       ['内存', '持续增长', '174-214MB 稳定'],
       ['线程', '可能泄漏', '63-79 稳定'],
       ['采集周期', '—', '103,000+ 帧'],
       ['画面全黑判定', '允许翻车', 'FaultCode=3 禁止翻车'],
       ['相机释放', '等 30 秒', '等 3 秒(GigE 心跳)'],
       ['并发 grab', 'RuntimeException', 'WebSocket 不再 grab']])

    doc.add_heading('12.1 崩溃根因(已修复)', 2)
    doc.add_paragraph('5 个后台 worker 同时调 pypylon.EnumerateDevices() → GigE 全局协议冲突 → 连真实相机也找不到 → 所有 worker 进入重连循环 → 资源耗尽 → uvicorn 冻结')
    doc.add_paragraph('修复：_ever_connected=False 的漏斗不调 pypylon，只有曾连接过的才重连。')

    doc.add_page_break()

    # ════════════════════════ 十三、安全漏洞修复记录 ════════════════════════
    doc.add_heading('十三、安全漏洞修复记录（55 项）', 1)
    T(doc, ['轮次', '数量', '关键修复'],
      [['初始', '27', '6 CRITICAL + 13 HIGH + 8 MEDIUM'],
       ['R1 审查', '4', '相机回退/异常 fail-safe/锁超时/WS 超时'],
       ['R2 审查', '4', '零帧 fail-safe/总览 WS/atexit/heartbeat 废弃'],
       ['R3', '1', 'pypylon 枚举冲突（反复崩溃根因）'],
       ['R4', '1', '重连上限改永不放弃'],
       ['R5', '3', '横幅漏报/XSS/PLC 初始化事件'],
       ['R6', '3', 'ID 白名单/PLC 回调注册/MockPLC 接口'],
       ['R7', '4', '边沿触发/断连全路径通知/admin 400'],
       ['R8', '5', '预赋值修复/异常通知补全/校验 400'],
       ['R9', '3', 'PLC 运行时事件闭环'],
       ['合计', '55', '10 轮 CODEX 审查迭代']])

    doc.add_page_break()

    # ════════════════════════ 十四、已知限制 ════════════════════════
    doc.add_heading('十四、已知限制（10 条）', 1)
    T(doc, ['编号', '限制', '影响', '改进时间'],
      [['L1', '采集控制器 per-funnel 但 PLC per-machine', '多相机争抢标签', '接第 2 台相机前'],
       ['L2', '配置变更非原子', '保存失败内存已变', 'V3.1'],
       ['L3', '运行时 add 不区分 ImportError', '极罕见', 'V3.1'],
       ['L4', '启动中途资源残留', 'OS 回收', 'V3.1'],
       ['L5', 'Token 无过期', '泄露长期有效', 'V3.2'],
       ['L6', 'WebSocket 无鉴权', '内网可看视频', 'V3.2'],
       ['L7', '报警不持久化', '重启丢失', 'V3.2(SQLite)'],
       ['L8', 'images 无自动清理', '磁盘满', 'V3.1'],
       ['L9', 'PLC 被挤掉不恢复', '需重启', '正常不出现'],
       ['L10', '单进程 5 秒空窗', '看门狗重启', 'PLC 2 秒保护']])

    doc.add_page_break()

    # ════════════════════════ 十五、部署运维 ════════════════════════
    doc.add_heading('十五、部署运维', 1)
    doc.add_heading('15.1 部署步骤（15 步）', 2)
    deploy = [
        '安装 Python 3.10+ 和依赖', '安装 Basler Pylon SDK',
        '复制项目到 D:\\coal_detection_project', '配置 devices.yaml',
        '设置管理员密码(ADMIN_PASSWORD)', '测试硬件(hardware_test.py)',
        'PLC 编程(Studio 5000, 10 Rung)', '联调测试(integration_test_hw.py)',
        '安装补光灯', '拍基准图(reference.jpg)', '标定格栅 ROI',
        '调检测阈值', '安装开机自启(install_autostart.bat)',
        '启动服务(start_production.bat)', '启动监控(start_monitor.bat)',
    ]
    for s in deploy:
        doc.add_paragraph(s, style='List Number')

    doc.add_heading('15.2 运维工具', 2)
    T(doc, ['工具', '功能'],
      [['start_production.bat', '看门狗：崩溃后 5 秒自动重启'],
       ['install_autostart.bat', 'Windows 开机自启'],
       ['start_monitor.bat', '系统监控（内存/线程/PLC/采集）'],
       ['tools/hardware_test.py', '硬件连接测试'],
       ['tools/integration_test_hw.py', '联调测试'],
       ['tools/system_monitor.py', '长时间稳定性监控'],
       ['/api/health', '健康检查 API'],
       ['/api/faults/all', '故障详情 API']])

    doc.add_heading('15.3 故障排查', 2)
    T(doc, ['故障', '排查'],
      [['相机连不上', 'ping IP + 等 3 秒 GigE 超时'],
       ['PLC 连不上', 'ping IP + 检查 RSLinx'],
       ['画面全黑', '检查补光灯 + 调曝光'],
       ['误报率高', '调 GRID_VISIBLE_THRESHOLD'],
       ['服务崩溃', '查 unified_*.log + 运行 monitor'],
       ['心跳超时', '检查网线 + reconnect 日志']])

    doc.add_page_break()

    # ════════════════════════ 十六、路线图 ════════════════════════
    doc.add_heading('十六、下一步路线图', 1)
    T(doc, ['阶段', '时间', '内容', '前置条件'],
      [['Phase 0', '现在', '补光灯采购安装', '—'],
       ['Phase 1', '灯到后 1-2 周', '标定+调参+真实测试', '补光灯到位'],
       ['Phase 2', '调参后 1 周', '并行验证(只记录不联锁)', '准确率达标'],
       ['Phase 3', '验证通过', '正式上线 7x24', '误报率<1%'],
       ['Phase 4', '上线 1 月后', '接第 2 台相机+L1 改进', '稳定运行'],
       ['Phase 5', '3 月后', '积累数据+YOLO 训练', '500+ 标注图'],
       ['Phase 6', 'YOLO 达标', 'YOLO+CV 双模式融合', 'GPU(Jetson)'],
       ['Phase 7', '6 月后', '分布式边缘全面替换', '方案 C 验证']])

    doc.add_page_break()

    # ════════════════════════ 十七、经验教训 ════════════════════════
    doc.add_heading('十七、经验教训', 1)
    doc.add_heading('17.1 做对的事', 2)
    T(doc, ['事项', '效果'],
      [['安全优先贯穿始终', '宁可漏报不可误报，55 项修复'],
       ['10 轮 CODEX 审查', '每轮发现→修复→验证，累计 55 项'],
       ['49h 实测验证', '不是理论分析，是真实运行数据'],
       ['PLC 梯形图同步设计', '服务器+PLC 双重安全保护'],
       ['整改文档完整记录', '每个漏洞有编号、修复方案、日期']])

    doc.add_heading('17.2 踩过的坑', 2)
    T(doc, ['坑', '代价', '教训'],
      [['相机型号 660gm vs 60gm', '全项目 grep 替换', '确认型号后立即更新文档'],
       ['GigE 心跳默认 10 秒', '重启等 30 秒', '一开始就设 3 秒'],
       ['画面全黑允许翻车', 'CRITICAL 漏洞', '质量失败必须设 fault_code'],
       ['没人看页面不检测', 'CRITICAL 漏洞', '检测必须独立于展示层'],
       ['pypylon 枚举冲突', '反复崩溃', '不存在的 IP 不枚举'],
       ['_was_connected 预赋值', '回调被抑制', '边沿触发由方法内部管理']])

    doc.add_page_break()

    # ════════════════════════ 十八、项目评价 ════════════════════════
    doc.add_heading('十八、项目评价', 1)
    T(doc, ['维度', '评分', '说明'],
      [['架构设计', '9/10', '三级层次+配置驱动+后台 worker+PLC 触发'],
       ['安全可靠', '9/10', '55 项修复+三重保护+故障帧过滤+边沿通知'],
       ['代码质量', '8/10', '116 测试+ID 校验+整改文档'],
       ['运行稳定', '9/10', '49h 无崩溃+看门狗+自动重连'],
       ['UI 体验', '8/10', '浅色主题+视频缩略图+故障面板'],
       ['文档完整', '9/10', '10+ 份文档+10 份 CODEX 提示词'],
       ['生产就绪', '7/10', '补光灯+标定+调参后可达 9/10']])

    doc.add_paragraph()
    B(doc, '最终结论：软件系统已具备工业部署条件（55 项安全漏洞已修复，49h 稳定运行验证），'
       '等补光灯到位后完成标定调参即可正式上线。')

    # Save
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'docs', 'final_summary_v3.0.docx')
    doc.save(out)
    print(f'OK: {out}')
    print(f'Size: {os.path.getsize(out)} bytes')


if __name__ == '__main__':
    main()
