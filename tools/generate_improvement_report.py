"""生成整改记录 Word 文档"""
import os, sys
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
    t = doc.add_table(rows=1+len(rows), cols=len(headers))
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
            t.rows[ri+1].cells[ci].text = str(val)
    doc.add_paragraph()


def main():
    doc = Document()
    setup(doc)

    # Cover
    for _ in range(5):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run('翻车机积煤检测系统 V3.0')
    r.font.size = Pt(26)
    r.bold = True
    r.font.color.rgb = RGBColor(0x1A, 0x3C, 0x6E)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run('整改记录与已知限制')
    r.font.size = Pt(18)
    r.font.color.rgb = RGBColor(0x44, 0x72, 0xC4)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run('2026-04-03').font.size = Pt(12)
    doc.add_page_break()

    # CRITICAL
    doc.add_heading('一、已修复 CRITICAL', 1)
    T(doc, ['编号', '问题', '修复', '日期'],
      [['C1', 'DetectionResult dict空', '移除继承', '03-28'],
       ['C2', '心跳无锁递增', '_heartbeat_value_lock', '03-28'],
       ['C3', 'None→允许翻车', 'is False判断', '03-28'],
       ['C4', '线程池饥饿卡死', '三池+超时', '03-30'],
       ['C5', '画质失败允许翻车', 'fault_code传递', '03-28'],
       ['C6', '无人看页面不检测', '后台worker', '04-03']])

    # HIGH
    doc.add_heading('二、已修复 HIGH', 1)
    T(doc, ['编号', '问题', '修复', '日期'],
      [['H1', 'grid_mask过时', '截断后重建', '03-28'],
       ['H2', '置信度逻辑重叠', 'consistency公式', '03-28'],
       ['H3', 'PLC重连无锁替换', '_io_lock下替换', '03-28'],
       ['H4', 'WebSocket永不退出', '30次失败break', '03-28'],
       ['H5', '启停API无鉴权', 'verify_admin', '03-28'],
       ['H6', '启停不检查PLC返回', '失败回滚+503', '04-03'],
       ['H7', '配置保存失败被吞', 'RuntimeError+500', '04-03'],
       ['H8', '生产回退Mock', 'raise不回退', '04-03'],
       ['H9', '投票字段名错位', '别名优先读取', '04-03'],
       ['H10', '增删不启停worker', '_start/_stop', '04-03'],
       ['H11', '并发grab相机', 'WS纯展示', '04-03'],
       ['H12', 'tick多线程驱动', '只由worker驱动', '04-03'],
       ['H13', '多漏斗争抢PLC', '无相机不驱动', '04-03']])

    # MEDIUM
    doc.add_heading('三、已修复 MEDIUM', 1)
    T(doc, ['编号', '问题', '修复', '日期'],
      [['M1', '无reset_statistics()', '添加方法', '04-03'],
       ['M2', '健康检查漏报', '区分未初始化/断连', '04-03'],
       ['M3', '历史接口无数据', 'worker写历史', '04-03'],
       ['M4', '阈值无校验', '范围+组合约束', '04-03'],
       ['M5', '非法输入未捕获', 'try/except→400', '04-03'],
       ['M6', 'PLC=None报成功', '回滚+报错', '04-03'],
       ['M7', '画质一刀切', '分区+对比度+自适应', '03-30'],
       ['M8', '故障帧参与投票', '故障帧排除', '03-30']])

    doc.add_page_break()

    # Known limits - Architecture
    doc.add_heading('四、已知限制 — 架构', 1)
    T(doc, ['编号', '限制', '影响', '改进时间'],
      [['L1', '采集控制器per-funnel但PLC per-machine', '多漏斗争抢标签', '接第2台相机前'],
       ['L2', '配置变更非原子', '保存失败内存已变', 'V3.1'],
       ['L3', '运行时add不区分ImportError', '极罕见场景', 'V3.1'],
       ['L4', '启动中途失败资源残留', 'OS级回收', 'V3.1']])

    # Known limits - Security
    doc.add_heading('五、已知限制 — 安全', 1)
    T(doc, ['编号', '限制', '影响', '接受条件'],
      [['L5', 'Token无过期', '泄露长期有效', '内网+改密码'],
       ['L6', 'WS无鉴权', '可看视频', '内网风险低'],
       ['L7', '报警重启丢失', '无法追溯', '日志可查+后续SQLite']])

    # Known limits - Ops
    doc.add_heading('六、已知限制 — 运维', 1)
    T(doc, ['编号', '限制', '影响', '接受条件'],
      [['L8', 'images无清理', '磁盘满', '手动或加retention'],
       ['L9', 'PLC被挤掉不恢复', '需重启', '正常不会出现'],
       ['L10', '单进程5秒空窗', '看门狗重启', 'PLC 2秒保护']])

    doc.add_page_break()

    # L1 improvement
    doc.add_heading('七、L1 架构改进方案', 1)
    doc.add_paragraph('当前问题：每个漏斗有独立的CaptureWindowController，但共享同一台翻车机的PLC标签。')
    doc.add_paragraph('改进方案：CaptureWindowController提升到MachineState级别')
    doc.add_paragraph('Machine级控制器唯一读写PLC标签', style='List Bullet')
    doc.add_paragraph('触发采集时通知所有漏斗worker抓帧', style='List Bullet')
    doc.add_paragraph('窗口结束汇总所有漏斗结果', style='List Bullet')
    doc.add_paragraph('预计工作量：2-3天，接第2台相机前完成', style='List Bullet')

    # Stability data
    doc.add_heading('八、稳定性验证', 1)
    T(doc, ['指标', '修复前', '修复后'],
      [['连续运行', '每2h崩溃', '49.4h无崩溃'],
       ['内存', '持续增长', '177-198MB稳定'],
       ['线程', '可能泄漏', '63-69稳定'],
       ['全黑判定', '允许翻车', 'FaultCode=3禁止'],
       ['相机释放', '等30秒', '等3秒'],
       ['并发grab', 'RuntimeException', 'WS不再grab']])

    # History
    doc.add_heading('九、变更历史', 1)
    T(doc, ['日期', '版本', '内容'],
      [['2026-03-28', 'V3.0.1', '修复9个安全漏洞(C1-C5,H1-H5)'],
       ['2026-03-30', 'V3.0.2', '线程池隔离+画质自检+看门狗'],
       ['2026-04-01', 'V3.0.3', 'PLC触发采集+窗口投票+启停'],
       ['2026-04-03', 'V3.0.4', '后台worker+并发修复+校验+文档']])

    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'docs', 'improvement_report_v3.0.docx')
    doc.save(out)
    print(f'OK: {out}')
    print(f'Size: {os.path.getsize(out)} bytes')


if __name__ == '__main__':
    main()
