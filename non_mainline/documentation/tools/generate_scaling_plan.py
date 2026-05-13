"""
生成 30 漏斗扩展方案 Word 文档

输出：docs/翻车机积煤检测系统_30漏斗扩展方案_V1.0.docx
"""
from pathlib import Path
from docx import Document
from docx.shared import Pt, Cm, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsmap
from docx.oxml import OxmlElement


# ========== 工具函数 ==========

def set_cell_bg(cell, color_hex):
    """设置表格单元格背景色"""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:fill'), color_hex)
    shd.set(qn('w:val'), 'clear')
    tc_pr.append(shd)


def set_cell_border(cell, **kwargs):
    """设置单元格边框"""
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = OxmlElement('w:tcBorders')
    for border_name in ('top', 'left', 'bottom', 'right'):
        border = OxmlElement(f'w:{border_name}')
        border.set(qn('w:val'), 'single')
        border.set(qn('w:sz'), '4')
        border.set(qn('w:color'), '888888')
        tc_borders.append(border)
    tc_pr.append(tc_borders)


def add_heading_styled(doc, text, level=1, color=None):
    """添加带样式的标题"""
    heading = doc.add_heading(text, level=level)
    for run in heading.runs:
        run.font.name = '微软雅黑'
        run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
        if color:
            run.font.color.rgb = color
    return heading


def add_paragraph_styled(doc, text, bold=False, size=11, color=None,
                         align=None, first_line_indent=None):
    """添加带样式的段落"""
    p = doc.add_paragraph()
    if align:
        p.alignment = align
    if first_line_indent:
        p.paragraph_format.first_line_indent = first_line_indent
    p.paragraph_format.space_after = Pt(6)

    run = p.add_run(text)
    run.font.name = '微软雅黑'
    run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = color
    return p


def add_bullet(doc, text, level=0):
    """添加项目符号段落"""
    p = doc.add_paragraph(text, style='List Bullet')
    p.paragraph_format.left_indent = Cm(0.75 + level * 0.75)
    for run in p.runs:
        run.font.name = '微软雅黑'
        run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
        run.font.size = Pt(11)
    return p


def add_numbered(doc, text, level=0):
    """添加编号段落"""
    p = doc.add_paragraph(text, style='List Number')
    p.paragraph_format.left_indent = Cm(0.75 + level * 0.75)
    for run in p.runs:
        run.font.name = '微软雅黑'
        run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
        run.font.size = Pt(11)
    return p


def add_table_styled(doc, headers, rows, col_widths=None, header_bg='2E75B6',
                     header_color='FFFFFF', alt_row_bg='F2F2F2'):
    """
    添加带样式的表格

    Args:
        headers: 表头列表
        rows: 数据行列表（每行是一个列表）
        col_widths: 列宽列表（Cm 单位）
        header_bg: 表头背景色
        header_color: 表头文字色
        alt_row_bg: 偶数行背景色（None 表示不交替）
    """
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = 'Light Grid Accent 1'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # 列宽
    if col_widths:
        for i, w in enumerate(col_widths):
            for cell in table.columns[i].cells:
                cell.width = Cm(w)

    # 表头
    hdr_cells = table.rows[0].cells
    for i, header in enumerate(headers):
        hdr_cells[i].text = ''
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(header)
        run.font.name = '微软雅黑'
        run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
        run.font.size = Pt(11)
        run.font.bold = True
        run.font.color.rgb = RGBColor.from_string(header_color)
        hdr_cells[i].vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        set_cell_bg(hdr_cells[i], header_bg)
        set_cell_border(hdr_cells[i])

    # 数据行
    for row_idx, row_data in enumerate(rows):
        row = table.add_row()
        is_alt = (row_idx % 2 == 1) and alt_row_bg is not None
        for i, cell_text in enumerate(row_data):
            cell = row.cells[i]
            cell.text = ''
            p = cell.paragraphs[0]
            run = p.add_run(str(cell_text))
            run.font.name = '微软雅黑'
            run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
            run.font.size = Pt(10.5)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            if is_alt:
                set_cell_bg(cell, alt_row_bg)
            set_cell_border(cell)

    return table


def add_code_block(doc, code):
    """添加代码块（等宽字体，灰色背景）"""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.5)
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(3)

    run = p.add_run(code)
    run.font.name = 'Consolas'
    run.font.size = Pt(9.5)
    run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

    # 背景色
    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:fill'), 'F5F5F5')
    pPr.append(shd)
    return p


def add_page_break(doc):
    doc.add_page_break()


def add_horizontal_line(doc):
    """添加水平分割线"""
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '6')
    bottom.set(qn('w:color'), '2E75B6')
    bottom.set(qn('w:space'), '1')
    pBdr.append(bottom)
    pPr.append(pBdr)


# ========== 文档生成 ==========

