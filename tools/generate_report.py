"""生成部署报告 Word 文档"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn


def set_chinese_font(doc):
    style = doc.styles['Normal']
    style.font.name = 'Microsoft YaHei'
    style.font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
    for i in range(1, 4):
        h = doc.styles[f'Heading {i}']
        h.font.name = 'Microsoft YaHei'
        h.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
        h.font.color.rgb = RGBColor(0x1A, 0x3C, 0x6E)


def add_table(doc, headers, rows):
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


def main():
    doc = Document()
    set_chinese_font(doc)

    # Cover
    for _ in range(6):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run('翻车机积煤检测系统 V3.0')
    r.font.size = Pt(28)
    r.bold = True
    r.font.color.rgb = RGBColor(0x1A, 0x3C, 0x6E)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run('部署报告')
    r.font.size = Pt(20)
    r.font.color.rgb = RGBColor(0x44, 0x72, 0xC4)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run('2026-04-03 | 煤矿翻车机房 | 工业现场').font.size = Pt(12)
    doc.add_page_break()

    # === Sections ===
    doc.add_heading('一、系统概述', 1)
    doc.add_paragraph('本系统基于计算机视觉技术，通过工业相机实时拍摄翻车机格栅画面，自动检测积煤覆盖，结果写入PLC与安全连锁联动。')
    p = doc.add_paragraph()
    r = p.add_run('核心原则：宁可漏报，不可误报。')
    r.bold = True
    r.font.color.rgb = RGBColor(0xC0, 0, 0)

    doc.add_heading('1.1 技术栈', 2)
    add_table(doc, ['技术', '版本', '用途'],
              [['Python', '3.10+', '主程序'], ['OpenCV', '4.8+', '图像处理'],
               ['pypylon', '3.0+', 'Basler相机SDK'], ['pycomm3', '1.2+', 'AB PLC通信'],
               ['FastAPI', '0.100+', 'Web监控'], ['loguru', '0.7+', '日志']])

    doc.add_heading('二、硬件清单', 1)
    add_table(doc, ['设备', '型号', 'IP', '说明'],
              [['工控机', 'Windows 10', '192.168.1.10', '运行检测服务'],
               ['相机', 'Basler acA1600-60gm', '192.168.1.12', 'Mono8 1600x1200 GigE'],
               ['PLC', '1769-L16ER/B B1B', '192.168.1.19', 'CompactLogix 固件36.11'],
               ['交换机', '千兆工业交换机', '-', '所有设备互联']])

    doc.add_heading('2.1 相机参数', 2)
    add_table(doc, ['参数', '值', '说明'],
              [['分辨率', '1600x1200', 'Mono8灰度'], ['帧率', '5.5 FPS', 'GigE带宽限制'],
               ['GigE心跳超时', '3000ms', '崩溃后3秒释放'], ['包间延迟', 'GevSCPD=100', '最佳值'],
               ['帧率节点', 'AcquisitionFrameRateAbs', '旧版SFNC']])

    doc.add_heading('2.2 I/O线缆 (Hirose 6-pin)', 2)
    add_table(doc, ['线色', 'Pin', '功能', '状态'],
              [['已接', 'Pin1+6', '电源+12V/GND', '已接通'],
               ['白', 'Pin2', 'Line1输入(触发)', '预留'],
               ['绿', 'Pin5', 'I/O GND', '预留'],
               ['黄', 'Pin4', 'Line2输出(曝光)', '可接补光灯'],
               ['蓝', 'Pin3', 'Line2 GND', '预留'],
               ['裸线', 'Shield', '屏蔽接地', '建议接PE']])

    doc.add_heading('三、PLC配置 (19个标签)', 1)
    doc.add_heading('3.1 服务器写入标签 (7个)', 2)
    add_table(doc, ['标签', '类型', '等级', '说明'],
              [['Vision_CanTip', 'BOOL', 'CRITICAL', '安全核心:无积煤=True'],
               ['Vision_FaultCode', 'DINT', 'CRITICAL', '0正常/1相机/2PLC/3画质/4人工'],
               ['Vision_ResultValid', 'BOOL', 'HIGH', '结果可信'],
               ['IPC_Heartbeat', 'DINT', 'CRITICAL', '500ms递增 0~65535'],
               ['IPC_Online', 'BOOL', 'HIGH', '系统在线'],
               ['Vision_Enable', 'BOOL', 'HIGH', '采集启用(停用→Allow=1)'],
               ['Vision_CaptureState', 'DINT', 'MEDIUM', '0空闲/1采集/2完成']])

    doc.add_heading('3.2 PLC写入标签 (2个)', 2)
    add_table(doc, ['标签', '类型', '说明'],
              [['PLC_CaptureCmd', 'DINT', '0空闲/1采集'],
               ['Tipper_InPosition', 'BOOL', '回位信号']])

    doc.add_heading('3.3 梯形图 (10个Rung)', 2)
    rungs = [
        'Rung 0: 心跳检测 NEQ→MOV+RES', 'Rung 1: 超时计时 TON 2000ms',
        'Rung 2: 存活判断 Online+XIO Timer.DN→Alive',
        'Rung 3: 故障灯 XIO Alive→Fault_Light',
        'Rung 4: 允许翻车(并联) Enable=0→Allow; Alive+CanTip+Valid+Fault=0→Allow',
        'Rung 5: 人工确认 Fault=4→Manual_Light',
        'Rung 6: 延时触发 Tipper+Enable+State=0→TON 10s',
        'Rung 7: 采集指令 Delay.DN→MOV 1→Cmd',
        'Rung 8: 完成复位 State=2→MOV 0→Cmd+RES',
        'Rung 9: 回位消失 XIO Tipper→MOV 0→Cmd+RES']
    for r in rungs:
        doc.add_paragraph(r, style='List Number')

    doc.add_heading('四、检测算法', 1)
    doc.add_paragraph('处理流程：原始帧→画质智能自检→ECC配准(320x240)→CLAHE增强→双因素检测→判定')

    doc.add_heading('4.1 画质智能自检', 2)
    add_table(doc, ['检查项', '方法', '拒绝条件'],
              [['绝对黑', 'mean+std', 'mean<5且std<3'],
               ['过曝', 'mean', 'mean>240'],
               ['格栅区域暗', 'ROI mean+std', 'roi_mean<8且roi_std<5'],
               ['模糊', 'Laplacian+自适应', 'laplacian<阈值且std<8']])

    doc.add_heading('4.2 性能指标', 2)
    add_table(doc, ['指标', '要求', '实测'],
              [['单帧处理', '≤80ms', '~51ms'],
               ['心跳间隔', '500ms', '正常'],
               ['帧数/窗口', '-', '~61-63帧']])

    doc.add_heading('五、安全设计', 1)
    doc.add_heading('5.1 已修复漏洞', 2)
    add_table(doc, ['编号', '严重度', '问题', '修复'],
              [['C1', 'CRITICAL', 'DetectionResult dict空', '移除继承'],
               ['C2', 'CRITICAL', '心跳无锁递增', '加锁'],
               ['C3', 'CRITICAL', 'None→允许翻车', 'is False'],
               ['C4', 'CRITICAL', '线程池饥饿卡死', '三池+超时'],
               ['-', 'CRITICAL', '画质失败允许翻车', 'fault传递'],
               ['H1-H5', 'HIGH', '5个高危漏洞', '全部修复']])

    doc.add_heading('5.2 线程池隔离', 2)
    add_table(doc, ['线程池', 'Workers', '用途', '超时'],
              [['_grab_executor', '4', 'camera.grab()', '10s'],
               ['_detect_executor', '8', 'detect_frame()', '10s'],
               ['心跳线程', '1', 'Heartbeat', '2s'],
               ['_io_lock', '-', 'PLC读写', '5s']])

    doc.add_heading('六、稳定性验证', 1)
    add_table(doc, ['指标', '结果'],
              [['连续运行', '45+小时无崩溃'], ['内存', '179MB稳定'],
               ['线程', '65个不增长'], ['采集周期', '2710+次'],
               ['错误', '0条ERROR']])

    doc.add_heading('七、部署指南', 1)
    doc.add_heading('7.1 硬件清单', 2)
    add_table(doc, ['序号', '项目', '数量', '说明'],
              [['1', '工控机', '1台', 'Win10+ Python3.10+'],
               ['2', 'Basler acA1600-60gm', 'N台', '每漏斗1台'],
               ['3', '1769-L16ER/B', 'N台', '每翻车机1台'],
               ['4', '千兆交换机', '1台', '互联'],
               ['5', '补光灯', 'N台', '每漏斗1台'],
               ['6', '网线Cat6+电源', '若干', '按现场']])

    doc.add_heading('7.2 部署步骤', 2)
    steps = ['安装Python+依赖', '安装Pylon SDK', '复制项目', '配置devices.yaml',
             '设置管理员密码', '硬件测试', 'PLC编程(10 Rung)', '联调测试',
             '安装补光灯', '拍基准图', '标定格栅ROI', '调阈值',
             '安装开机自启', '启动服务', '启动监控']
    for s in steps:
        doc.add_paragraph(s, style='List Number')

    doc.add_heading('7.3 故障排查', 2)
    add_table(doc, ['故障', '原因', '排查'],
              [['相机连不上', 'IP/网线/占用', 'ping+等3秒'],
               ['PLC连不上', 'IP/RSLinx', 'ping+检查驱动'],
               ['画面全黑', '无补光灯', '检查灯+曝光'],
               ['误报率高', '阈值不合适', '调阈值'],
               ['服务崩溃', '线程问题', '查日志+monitor']])

    doc.add_heading('八、验收标准', 1)
    add_table(doc, ['项目', '标准', '方法'],
              [['通信', '心跳持续', 'hardware_test.py'],
               ['准确', '误报<1%漏报<5%', '100次测试'],
               ['延迟', '<150ms', 'profiler'],
               ['稳定', '24h无崩溃', 'monitor'],
               ['安全', '故障禁止翻车', '拔网线测试'],
               ['恢复', '5秒重启', '杀进程验证']])

    # Save
    output = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'docs', '翻车机积煤检测系统_部署报告_V3.0.docx')
    doc.save(output)
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '_doc_result.txt'), 'w') as f:
        f.write(f'OK: {output}\nSize: {os.path.getsize(output)} bytes')


if __name__ == '__main__':
    main()