def generate_document():
    doc = Document()

    # 页面设置（A4）
    for section in doc.sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    # 默认字体
    style = doc.styles['Normal']
    style.font.name = '微软雅黑'
    style.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    style.font.size = Pt(11)

    # ============ 封面页 ============
    for _ in range(4):
        doc.add_paragraph()

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run('翻车机积煤检测系统')
    run.font.name = '微软雅黑'
    run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    run.font.size = Pt(28)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run('30 漏斗规模化扩展方案')
    run.font.name = '微软雅黑'
    run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    run.font.size = Pt(22)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x2E, 0x75, 0xB6)

    doc.add_paragraph()

    subsubtitle = doc.add_paragraph()
    subsubtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subsubtitle.add_run('—— 分布式边缘计算架构设计方案 ——')
    run.font.name = '微软雅黑'
    run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    run.font.size = Pt(14)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    for _ in range(6):
        doc.add_paragraph()

    # 封面信息表
    info_table = doc.add_table(rows=6, cols=2)
    info_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    info_data = [
        ('文档版本', 'V1.0'),
        ('文档类型', '技术方案'),
        ('密级', '内部'),
        ('当前系统版本', 'V3.0.11'),
        ('目标规模', '30 漏斗（6 台翻车机 × 5 漏斗）'),
        ('编制日期', '2026-04'),
    ]
    for i, (k, v) in enumerate(info_data):
        cells = info_table.rows[i].cells
        cells[0].text = ''
        cells[1].text = ''

        p0 = cells[0].paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r0 = p0.add_run(k + ':')
        r0.font.name = '微软雅黑'
        r0.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
        r0.font.size = Pt(11)
        r0.font.bold = True
        r0.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

        p1 = cells[1].paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r1 = p1.add_run(v)
        r1.font.name = '微软雅黑'
        r1.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
        r1.font.size = Pt(11)

        cells[0].width = Cm(5)
        cells[1].width = Cm(9)

    add_page_break(doc)

    # ============ 目录 ============
    add_heading_styled(doc, '目录', level=1, color=RGBColor(0x1F, 0x4E, 0x79))

    toc_items = [
        ('第一章  项目背景与需求', '3'),
        ('    1.1  当前系统概况', '3'),
        ('    1.2  扩展需求', '3'),
        ('    1.3  扩展目标', '4'),
        ('第二章  单机架构瓶颈分析', '5'),
        ('    2.1  网络带宽瓶颈', '5'),
        ('    2.2  CPU 与内存分析', '6'),
        ('    2.3  线程与连接数评估', '6'),
        ('    2.4  存储与 PLC 负载分析', '7'),
        ('    2.5  代码架构局限', '7'),
        ('第三章  三种扩展方案对比', '8'),
        ('    3.1  方案 A：单机 + 10GigE 高端服务器', '8'),
        ('    3.2  方案 B：分布式边缘计算（推荐）', '9'),
        ('    3.3  方案 C：Jetson 边缘 + YOLO AI', '10'),
        ('    3.4  方案综合对比', '11'),
        ('第四章  推荐方案详细设计', '12'),
        ('    4.1  总体架构', '12'),
        ('    4.2  硬件清单', '13'),
        ('    4.3  网络拓扑', '14'),
        ('    4.4  软件架构', '15'),
        ('    4.5  PLC 分配方案', '16'),
        ('第五章  中央聚合层开发方案', '17'),
        ('    5.1  技术栈', '17'),
        ('    5.2  API 接口设计', '17'),
        ('    5.3  数据流与同步策略', '18'),
        ('    5.4  开发工作量估算', '19'),
        ('第六章  分阶段实施路线图', '20'),
        ('    6.1  阶段一：单节点验证（0-3 月）', '20'),
        ('    6.2  阶段二：分布式部署（3-9 月）', '21'),
        ('    6.3  阶段三：AI 升级（9-18 月）', '22'),
        ('第七章  成本预算', '23'),
        ('    7.1  硬件成本', '23'),
        ('    7.2  软件开发成本', '23'),
        ('    7.3  运维成本（三年）', '24'),
        ('    7.4  总预算与 ROI', '24'),
        ('第八章  风险评估与应对', '25'),
        ('    8.1  技术风险', '25'),
        ('    8.2  项目风险', '26'),
        ('    8.3  运维风险', '26'),
        ('第九章  验收标准', '27'),
        ('    9.1  功能验收', '27'),
        ('    9.2  性能验收', '27'),
        ('    9.3  可靠性验收', '28'),
        ('附录 A  PLC 标签清单（30 漏斗）', '29'),
        ('附录 B  网络配置建议', '30'),
        ('附录 C  运维手册大纲', '31'),
    ]
    for item, page in toc_items:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run(item)
        run.font.name = '微软雅黑'
        run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
        run.font.size = Pt(11)

        # 使用制表符+点号实现目录效果
        p.paragraph_format.tab_stops.add_tab_stop(Cm(16), alignment=WD_ALIGN_PARAGRAPH.RIGHT)
        run2 = p.add_run(f'\t{page}')
        run2.font.name = '微软雅黑'
        run2.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
        run2.font.size = Pt(11)
        run2.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    add_page_break(doc)

    # ============ 第一章：项目背景与需求 ============
    add_heading_styled(doc, '第一章  项目背景与需求', level=1, color=RGBColor(0x1F, 0x4E, 0x79))

    add_heading_styled(doc, '1.1  当前系统概况', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    add_paragraph_styled(doc,
        '翻车机积煤检测系统 V3.0 是基于计算机视觉的工业级积煤检测解决方案，'
        '用于煤矿翻车机房格栅积煤的实时检测，与可编程逻辑控制器（PLC）实现安全连锁控制。'
        '系统采用"宁可漏报，不可误报"的安全原则，防止误报引发翻车机急停造成的煤车倾倒卡死事故。',
        first_line_indent=Cm(0.74))

    add_paragraph_styled(doc, '当前硬件环境：', bold=True)

    cur_hw = [
        ('工控机', 'Windows 10 Pro，IP: 192.168.1.10', 'Python 3.10+，单机运行'),
        ('相机', 'Basler acA1600-60gm', 'Mono8 灰度, 1600×1200, GigE，IP: 192.168.1.12'),
        ('PLC', 'AB 1769-L16ER/B', 'CompactLogix, Ethernet/IP，IP: 192.168.1.19'),
        ('网络', '千兆工业交换机', '相机/PLC/工控机互联'),
        ('采集频率', '5.5 FPS', 'GigE 带宽限制下的稳定帧率'),
        ('检测延迟', '< 150ms', '端到端（采集→检测→PLC写入）'),
    ]
    add_table_styled(doc,
        ['项目', '型号/规格', '说明'],
        cur_hw,
        col_widths=[3.0, 5.5, 7.5])

    add_paragraph_styled(doc, '当前软件架构：', bold=True)

    cur_sw = [
        ('核心检测', 'ECC 配准 + CLAHE 增强 + 双因素检测（格栅计数+积煤面积）'),
        ('判定逻辑', '三级置信度（HIGH/MEDIUM/LOW）+ 多帧投票'),
        ('采集模式', 'PLC 触发窗口采集（翻车机回位后定时采集）'),
        ('PLC 协议', '9 标签完整协议（心跳、故障码、结果、采集状态、翻车机位置）'),
        ('Web 管理', 'FastAPI + WebSocket，四级页面（总览/机器/漏斗/设置）'),
        ('安全连锁', 'can_tip 三重保护：coal_present+need_manual+fault_code'),
        ('连续运行', '验证稳定性 95 小时以上，内存稳定 180-210MB'),
    ]
    add_table_styled(doc,
        ['模块', '技术细节'],
        cur_sw,
        col_widths=[3.5, 12.5])

    add_heading_styled(doc, '1.2  扩展需求', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    add_paragraph_styled(doc,
        '随着煤矿生产规模扩大和自动化程度提升，单台翻车机单漏斗的检测范围已无法满足业务需求。'
        '煤矿现场预计部署以下规模：',
        first_line_indent=Cm(0.74))

    add_bullet(doc, '6 台翻车机（每台独立 PLC 控制）')
    add_bullet(doc, '每台翻车机配 5 个卸煤漏斗')
    add_bullet(doc, '总计 30 个漏斗、30 台相机需要同步检测')
    add_bullet(doc, '要求统一的中央监控与历史数据查询')
    add_bullet(doc, '未来可进一步扩展到 60+ 漏斗')

    add_heading_styled(doc, '1.3  扩展目标', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    goals = [
        ('功能完整性', '30 漏斗同时检测，检测精度和延迟与当前单漏斗一致'),
        ('可靠性', '单点故障不影响全局，MTBF ≥ 500 小时'),
        ('可扩展性', '支持平滑扩展到 60 漏斗（不需要重构架构）'),
        ('可维护性', '远程部署、集中监控、分布式调试能力'),
        ('成本控制', '硬件投资回报周期 ≤ 3 年'),
        ('兼容性', '复用当前代码 90% 以上，避免推倒重来'),
        ('安全性', '保留 V3.0 所有安全连锁逻辑（65 项审查修复全部保留）'),
    ]
    add_table_styled(doc,
        ['目标维度', '具体指标'],
        goals,
        col_widths=[4.0, 12.0])

    add_page_break(doc)

    # ============ 第二章：单机架构瓶颈分析 ============
    add_heading_styled(doc, '第二章  单机架构瓶颈分析', level=1, color=RGBColor(0x1F, 0x4E, 0x79))

    add_paragraph_styled(doc,
        '在决定扩展方案之前，首先必须定量分析当前单机架构的性能瓶颈，确认"单机能否承载 30 漏斗"的问题。'
        '以下从五个维度进行系统性评估：',
        first_line_indent=Cm(0.74))

    add_heading_styled(doc, '2.1  网络带宽瓶颈', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    add_paragraph_styled(doc, '单相机数据带宽计算：', bold=True)
    add_code_block(doc,
        '带宽 = 分辨率 × 像素深度 × 帧率\n'
        '     = 1600 × 1200 × 1 byte (Mono8) × 5.5 fps\n'
        '     = 10.56 MB/s\n\n'
        '30 相机总带宽 = 10.56 × 30 = 316.8 MB/s')

    add_paragraph_styled(doc, 'GigE 网络承载能力：', bold=True)

    bw_table = [
        ('GigE 理论带宽', '1000 Mbps', '125 MB/s'),
        ('GigE 实际可用', '~800 Mbps', '~100 MB/s（留 20% 余量防丢包）'),
        ('单相机带宽', '85 Mbps', '10.56 MB/s'),
        ('30 相机需求', '2534 Mbps', '316.8 MB/s'),
        ('超出比例', '3.2 倍', '严重过载，必然丢包'),
        ('理论上限', '~9 相机/GigE', '实测 6-7 相机最稳'),
    ]
    add_table_styled(doc,
        ['项目', '速率', '备注'],
        bw_table,
        col_widths=[4.0, 4.5, 7.5])

    add_paragraph_styled(doc,
        '结论：GigE 单端口最多支持 6-7 台相机稳定采集。30 漏斗需要至少 5 个独立 GigE 端口，'
        '或升级到 10GigE 网络（仅服务器端）。这是单机架构扩展到 30 漏斗的第一个硬性瓶颈。',
        color=RGBColor(0xC0, 0x00, 0x00), bold=True,
        first_line_indent=Cm(0.74))

    add_heading_styled(doc, '2.2  CPU 与内存分析', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    cpu_table = [
        ('ECC 配准', '15-20ms/帧', '降采样 320×240 + 5 次迭代'),
        ('CLAHE 增强', '5-10ms/帧', '复用预创建对象'),
        ('格栅计数', '5-8ms/帧', '二值化 + 轮廓面积'),
        ('积煤面积', '3-5ms/帧', 'HSV 分割向量化'),
        ('综合判定', '<1ms/帧', '简单条件判断'),
        ('单帧总耗时', '30-45ms', '单线程单核心'),
        ('单漏斗 CPU 占用', '15-20%', '按 5.5 FPS + 1 核心基准'),
        ('30 漏斗总 CPU', '450-600%', '需要 5-6 核心满载'),
    ]
    add_table_styled(doc,
        ['处理步骤', '耗时', '优化方式'],
        cpu_table,
        col_widths=[4.0, 3.0, 9.0])

    add_paragraph_styled(doc,
        'CPU 结论：现代 8-16 核心工控机在理论上可支持 30 漏斗的计算负载，但仍需考虑：',
        first_line_indent=Cm(0.74))
    add_bullet(doc, '线程切换开销（30+ 后台 worker）随并发度上升')
    add_bullet(doc, 'Web/WebSocket 并发消耗（最多 30 路视频推流）')
    add_bullet(doc, 'PLC 心跳与故障处理线程')
    add_bullet(doc, '最高峰值可能达到 80% 使用率，余量不足')

    add_paragraph_styled(doc, '内存分析：', bold=True)
    mem_table = [
        ('单漏斗 StateManager', '~30 MB', 'Detector、buffer、config'),
        ('30 漏斗总计', '~900 MB', '仅状态对象'),
        ('Web 缓存与队列', '~200 MB', 'WebSocket、日志、snapshot'),
        ('Python 运行时', '~200 MB', '解释器、库加载'),
        ('OS + 系统服务', '~2 GB', 'Windows 10 Pro 基础'),
        ('建议配置', '≥ 16 GB', '留 50% 余量防止 swap'),
    ]
    add_table_styled(doc,
        ['内存项目', '占用', '说明'],
        mem_table,
        col_widths=[4.5, 3.5, 8.0])

    add_heading_styled(doc, '2.3  线程与连接数评估', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    thread_table = [
        ('心跳线程', '1 个/PLC', '6 个 PLC = 6 个心跳线程'),
        ('检测 worker', '1 个/漏斗', '30 个漏斗 = 30 个 worker'),
        ('相机采集', '1 个/漏斗', '30 个采集线程'),
        ('检测执行池', '8 个', '共享全局池'),
        ('采集执行池', '4 个', '共享全局池'),
        ('WebSocket', '~30 个', '浏览器实时连接'),
        ('FastAPI 请求', '~10 个', 'HTTP API 并发处理'),
        ('总估算', '~100-150 个', '单 Python 进程承载'),
    ]
    add_table_styled(doc,
        ['线程类型', '数量', '说明'],
        thread_table,
        col_widths=[4.0, 3.0, 9.0])

    add_paragraph_styled(doc,
        '线程数约 100-150 个在 Windows 平台上属于可控范围，但需要注意：',
        first_line_indent=Cm(0.74))
    add_bullet(doc, 'GIL（Python 全局锁）导致 CPU 密集型检测任务无法真并发')
    add_bullet(doc, '单进程线程数过多增加上下文切换开销')
    add_bullet(doc, '一个线程崩溃可能影响整个进程（需要 watchdog）')

    add_heading_styled(doc, '2.4  存储与 PLC 负载分析', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    add_paragraph_styled(doc, '存储压力：', bold=True)
    add_paragraph_styled(doc,
        '当前单漏斗运行 1 个月约产生 74000 张报警图像，占用 21GB 磁盘空间。'
        '扩展到 30 漏斗后的存储增长：',
        first_line_indent=Cm(0.74))
    add_code_block(doc,
        '单漏斗：74000 张/月 × 300KB/张 ≈ 21 GB/月\n'
        '30 漏斗：21 × 30 = 630 GB/月\n'
        '年度：630 × 12 = 7.56 TB/年\n\n'
        '当前本机磁盘余量：663 GB\n'
        '运行时长：约 1 个月即满')

    add_paragraph_styled(doc, 'PLC 压力：', bold=True)
    add_paragraph_styled(doc,
        '每台翻车机独立 PLC（1769-L16ER），30 漏斗对应 6 台 PLC，每台 PLC 承载 5 漏斗：',
        first_line_indent=Cm(0.74))
    add_bullet(doc, '每台 PLC 点位数：9 个（心跳、故障、结果等） × 5 漏斗 = 45 个点位')
    add_bullet(doc, '心跳频率：500ms/次，即 2 次/秒')
    add_bullet(doc, 'PLC 扫描周期：约 10-50ms，压力可控')
    add_bullet(doc, '集中工控机并发访问 6 个 PLC，pycomm3 连接数可能成为瓶颈')

    add_heading_styled(doc, '2.5  代码架构局限', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    arch_limits = [
        ('StateManager 集中管理', '所有漏斗状态在一个进程内，单点失败影响全局'),
        ('PLC 连接共享', 'pycomm3 非线程安全，必须全局 _io_lock 串行化'),
        ('单进程部署', '无法利用多核真并行（GIL），无进程隔离'),
        ('Web 单入口', '所有 HTTP/WebSocket 流量集中在一个 FastAPI 实例'),
        ('配置耦合', 'devices.yaml 必须包含所有设备，无法分布式配置'),
        ('日志集中', '所有日志写入同一文件，30 漏斗后日志量过大'),
    ]
    add_table_styled(doc,
        ['架构限制', '影响'],
        arch_limits,
        col_widths=[5.0, 11.0])

    add_paragraph_styled(doc,
        '综合评估结论：当前单机架构在网络带宽、存储、架构弹性三个维度上均无法承载 30 漏斗的规模。'
        '必须改为分布式架构。',
        color=RGBColor(0xC0, 0x00, 0x00), bold=True,
        first_line_indent=Cm(0.74))

    add_page_break(doc)

    # ============ 第三章：三种扩展方案对比 ============
    add_heading_styled(doc, '第三章  三种扩展方案对比', level=1, color=RGBColor(0x1F, 0x4E, 0x79))

    add_paragraph_styled(doc,
        '基于第二章的瓶颈分析，本章提出三种可行的扩展方案，从硬件成本、软件改造、运维复杂度、'
        '扩展性等维度进行对比，为最终决策提供依据。',
        first_line_indent=Cm(0.74))

    add_heading_styled(doc, '3.1  方案 A：单机 + 10GigE 高端服务器', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    add_paragraph_styled(doc, '方案描述：', bold=True)
    add_paragraph_styled(doc,
        '升级单台工控机为高性能服务器（Xeon Gold 32 核 + 64GB 内存），'
        '配置 10GigE 网络，所有 30 台相机接入同一 10GigE 交换机。',
        first_line_indent=Cm(0.74))

    add_paragraph_styled(doc, '硬件配置：', bold=True)
    plan_a_hw = [
        ('CPU', 'Intel Xeon Gold 6338 32核', '约 3.5 万'),
        ('内存', '64GB DDR4 ECC', '约 0.5 万'),
        ('网络', '双 10GigE 网卡', '约 0.8 万'),
        ('存储', 'NVMe SSD 4TB + HDD 8TB', '约 0.6 万'),
        ('核心交换机', '48 口管理型 10GigE', '约 3 万'),
        ('服务器机架与 UPS', '机柜 + 2KVA UPS', '约 2 万'),
        ('相机与线缆', '30 × Basler + GigE 线缆', '约 9 万'),
        ('合计', '', '约 19.4 万'),
    ]
    add_table_styled(doc,
        ['硬件项', '规格', '单价'],
        plan_a_hw,
        col_widths=[4.5, 6.5, 5.0])

    add_paragraph_styled(doc, '优势：', bold=True)
    add_bullet(doc, '代码改动最小（仍为单机架构）')
    add_bullet(doc, '统一管理、统一部署')
    add_bullet(doc, '无分布式通信复杂度')

    add_paragraph_styled(doc, '劣势：', bold=True)
    add_bullet(doc, '❌ 单点故障：服务器宕机 30 漏斗全停')
    add_bullet(doc, '❌ 相机线缆长度受限（GigE 标准 100 米），现场布线困难')
    add_bullet(doc, '❌ GIL 限制：无法真正利用 32 核并行')
    add_bullet(doc, '❌ 扩展到 60 漏斗需再次升级硬件')
    add_bullet(doc, '⚠️ 一次性投资大，无法分期部署')

    add_paragraph_styled(doc, '适用场景：小规模（<20 漏斗）、布线条件好、对单点故障容忍度高的场景。',
                         color=RGBColor(0x66, 0x66, 0x66), first_line_indent=Cm(0.74))

    add_heading_styled(doc, '3.2  方案 B：分布式边缘计算（推荐）', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    add_paragraph_styled(doc, '方案描述：', bold=True)
    add_paragraph_styled(doc,
        '部署 6 台边缘工控机节点，每台负责 5 漏斗（对应 1 台翻车机 + 1 台 PLC）。'
        '配合 1 台中央服务器进行状态聚合、历史数据存储与统一 Web 展示。'
        '每个边缘节点独立运行，单点故障只影响 1/6 漏斗。',
        first_line_indent=Cm(0.74))

    add_paragraph_styled(doc, '拓扑结构：', bold=True)
    add_code_block(doc,
        '                    ┌─────────────────┐\n'
        '                    │  中央监控服务器  │\n'
        '                    │ （聚合/存储/Web）│\n'
        '                    └────────┬────────┘\n'
        '                             │ 千兆以太网\n'
        '         ┌──────┬──────┬─────┴────┬──────┬──────┐\n'
        '         │      │      │          │      │      │\n'
        '      ┌──┴──┐┌──┴──┐┌──┴──┐   ┌──┴──┐┌──┴──┐┌──┴──┐\n'
        '      │边缘1 ││边缘2 ││边缘3 │…  │边缘4 ││边缘5 ││边缘6 │\n'
        '      │5漏斗││5漏斗││5漏斗│   │5漏斗││5漏斗││5漏斗│\n'
        '      └──┬──┘└──┬──┘└──┬──┘   └──┬──┘└──┬──┘└──┬──┘\n'
        '      Cam×5 PLC Cam×5 PLC Cam×5 PLC ……')

    add_paragraph_styled(doc, '硬件配置：', bold=True)
    plan_b_hw = [
        ('边缘节点', '6 台', '工控机 i7-12700/16GB/1TB SSD', '1.5 万', '9 万'),
        ('中央服务器', '1 台', 'i7-12700/32GB/4TB SSD + 8TB HDD', '2 万', '2 万'),
        ('边缘交换机', '6 台', '8 口管理型 GigE 工业交换机', '0.5 万', '3 万'),
        ('核心交换机', '1 台', '24 口管理型 GigE 交换机', '1 万', '1 万'),
        ('相机与线缆', '30 套', 'Basler acA1600-60gm + 30m 线缆', '0.3 万', '9 万'),
        ('UPS 电源', '1 套', '3KVA 机架式 UPS', '1 万', '1 万'),
        ('机柜与辅材', '', '标准 42U 机柜 + 理线架', '0.5 万', '0.5 万'),
        ('合计', '', '', '', '约 25.5 万'),
    ]
    add_table_styled(doc,
        ['硬件项', '数量', '规格', '单价', '小计'],
        plan_b_hw,
        col_widths=[3.0, 1.5, 6.0, 2.5, 3.0])

    add_paragraph_styled(doc, '优势：', bold=True)
    add_bullet(doc, '✅ 单点故障隔离：1 节点挂掉只影响 5 漏斗，其余正常')
    add_bullet(doc, '✅ 代码高度复用：边缘节点 = 当前单机系统，只改配置')
    add_bullet(doc, '✅ 分期部署：可先部署 2-3 节点，稳定后再扩')
    add_bullet(doc, '✅ 相机线缆距离：每节点靠近相机安装，线缆短')
    add_bullet(doc, '✅ 扩展性好：30 → 60 只需加 6 个节点')
    add_bullet(doc, '✅ 运维灵活：单节点维护不影响其他')

    add_paragraph_styled(doc, '劣势：', bold=True)
    add_bullet(doc, '⚠️ 需要开发中央聚合层（约 2-3 周）')
    add_bullet(doc, '⚠️ 运维复杂度略高（管理 6 台 IPC）')
    add_bullet(doc, '⚠️ 节点间时钟同步要求（NTP）')

    add_paragraph_styled(doc, '适用场景：中大规模（10+ 漏斗）、对可用性要求高、希望平滑扩展的工业场景。',
                         color=RGBColor(0x00, 0x80, 0x00), bold=True, first_line_indent=Cm(0.74))

    add_heading_styled(doc, '3.3  方案 C：Jetson 边缘 + YOLO AI（未来架构）', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    add_paragraph_styled(doc, '方案描述：', bold=True)
    add_paragraph_styled(doc,
        '将边缘节点升级为 NVIDIA Jetson AGX Orin 嵌入式 GPU 平台，配合 YOLO v11 深度学习模型进行积煤检测。'
        'GPU 推理延迟 <20ms，检测精度远超传统 CV 算法，同时功耗更低、体积更小。',
        first_line_indent=Cm(0.74))

    plan_c_hw = [
        ('Jetson 边缘节点', '6 台', 'AGX Orin 64GB Dev Kit', '1.8 万', '10.8 万'),
        ('中央服务器', '1 台', 'i7/32GB + GPU 训练卡 RTX 4070', '3 万', '3 万'),
        ('交换机与辅助', '1 套', '同方案 B', '5 万', '5 万'),
        ('相机与线缆', '30 套', '同方案 B', '0.3 万', '9 万'),
        ('软件开发', '1 次', 'YOLO 模型训练 + 部署开发', '3 万', '3 万'),
        ('合计', '', '', '', '约 30.8 万'),
    ]
    add_table_styled(doc,
        ['硬件项', '数量', '规格', '单价', '小计'],
        plan_c_hw,
        col_widths=[3.0, 1.5, 6.0, 2.5, 3.0])

    add_paragraph_styled(doc, '优势：', bold=True)
    add_bullet(doc, '✅ 检测精度大幅提升（YOLO > 传统 CV）')
    add_bullet(doc, '✅ 抗干扰性好（光照/震动/背景变化）')
    add_bullet(doc, '✅ 嵌入式设备功耗低（<60W）')
    add_bullet(doc, '✅ 技术前沿，符合智能化趋势')

    add_paragraph_styled(doc, '劣势：', bold=True)
    add_bullet(doc, '❌ 开发周期长（3-6 个月：数据采集+标注+训练+部署）')
    add_bullet(doc, '❌ 需要大量标注数据（至少 5000+ 张积煤图像）')
    add_bullet(doc, '❌ 初期成本高')
    add_bullet(doc, '⚠️ YOLO 模型黑盒，不如传统 CV 易调试')

    add_paragraph_styled(doc,
        '建议：方案 C 作为长期演进目标，在方案 B 稳定运行、积累足够训练数据后逐步替换。',
        color=RGBColor(0x66, 0x66, 0x66), first_line_indent=Cm(0.74))

    add_heading_styled(doc, '3.4  方案综合对比', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    compare_table = [
        ('一次性投资', '19.4 万', '25.5 万', '30.8 万'),
        ('开发周期', '2 周', '4-6 周', '3-6 月'),
        ('代码复用率', '95%', '90%', '50%'),
        ('单点故障', '❌ 严重', '✅ 隔离', '✅ 隔离'),
        ('检测精度', '基准', '基准', '★★★★★'),
        ('扩展性', '一般', '优秀', '优秀'),
        ('运维难度', '低', '中', '中高'),
        ('功耗', '高', '中', '低'),
        ('技术风险', '低', '低', '中'),
        ('适用阶段', '短期过渡', '中期主力', '长期目标'),
    ]
    add_table_styled(doc,
        ['对比维度', '方案 A', '方案 B（推荐）', '方案 C（未来）'],
        compare_table,
        col_widths=[4.0, 4.0, 4.0, 4.0])

    add_paragraph_styled(doc,
        '最终建议：采用方案 B（分布式边缘计算）作为当前扩展的主力架构，'
        '方案 C 作为 12-18 个月后的技术演进方向。',
        bold=True, color=RGBColor(0x00, 0x80, 0x00),
        first_line_indent=Cm(0.74))

    add_page_break(doc)

    # ============ 第四章：推荐方案详细设计 ============
    add_heading_styled(doc, '第四章  推荐方案详细设计', level=1, color=RGBColor(0x1F, 0x4E, 0x79))

    add_heading_styled(doc, '4.1  总体架构', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    add_paragraph_styled(doc,
        '方案 B 采用三层架构：边缘层（边缘节点）+ 聚合层（中央服务器）+ 展示层（Web 前端）。',
        first_line_indent=Cm(0.74))

    arch_layers = [
        ('边缘层', '6 台 IPC', '本地检测、PLC 控制、采集窗口状态机、本地报警存储'),
        ('聚合层', '1 台中央服务器', '状态聚合、历史数据、告警推送、统一 API'),
        ('展示层', 'Web 前端', '统一总览页、30 漏斗卡片、远程管理、历史查询'),
    ]
    add_table_styled(doc,
        ['层级', '节点', '职责'],
        arch_layers,
        col_widths=[3.0, 4.0, 9.0])

    add_paragraph_styled(doc, '设计原则：', bold=True)
    add_numbered(doc, '边缘自治：每个边缘节点可独立运行，脱离中央服务器也能保证安全连锁')
    add_numbered(doc, '异步聚合：中央服务器通过 HTTP 轮询边缘节点，不阻塞边缘检测')
    add_numbered(doc, '统一 Web：用户访问中央 Web，看到所有 30 漏斗；也可直连边缘 Web 调试')
    add_numbered(doc, '无状态聚合：中央服务器不存储实时状态，只做数据中转和历史归档')
    add_numbered(doc, '故障降级：中央服务器宕机不影响边缘检测与 PLC 控制')

    add_heading_styled(doc, '4.2  硬件清单', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    add_paragraph_styled(doc, '边缘节点配置（每台，共 6 台）：', bold=True)
    edge_spec = [
        ('CPU', 'Intel Core i7-12700', '12 核 20 线程，3.6GHz 睿频 4.9GHz'),
        ('内存', '16GB DDR4', '双通道，预留扩展到 32GB'),
        ('存储', '1TB NVMe SSD', '500GB 系统 + 500GB 报警图像缓存'),
        ('网络', '双千兆网口', '1 口接相机网，1 口接管理网'),
        ('机箱', '无风扇工控机', '宽温 -20℃～60℃，防尘 IP65'),
        ('操作系统', 'Windows 10 IoT Enterprise LTSC', '长期稳定维护'),
    ]
    add_table_styled(doc,
        ['部件', '规格', '说明'],
        edge_spec,
        col_widths=[3.5, 5.5, 7.0])

    add_paragraph_styled(doc, '中央服务器配置：', bold=True)
    central_spec = [
        ('CPU', 'Intel Core i7-12700', '12 核 20 线程'),
        ('内存', '32GB DDR4 ECC', '错误校正防止数据损坏'),
        ('系统盘', '512GB NVMe SSD', '操作系统与应用'),
        ('数据盘', '4TB NVMe SSD + 8TB HDD', 'SSD 热数据 + HDD 冷备份'),
        ('网络', '千兆以太网', '接核心交换机'),
        ('UPS', '3KVA', '断电保护 30 分钟'),
        ('操作系统', 'Windows Server 2022 或 Ubuntu 22.04 LTS', '优先 Linux（稳定性）'),
    ]
    add_table_styled(doc,
        ['部件', '规格', '说明'],
        central_spec,
        col_widths=[3.5, 5.5, 7.0])

    add_paragraph_styled(doc, '网络设备：', bold=True)
    net_spec = [
        ('核心交换机 × 1', 'H3C S5120V3-28P-SI', '24 千兆电口 + 4 SFP 上联，VLAN 划分'),
        ('边缘交换机 × 6', 'H3C S1208P-PWR-HPWR', '8 口千兆 PoE，支持 VLAN'),
        ('路由器', '支持远程访问', '为运维留一条 VPN 通道'),
    ]
    add_table_styled(doc,
        ['设备', '型号建议', '说明'],
        net_spec,
        col_widths=[4.5, 5.5, 6.0])

    add_heading_styled(doc, '4.3  网络拓扑', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    add_paragraph_styled(doc, 'IP 地址规划：', bold=True)
    ip_table = [
        ('管理网段', '192.168.1.0/24', '中央服务器、边缘节点、运维管理'),
        ('机器-1 采集网段', '192.168.101.0/24', '边缘 1 节点及其 5 相机 + PLC'),
        ('机器-2 采集网段', '192.168.102.0/24', '边缘 2 节点及其 5 相机 + PLC'),
        ('机器-3 采集网段', '192.168.103.0/24', '边缘 3 节点及其 5 相机 + PLC'),
        ('机器-4 采集网段', '192.168.104.0/24', '边缘 4 节点及其 5 相机 + PLC'),
        ('机器-5 采集网段', '192.168.105.0/24', '边缘 5 节点及其 5 相机 + PLC'),
        ('机器-6 采集网段', '192.168.106.0/24', '边缘 6 节点及其 5 相机 + PLC'),
    ]
    add_table_styled(doc,
        ['网段', 'IP 范围', '用途'],
        ip_table,
        col_widths=[4.5, 5.0, 6.5])

    add_paragraph_styled(doc, '每个边缘节点内部 IP 分配：', bold=True)
    add_code_block(doc,
        '192.168.10X.1    边缘节点（管理+采集网关）\n'
        '192.168.10X.10   PLC (1769-L16ER)\n'
        '192.168.10X.12   相机 1\n'
        '192.168.10X.13   相机 2\n'
        '192.168.10X.14   相机 3\n'
        '192.168.10X.15   相机 4\n'
        '192.168.10X.16   相机 5\n'
        '\n（X = 1~6 对应机器 1~6）')

    add_paragraph_styled(doc, 'VLAN 划分：', bold=True)
    add_bullet(doc, 'VLAN 10：管理网（中央服务器 + 边缘节点管理口）')
    add_bullet(doc, 'VLAN 101-106：采集网 1-6（各边缘节点独立采集网段隔离）')
    add_bullet(doc, '采集网络不与管理网互通，防止广播风暴与带宽争抢')

    add_heading_styled(doc, '4.4  软件架构', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    add_paragraph_styled(doc, '边缘节点软件（基本复用当前代码）：', bold=True)
    edge_sw = [
        ('web.unified_app', 'FastAPI 主应用', '保持不变'),
        ('web.state_manager', '状态管理', '保持不变，只管理本节点 5 漏斗'),
        ('core.capture_window', '采集窗口', '保持不变'),
        ('algo.detector', '检测算法', '保持不变'),
        ('plc.allen_bradley', 'PLC 通信', '保持不变'),
        ('config/devices.yaml', '本节点配置', '只配 1 机 5 漏斗'),
        ('(新增) web.report_client', '上报客户端', '定时上报状态到中央服务器'),
    ]
    add_table_styled(doc,
        ['模块', '职责', '改动'],
        edge_sw,
        col_widths=[4.5, 5.0, 6.5])

    add_paragraph_styled(doc, '中央服务器软件（新开发）：', bold=True)
    central_sw = [
        ('web.central_app', 'FastAPI 聚合应用', '新开发'),
        ('central.aggregator', '状态聚合器', '定时从各边缘拉取 /api/overview'),
        ('central.storage', '历史数据存储', 'SQLite / PostgreSQL'),
        ('central.alert_router', '告警路由', '将边缘告警推送给运维'),
        ('(新增) Web 总览页', '30 漏斗统一展示', '新开发前端'),
    ]
    add_table_styled(doc,
        ['模块', '职责', '说明'],
        central_sw,
        col_widths=[4.5, 5.0, 6.5])

    add_heading_styled(doc, '4.5  PLC 分配方案', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    plc_alloc = [
        ('翻车机 1', 'PLC 1 (192.168.101.10)', '漏斗 1-1 ～ 1-5', '边缘节点 1'),
        ('翻车机 2', 'PLC 2 (192.168.102.10)', '漏斗 2-1 ～ 2-5', '边缘节点 2'),
        ('翻车机 3', 'PLC 3 (192.168.103.10)', '漏斗 3-1 ～ 3-5', '边缘节点 3'),
        ('翻车机 4', 'PLC 4 (192.168.104.10)', '漏斗 4-1 ～ 4-5', '边缘节点 4'),
        ('翻车机 5', 'PLC 5 (192.168.105.10)', '漏斗 5-1 ～ 5-5', '边缘节点 5'),
        ('翻车机 6', 'PLC 6 (192.168.106.10)', '漏斗 6-1 ～ 6-5', '边缘节点 6'),
    ]
    add_table_styled(doc,
        ['翻车机', 'PLC 地址', '漏斗范围', '归属边缘节点'],
        plc_alloc,
        col_widths=[3.0, 4.5, 3.5, 3.5])

    add_paragraph_styled(doc,
        '每台 PLC 沿用 V3.0 的完整 9 标签协议（IPC_Heartbeat、IPC_Online、Vision_CanTip、'
        'Vision_FaultCode、Vision_ResultValid、Vision_Enable、Vision_CaptureState、'
        'PLC_CaptureCmd、Tipper_InPosition），PLC 梯形图无需改动。',
        first_line_indent=Cm(0.74))

    add_page_break(doc)

    # ============ 第五章：中央聚合层开发方案 ============
    add_heading_styled(doc, '第五章  中央聚合层开发方案', level=1, color=RGBColor(0x1F, 0x4E, 0x79))

    add_heading_styled(doc, '5.1  技术栈', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    tech_stack = [
        ('Web 框架', 'FastAPI + Uvicorn', '与边缘节点一致，复用模板'),
        ('数据存储', 'PostgreSQL 16', '历史数据、告警、审计日志'),
        ('时序数据', 'TimescaleDB 扩展', '心跳、检测结果时序分析'),
        ('消息队列', 'Redis Streams', '告警路由、跨节点通信'),
        ('任务调度', 'APScheduler', '定时聚合、归档、健康检查'),
        ('前端', 'Vue 3 + ECharts', '比当前 Jinja 模板更现代'),
        ('部署', 'Docker Compose', '快速部署、易维护'),
    ]
    add_table_styled(doc,
        ['组件', '选型', '理由'],
        tech_stack,
        col_widths=[3.5, 5.5, 7.0])

    add_heading_styled(doc, '5.2  API 接口设计', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    add_paragraph_styled(doc, '中央服务器 API：', bold=True)

    api_table = [
        ('GET', '/api/central/overview', '所有 6 节点 × 5 漏斗 = 30 漏斗的聚合状态'),
        ('GET', '/api/central/edges', '边缘节点列表与在线状态'),
        ('GET', '/api/central/edge/{id}', '单个边缘节点详情'),
        ('GET', '/api/central/history/alarms', '历史告警查询（分页）'),
        ('GET', '/api/central/history/timeline', '采集窗口时间线（最近 1000 条）'),
        ('POST', '/api/central/admin/edge/{id}/action', '对指定边缘节点下发控制命令（启/停）'),
    ]
    add_table_styled(doc,
        ['方法', '路径', '说明'],
        api_table,
        col_widths=[2.0, 6.0, 8.0])

    add_paragraph_styled(doc, '边缘节点上报 API（被动拉取）：', bold=True)
    add_paragraph_styled(doc,
        '中央服务器定时（如每 3 秒）调用边缘节点的 /api/overview 聚合状态，'
        '不需要边缘节点主动推送。这种设计简单且健壮——边缘节点无需知道中央服务器的存在。',
        first_line_indent=Cm(0.74))

    add_heading_styled(doc, '5.3  数据流与同步策略', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    add_paragraph_styled(doc, '三种数据流：', bold=True)

    data_flow = [
        ('实时状态流', '3 秒/次', '轮询 /api/overview', '内存缓存，供 Web 展示'),
        ('告警流', '事件驱动', '轮询 /api/faults/all', '变化检测，入库存档'),
        ('历史归档流', '每小时', '批量拉取检测记录', 'PostgreSQL 归档'),
    ]
    add_table_styled(doc,
        ['数据流', '频率', '拉取方式', '处理'],
        data_flow,
        col_widths=[3.5, 2.5, 4.5, 5.5])

    add_paragraph_styled(doc, '数据一致性保证：', bold=True)
    add_bullet(doc, '边缘节点生成 UUID 作为检测记录主键，中央服务器按 UUID 去重')
    add_bullet(doc, '时钟同步：所有节点 NTP 同步到同一时钟源')
    add_bullet(doc, '网络中断恢复：边缘节点本地持久化待上报数据，恢复后补传')
    add_bullet(doc, '中央服务器宕机：边缘节点独立运行，不影响安全连锁')

    add_heading_styled(doc, '5.4  开发工作量估算', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    workload = [
        ('边缘节点改造', '0.5 周', '仅需在 web.state_manager 加 edge_id 字段'),
        ('中央聚合器开发', '1 周', '定时拉取 + 内存缓存 + 去重'),
        ('中央 Web API', '1 周', '6 个 REST API + WebSocket'),
        ('中央 Web 前端', '1.5 周', 'Vue 3 总览页 + 历史查询'),
        ('数据库设计与实现', '0.5 周', '5 张表 + 索引 + 视图'),
        ('部署脚本', '0.3 周', 'Docker Compose + 初始化脚本'),
        ('联调测试', '1 周', '多节点联调 + 故障注入测试'),
        ('文档与交付', '0.2 周', '运维手册 + API 文档'),
        ('总计', '6 周', '由 1 名高级工程师完成'),
    ]
    add_table_styled(doc,
        ['任务', '工期', '说明'],
        workload,
        col_widths=[4.0, 2.5, 9.5])

    add_page_break(doc)

    # ============ 第六章：分阶段实施路线图 ============
    add_heading_styled(doc, '第六章  分阶段实施路线图', level=1, color=RGBColor(0x1F, 0x4E, 0x79))

    add_paragraph_styled(doc,
        '分阶段实施可以控制风险、快速验证、灵活调整。本章制定三阶段路线图，'
        '每阶段有明确的交付物与验收标准。',
        first_line_indent=Cm(0.74))

    add_heading_styled(doc, '6.1  阶段一：单节点验证（0-3 月）', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    add_paragraph_styled(doc, '目标：', bold=True)
    add_paragraph_styled(doc,
        '在现有单机 + 单 PLC 的基础上，扩展到 5 漏斗配置。'
        '验证单节点承载 5 漏斗的稳定性，为后续多节点部署积累数据。',
        first_line_indent=Cm(0.74))

    phase1 = [
        ('第 1 月', '补光灯安装 + 现场标定', '解决 fault_code=3 画面全黑问题'),
        ('第 1 月', '采购 4 台相机 + 4 台PLC（或复用现有 PLC 多漏斗标签）', '扩展硬件'),
        ('第 2 月', '配置 5 漏斗的 devices.yaml', '修改配置文件'),
        ('第 2 月', '格栅 ROI 标定（4 个新漏斗）', '使用 tools/grid_calibrator'),
        ('第 2 月', '阈值调优（grid_ratio, coverage）', '根据真实积煤数据'),
        ('第 3 月', '连续运行验证', '72 小时无崩溃，误报率 < 1%'),
        ('第 3 月', '生成阶段性报告', '性能数据、问题清单、优化建议'),
    ]
    add_table_styled(doc,
        ['时间', '任务', '交付物/验收'],
        phase1,
        col_widths=[2.0, 7.0, 7.0])

    add_paragraph_styled(doc, '阶段一投入：', bold=True)
    add_bullet(doc, '硬件：4 × 相机 + 线缆 = 约 1.5 万')
    add_bullet(doc, '人力：0.5 人·月（现场标定 + 测试）')
    add_bullet(doc, '风险：现场布线、补光灯采购周期')

    add_heading_styled(doc, '6.2  阶段二：分布式部署（3-9 月）', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    add_paragraph_styled(doc, '目标：', bold=True)
    add_paragraph_styled(doc,
        '按方案 B 部署 6 个边缘节点 + 1 个中央服务器，实现 30 漏斗的完整检测能力与统一监控。',
        first_line_indent=Cm(0.74))

    phase2 = [
        ('第 4 月', '采购全部硬件（5 边缘节点 + 中央服务器 + 交换机）', '硬件到位'),
        ('第 4 月', '开发中央聚合层（Week 1-4）', '中央 API 开发完成'),
        ('第 5 月', '中央 Web 前端开发 + 联调', 'Web 总览页完成'),
        ('第 5 月', '部署边缘节点 2 和 3（先验证 2 节点聚合）', '2 节点联调通过'),
        ('第 6 月', '部署边缘节点 4-6，逐台验证', '6 节点全部上线'),
        ('第 7 月', '系统整体联调测试（含 PLC 梯形图）', '全链路测试通过'),
        ('第 7 月', '故障注入测试：断网、断电、节点宕机', '可用性测试通过'),
        ('第 8 月', '试运行阶段：现场 30 漏斗连续运行', '1 个月无重大故障'),
        ('第 9 月', '正式验收 + 运维交付', '验收通过，文档交付'),
    ]
    add_table_styled(doc,
        ['时间', '任务', '交付物/验收'],
        phase2,
        col_widths=[2.0, 7.0, 7.0])

    add_paragraph_styled(doc, '阶段二投入：', bold=True)
    add_bullet(doc, '硬件：约 24 万（扣除阶段一已采购部分）')
    add_bullet(doc, '软件开发：1.5 人·月（中央聚合层）')
    add_bullet(doc, '现场部署：2 人·月（安装、布线、调试）')
    add_bullet(doc, '风险：多节点时钟同步、网络稳定性、现场 PLC 配合度')

    add_heading_styled(doc, '6.3  阶段三：AI 升级（9-18 月）', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    add_paragraph_styled(doc, '目标：', bold=True)
    add_paragraph_styled(doc,
        '在方案 B 稳定运行 3 个月后，启动方案 C 的 AI 升级。'
        '利用阶段二积累的真实积煤图像训练 YOLO 模型，逐台替换边缘节点为 Jetson AGX Orin。',
        first_line_indent=Cm(0.74))

    phase3 = [
        ('第 10 月', '图像数据收集与标注（5000+ 张）', '标注数据集交付'),
        ('第 11-12 月', 'YOLO v11 模型训练', '模型 mAP ≥ 0.90'),
        ('第 13 月', 'Jetson AGX Orin 环境搭建 + 模型部署', 'Jetson 边缘节点原型完成'),
        ('第 14 月', '现场 1 台 Jetson 节点试运行', '1 个月对比测试'),
        ('第 15-17 月', '逐台替换其余 5 台工控机为 Jetson', '6 个 Jetson 节点全部上线'),
        ('第 18 月', 'AI 版验收 + 知识转移', 'AI 方案正式切换'),
    ]
    add_table_styled(doc,
        ['时间', '任务', '交付物/验收'],
        phase3,
        col_widths=[2.5, 7.0, 6.5])

    add_paragraph_styled(doc, '阶段三投入：', bold=True)
    add_bullet(doc, '硬件：Jetson AGX Orin × 6 = 约 10.8 万（工控机可回收或复用）')
    add_bullet(doc, '软件：AI 工程师 6 人·月（数据标注 + 训练 + 部署）')
    add_bullet(doc, '服务器：GPU 训练卡 RTX 4070 = 约 0.8 万')
    add_bullet(doc, '风险：标注数据不足、模型泛化性、现场光照变化')

    add_page_break(doc)

    # ============ 第七章：成本预算 ============
    add_heading_styled(doc, '第七章  成本预算', level=1, color=RGBColor(0x1F, 0x4E, 0x79))

    add_heading_styled(doc, '7.1  硬件成本', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    hw_cost = [
        ('边缘工控机', '5 台', '1.5 万', '7.5 万', '现有 1 台可复用，实购 5 台'),
        ('中央服务器', '1 台', '2 万', '2 万', 'i7/32GB/12TB 存储'),
        ('工业交换机', '7 台', '约 0.6 万', '4 万', '6 边缘 + 1 核心'),
        ('UPS 电源', '2 套', '1 万 + 1 万', '2 万', '中央机柜 + 边缘集中'),
        ('相机 Basler', '29 台', '0.3 万', '8.7 万', '现有 1 台复用'),
        ('GigE 线缆', '30 套', '200 元', '0.6 万', '工业屏蔽线缆，30 米'),
        ('补光灯', '30 套', '500 元', '1.5 万', 'LED 工业补光，含支架'),
        ('机柜与线缆桥架', '', '—', '1 万', '标准 42U 机柜 × 2'),
        ('合计（硬件）', '', '', '27.3 万', ''),
    ]
    add_table_styled(doc,
        ['项目', '数量', '单价', '合计', '说明'],
        hw_cost,
        col_widths=[3.5, 1.5, 2.5, 2.5, 5.5])

    add_heading_styled(doc, '7.2  软件开发成本', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    sw_cost = [
        ('中央聚合层开发', '1 人 × 6 周', '2 万/月', '3 万'),
        ('前端 Web 开发', '1 人 × 2 周', '1.5 万/月', '0.75 万'),
        ('现场部署与调试', '2 人 × 4 周', '1.5 万/月', '3 万'),
        ('测试与验收', '1 人 × 2 周', '1.5 万/月', '0.75 万'),
        ('文档与培训', '1 人 × 1 周', '1 万/月', '0.25 万'),
        ('合计（软件+服务）', '', '', '7.75 万'),
    ]
    add_table_styled(doc,
        ['项目', '工期', '单价', '合计'],
        sw_cost,
        col_widths=[5.0, 3.5, 3.5, 4.0])

    add_heading_styled(doc, '7.3  运维成本（三年）', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    ops_cost = [
        ('日常巡检', '每月 1 次', '1000 元/次', '3.6 万/3 年'),
        ('硬件维护', '故障更换', '预估 5%/年', '4.1 万/3 年'),
        ('软件升级', '每年 2 次', '1 万/次', '6 万/3 年'),
        ('电力消耗', '7 节点 × 150W × 24h', '0.8 元/kWh', '2.2 万/3 年'),
        ('网络与运营', '专线 + 云存储', '', '1 万/3 年'),
        ('合计（三年）', '', '', '约 16.9 万'),
    ]
    add_table_styled(doc,
        ['运维项目', '频率', '单价', '三年总计'],
        ops_cost,
        col_widths=[4.0, 3.5, 3.5, 5.0])

    add_heading_styled(doc, '7.4  总预算与 ROI', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    total_table = [
        ('硬件采购', '27.3 万', '一次性'),
        ('软件与服务', '7.75 万', '一次性'),
        ('运维（3 年）', '16.9 万', '分期'),
        ('三年总持有成本', '51.95 万', ''),
        ('单漏斗成本', '1.73 万/漏斗', '30 漏斗均摊'),
    ]
    add_table_styled(doc,
        ['成本项', '金额', '说明'],
        total_table,
        col_widths=[5.0, 4.0, 7.0])

    add_paragraph_styled(doc, 'ROI（投资回报）估算：', bold=True)
    add_paragraph_styled(doc,
        '假设每次翻车机卡死处理成本 5 万元（停产+人工+设备损坏），'
        '积煤检测系统每减少 1 次误翻即可产生直接收益。',
        first_line_indent=Cm(0.74))
    add_bullet(doc, '人工目视检测漏报率：15-20%（行业经验）')
    add_bullet(doc, '视觉系统漏报率：< 1%（实测数据）')
    add_bullet(doc, '30 漏斗年翻车次数：30 × 20 次/天 × 365 = 约 22 万次/年')
    add_bullet(doc, '视觉系统减少误翻：22 万 × 10% = 约 2.2 万次/年')
    add_bullet(doc, '直接经济效益：2.2 万 × 5 万/次 × 0.1%（卡死概率） ≈ 110 万/年')
    add_bullet(doc, '投资回收期：≈ 6 个月')

    add_page_break(doc)

    # ============ 第八章：风险评估与应对 ============
    add_heading_styled(doc, '第八章  风险评估与应对', level=1, color=RGBColor(0x1F, 0x4E, 0x79))

    add_heading_styled(doc, '8.1  技术风险', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    tech_risks = [
        ('节点间通信延迟', '中', '中央聚合可能滞后', '异步拉取 + 本地缓存降级'),
        ('时钟不同步', '低', '日志时序混乱', 'NTP 同步到同一时钟源'),
        ('PLC 连接并发', '中', '6 个 PLC 同时访问冲突', '每个边缘节点独立管理本地 PLC'),
        ('相机 GigE 带宽', '低', '30 台相机分布 6 个网段', '每节点 5 相机远低于 GigE 上限'),
        ('YOLO 模型精度', '中', '未训练数据可能精度低', '初期保留传统 CV 算法双保险'),
        ('Windows vs Linux', '低', '中央服务器选择', '优先 Ubuntu LTS（生产稳定）'),
    ]
    add_table_styled(doc,
        ['风险', '概率', '影响', '应对措施'],
        tech_risks,
        col_widths=[3.5, 1.5, 3.5, 7.5])

    add_heading_styled(doc, '8.2  项目风险', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    proj_risks = [
        ('硬件采购周期', '中', '影响整体进度', '提前 2 个月下单，关键件备货'),
        ('现场施工延误', '中', '布线和补光灯安装', '与施工方签订 SLA，分段验收'),
        ('开发人员不足', '低', '中央聚合层延期', '预留 20% 进度缓冲'),
        ('测试覆盖不足', '中', '上线后暴露问题', '建立完整的故障注入测试'),
        ('需求变更', '低', '比如甲方要求 40 漏斗', '架构预留扩展能力，变更按工时计费'),
    ]
    add_table_styled(doc,
        ['风险', '概率', '影响', '应对措施'],
        proj_risks,
        col_widths=[3.5, 1.5, 3.5, 7.5])

    add_heading_styled(doc, '8.3  运维风险', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    ops_risks = [
        ('单节点故障', '中', '5 漏斗不可用', '监控告警 + 15 分钟响应 SLA'),
        ('中央服务器宕机', '低', '监控页失效，边缘不受影响', '热备或快照还原'),
        ('网络中断', '低', '节点失联', '边缘节点独立运行，故障发生不影响安全'),
        ('磁盘空间不足', '中', '报警图像丢失', '自动归档 + 预警阈值 80%'),
        ('人员变更', '低', '维护知识流失', '完整文档 + 知识库'),
    ]
    add_table_styled(doc,
        ['风险', '概率', '影响', '应对措施'],
        ops_risks,
        col_widths=[3.5, 1.5, 3.5, 7.5])

    add_page_break(doc)

    # ============ 第九章：验收标准 ============
    add_heading_styled(doc, '第九章  验收标准', level=1, color=RGBColor(0x1F, 0x4E, 0x79))

    add_heading_styled(doc, '9.1  功能验收', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    func_acc = [
        ('F-01', '30 漏斗全部检测', '所有漏斗在总览页显示状态'),
        ('F-02', '报警触发与展示', '有煤时 3 秒内触发报警并显示在总览'),
        ('F-03', '采集窗口记录', '每次 PLC 触发记录完整窗口日志'),
        ('F-04', '安全连锁', 'coal_present=True 时 Vision_CanTip=False'),
        ('F-05', '心跳机制', 'PLC 端 Vision_Alive 持续为 True'),
        ('F-06', '故障告警', '相机/PLC 离线能触发故障告警'),
        ('F-07', '历史查询', '可查询 30 天内任意时段告警'),
        ('F-08', '远程管理', '通过 Web 可启停指定漏斗'),
        ('F-09', 'WebSocket 实时流', '总览页 3 秒内更新状态'),
        ('F-10', '鉴权系统', '管理操作需要 admin token'),
    ]
    add_table_styled(doc,
        ['编号', '功能项', '验收标准'],
        func_acc,
        col_widths=[2.0, 5.5, 8.5])

    add_heading_styled(doc, '9.2  性能验收', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    perf_acc = [
        ('P-01', '单帧检测延迟', '≤ 80ms'),
        ('P-02', '端到端延迟', '≤ 150ms'),
        ('P-03', '跳帧率', '≤ 10%'),
        ('P-04', '心跳稳定性', '500ms ± 50ms'),
        ('P-05', '检测误报率', '≤ 1%'),
        ('P-06', '检测漏报率', '≤ 0.5%'),
        ('P-07', '边缘节点 CPU 使用率', '≤ 60%（5 漏斗满负载）'),
        ('P-08', '中央服务器 CPU', '≤ 30%（30 漏斗聚合）'),
        ('P-09', '网络带宽利用率', '≤ 70%（单 GigE）'),
        ('P-10', '内存稳定性', '连续 7 天无泄漏'),
    ]
    add_table_styled(doc,
        ['编号', '性能项', '验收标准'],
        perf_acc,
        col_widths=[2.0, 5.5, 8.5])

    add_heading_styled(doc, '9.3  可靠性验收', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    rel_acc = [
        ('R-01', '连续运行时长', '≥ 500 小时无崩溃'),
        ('R-02', '单节点故障隔离', '1 节点故障不影响其他节点'),
        ('R-03', '自动重启', '进程崩溃后看门狗 10 秒内拉起'),
        ('R-04', '故障自愈', '相机掉线自动重连'),
        ('R-05', 'PLC 断网恢复', 'PLC 恢复后心跳自动重建'),
        ('R-06', '数据持久化', '断电重启后已归档数据不丢失'),
        ('R-07', '告警不漏', '30 天无未送达告警'),
        ('R-08', '系统可用率', '≥ 99.5%（月度）'),
        ('R-09', 'MTBF', '≥ 500 小时'),
        ('R-10', 'MTTR', '≤ 15 分钟（有人值守时）'),
    ]
    add_table_styled(doc,
        ['编号', '可靠性项', '验收标准'],
        rel_acc,
        col_widths=[2.0, 5.5, 8.5])

    add_page_break(doc)

    # ============ 附录 A ============
    add_heading_styled(doc, '附录 A  PLC 标签清单（每台翻车机，6 台共用）', level=1, color=RGBColor(0x1F, 0x4E, 0x79))

    add_paragraph_styled(doc,
        '每台 PLC 承载 1 台翻车机 × 5 漏斗。标签命名规范：下划线区分字段，漏斗编号后缀。',
        first_line_indent=Cm(0.74))

    add_heading_styled(doc, 'A.1  全局标签（每 PLC 共用）', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    global_tags = [
        ('IPC_Heartbeat_1', 'DINT', 'W', '边缘节点 → PLC 心跳（500ms 递增）'),
        ('IPC_Online_1', 'BOOL', 'W', '边缘节点在线状态'),
        ('HB_Last_1', 'DINT', 'R', 'PLC 记录上次心跳值'),
        ('HB_Timer_1', 'TIMER', 'R', 'PLC 心跳超时计时器（2 秒）'),
        ('Vision_Alive_1', 'BOOL', 'R', 'PLC 侧综合判定视觉系统存活'),
    ]
    add_table_styled(doc,
        ['标签名', '类型', '方向', '说明'],
        global_tags,
        col_widths=[5.0, 2.5, 2.0, 6.5])

    add_heading_styled(doc, 'A.2  每漏斗标签（5 漏斗各 1 组）', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    per_funnel = [
        ('Vision_CanTip_1_X', 'BOOL', 'W', '漏斗 X 可翻转（X=1-5）'),
        ('Vision_FaultCode_1_X', 'DINT', 'W', '故障码（0=正常 / 1-4）'),
        ('Vision_ResultValid_1_X', 'BOOL', 'W', '结果可信'),
        ('Vision_Enable_1_X', 'BOOL', 'W', '视觉采集启用'),
        ('Vision_CaptureState_1_X', 'DINT', 'W', '采集状态（0 闲 /1 采集 / 2 完成）'),
        ('PLC_CaptureCmd_1_X', 'DINT', 'R', '采集指令（0 停 / 1 启）'),
        ('Tipper_InPosition_1_X', 'BOOL', 'R', '翻车机回位信号'),
    ]
    add_table_styled(doc,
        ['标签名（X=1-5）', '类型', '方向', '说明'],
        per_funnel,
        col_widths=[5.5, 2.5, 2.0, 6.0])

    add_paragraph_styled(doc,
        '每台 PLC 合计标签数 = 5（全局） + 5 漏斗 × 7（每漏斗） = 40 个标签。',
        bold=True, first_line_indent=Cm(0.74))

    add_page_break(doc)

    # ============ 附录 B ============
    add_heading_styled(doc, '附录 B  网络配置建议', level=1, color=RGBColor(0x1F, 0x4E, 0x79))

    add_heading_styled(doc, 'B.1  交换机配置清单', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    switch_config = [
        ('VLAN 划分', '管理 VLAN 10 + 采集 VLAN 101-106'),
        ('MTU 设置', '采集 VLAN 启用 Jumbo Frame（9000 字节）以减少相机帧分包'),
        ('QoS', '相机流量标记为 EF（加急转发）优先级'),
        ('广播风暴抑制', '采集 VLAN 限制广播包 < 5%'),
        ('端口聚合', '核心交换机到边缘交换机 4 口 LAG 聚合'),
        ('STP', '生成树协议启用，防止环路'),
        ('SNMP 监控', '所有交换机开启 SNMP v3，监控端口流量'),
        ('日志', 'Syslog 推送到中央服务器'),
    ]
    add_table_styled(doc,
        ['配置项', '建议值'],
        switch_config,
        col_widths=[4.5, 11.5])

    add_heading_styled(doc, 'B.2  防火墙策略', level=2, color=RGBColor(0x2E, 0x75, 0xB6))

    fw_rules = [
        ('采集 VLAN → 管理 VLAN', '只允许 TCP 8080（HTTP API）'),
        ('管理 VLAN → 采集 VLAN', '阻断（采集网隔离）'),
        ('外网 → 管理 VLAN', '只允许 VPN'),
        ('内网 SSH/RDP', '白名单 IP'),
    ]
    add_table_styled(doc,
        ['流向', '策略'],
        fw_rules,
        col_widths=[6.0, 10.0])

    add_page_break(doc)

    # ============ 附录 C ============
    add_heading_styled(doc, '附录 C  运维手册大纲', level=1, color=RGBColor(0x1F, 0x4E, 0x79))

    add_paragraph_styled(doc,
        '运维手册是系统交付的重要组成部分，本节给出详细大纲，正式文档将在阶段二末期交付。',
        first_line_indent=Cm(0.74))

    ops_toc = [
        ('第 1 章', '系统架构概述', '边缘节点 + 中央服务器的基本工作原理'),
        ('第 2 章', '日常巡检清单', '每日、每周、每月巡检项'),
        ('第 3 章', '监控指标与告警', '关键指标阈值、告警级别、响应动作'),
        ('第 4 章', '常见故障处理', '相机掉线、PLC 断连、边缘节点宕机等'),
        ('第 5 章', '配置变更流程', '增删漏斗、修改阈值、人员权限'),
        ('第 6 章', '数据备份恢复', '报警图像、配置文件、历史数据'),
        ('第 7 章', '系统升级指南', '升级检查清单、回滚流程'),
        ('第 8 章', '安全管理', '账号权限、审计日志、密码轮换'),
        ('第 9 章', '应急预案', '断电、断网、关键节点故障'),
        ('第 10 章', '联系方式', '技术支持、应急电话、升级窗口'),
    ]
    add_table_styled(doc,
        ['章节', '标题', '内容概述'],
        ops_toc,
        col_widths=[2.5, 4.0, 9.5])

    # 结尾
    add_page_break(doc)

    add_heading_styled(doc, '文档审批', level=1, color=RGBColor(0x1F, 0x4E, 0x79))

    for _ in range(2):
        doc.add_paragraph()

    approval = doc.add_table(rows=5, cols=3)
    approval.alignment = WD_TABLE_ALIGNMENT.CENTER

    hdr = approval.rows[0].cells
    for i, text in enumerate(['角色', '姓名', '签字/日期']):
        hdr[i].text = ''
        p = hdr[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(text)
        run.font.name = '微软雅黑'
        run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
        run.font.size = Pt(11)
        run.font.bold = True
        set_cell_bg(hdr[i], '2E75B6')
        run.font.color.rgb = RGBColor.from_string('FFFFFF')
        set_cell_border(hdr[i])

    roles = ['项目负责人', '技术负责人', '安全负责人', '甲方代表']
    for i, role in enumerate(roles):
        row_cells = approval.rows[i+1].cells
        row_cells[0].text = ''
        p = row_cells[0].paragraphs[0]
        run = p.add_run(role)
        run.font.name = '微软雅黑'
        run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
        run.font.size = Pt(11)
        set_cell_border(row_cells[0])
        set_cell_border(row_cells[1])
        set_cell_border(row_cells[2])
        row_cells[1].width = Cm(4)
        row_cells[2].width = Cm(6)

    for _ in range(4):
        doc.add_paragraph()

    end = doc.add_paragraph()
    end.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = end.add_run('—— 文档结束 ——')
    run.font.name = '微软雅黑'
    run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    run.font.italic = True

    # 保存
    output_path = Path(r'D:\coal_detection_project\docs\翻车机积煤检测系统_30漏斗扩展方案_V1.0.docx')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    print(f'文档已生成: {output_path}')
    print(f'文件大小: {output_path.stat().st_size / 1024:.1f} KB')


if __name__ == '__main__':
    generate_document()
