"""Generate full edge computing plan Word doc (Chinese)"""
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
    setup(doc)

    # Cover
    for _ in range(4):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run('翻车机积煤检测系统 — 分布式边缘计算整体方案')
    r.font.size = Pt(22)
    r.bold = True
    r.font.color.rgb = RGBColor(0x1A, 0x3C, 0x6E)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run('替代现有集中式方案 | 2026-04-09').font.size = Pt(12)
    doc.add_page_break()

    # 1
    doc.add_heading('一、现有问题', 1)
    T(doc, ['问题', '影响', '根因'],
      [['单点故障', '工控机宕机全停', '集中式'],
       ['pypylon冲突', '多相机枚举互相干扰', 'GigE全局协议'],
       ['PLC标签争抢', '多漏斗争抢同一组标签', 'L1架构限制'],
       ['CV局限', '光照/阴影/锈斑敏感', '无深度学习'],
       ['扩展困难', '增加设备需改代码', '集中式设计']])

    # 2
    doc.add_heading('二、新方案对比', 1)
    T(doc, ['维度', '现有(集中式)', '新方案(分布式边缘)'],
      [['架构', '1台工控机', '每漏斗1台Jetson'],
       ['算法', '传统CV(阈值)', 'YOLO26+CV融合'],
       ['推理', '51ms(CPU)', '8-15ms(GPU TensorRT)'],
       ['相机', 'GigE网络(冲突)', 'USB3直连(无冲突)'],
       ['故障隔离', '一坏全停', '独立不影响'],
       ['PLC标签', '共享(冲突)', '每漏斗独立'],
       ['扩展', '需改代码', '即插即用']])

    # 3
    doc.add_heading('三、硬件配置', 1)
    doc.add_heading('3.1 单节点', 2)
    T(doc, ['组件', '型号', '价格'],
      [['边缘计算', 'Jetson Orin Nano 8GB', '2,500元'],
       ['相机', 'Basler acA1600-60gm(复用)', '4,300元'],
       ['补光灯', 'LED工业补光灯', '1,000元'],
       ['防护壳', 'IP65+散热', '500元'],
       ['电源+线缆', '12V+Cat6+USB3', '350元'],
       ['单节点合计', '', '8,650元']])
    doc.add_heading('3.2 整机(5漏斗)', 2)
    T(doc, ['项目', '数量', '小计'],
      [['边缘节点', '5', '43,250'],
       ['PLC(1769-L16ER)', '1', '15,000'],
       ['交换机+辅材', '1', '1,000'],
       ['合计', '', '59,250元']])

    # 4
    doc.add_heading('四、软件设计', 1)
    T(doc, ['模块', '功能', '复用'],
      [['相机驱动', 'pypylon USB3/GigE', '100%'],
       ['YOLO检测', 'YOLO26n TensorRT', '新增'],
       ['传统CV', '格栅计数+面积(备用)', '100%'],
       ['融合判定', 'YOLO+CV双模式投票', '新增'],
       ['PLC通信', 'pycomm3', '100%'],
       ['采集窗口', 'PLC触发+投票', '90%'],
       ['安全信号', 'can_tip三条件', '100%'],
       ['状态API', '轻量HTTP', '重写'],
       ['看门狗', 'systemd服务', '新增']])

    # 5
    doc.add_heading('五、YOLO模型', 1)
    doc.add_heading('5.1 检测类别', 2)
    T(doc, ['类别', '含义', '动作'],
      [['grid_visible', '格栅可见', '正常'],
       ['coal_cover', '积煤覆盖', '报警'],
       ['shadow', '阴影(非煤)', '忽略'],
       ['rust', '锈斑(非煤)', '忽略'],
       ['foreign_object', '异物', '报警']])
    doc.add_heading('5.2 双模式融合', 2)
    T(doc, ['YOLO', 'CV', '融合', '置信度'],
      [['有煤', '有煤', '有煤', 'HIGH'],
       ['有煤', '无煤', '有煤', 'MEDIUM'],
       ['无煤', '有煤', '人工确认', 'LOW'],
       ['无煤', '无煤', '无煤', 'HIGH'],
       ['YOLO失败', '任意', '用CV', '降级']])

    # 6
    doc.add_heading('六、PLC改造', 1)
    T(doc, ['标签', '类型', '说明'],
      [['FunnelN_CanTip(x5)', 'BOOL', '各漏斗可翻转'],
       ['FunnelN_FaultCode(x5)', 'DINT', '各漏斗故障码'],
       ['FunnelN_Heartbeat(x5)', 'DINT', '各漏斗心跳'],
       ['FunnelN_Online(x5)', 'BOOL', '各漏斗在线'],
       ['All_CanTip', 'BOOL', '全部允许才翻车'],
       ['Allow_Tip', 'BOOL', '最终输出']])
    doc.add_paragraph('Allow_Tip = All_CanTip AND 所有心跳正常 AND 无故障')

    # 7
    doc.add_heading('七、安全设计', 1)
    T(doc, ['故障', 'Jetson行为', 'PLC行为'],
      [['Jetson宕机', '心跳停', '该漏斗CanTip=False'],
       ['相机断开', 'fault_code=1', 'CanTip=False'],
       ['YOLO失败', '回退CV', '继续检测'],
       ['全部Jetson坏', '全部心跳停', 'Allow_Tip=False']])
    doc.add_paragraph('can_tip = (coal_present is False) and (not need_manual) and (fault_code == 0)')

    # 8
    doc.add_heading('八、成本对比', 1)
    T(doc, ['', '现有', '新方案', '差异'],
      [['硬件', '50,000', '59,250', '+18.5%'],
       ['推理', '51ms', '8-15ms', '3-6倍快'],
       ['准确性', '中', '高', '大幅提升'],
       ['故障隔离', '无', '有', '根本改进'],
       ['功耗', '65W', '75W', '+10W']])
    p = doc.add_paragraph()
    r = p.add_run('结论：多投18.5%成本，换来3-6倍速度+故障隔离+YOLO准确性。')
    r.bold = True

    # 9
    doc.add_heading('九、实施计划(12周)', 1)
    T(doc, ['阶段', '周期', '内容'],
      [['Phase 1', '1-2周', '采购1台Jetson，移植代码，验证USB3'],
       ['Phase 2', '3-4周', '安装补光灯，拍550张图，标注'],
       ['Phase 3', '5周', '训练YOLO26n，TensorRT转换'],
       ['Phase 4', '6周', '双模式融合验证'],
       ['Phase 5', '7-8周', 'PLC改造，1#漏斗试运行'],
       ['Phase 6', '9-12周', '采购剩余4台，全面上线'],
       ['Phase 7', '13周', '去掉工控机，迁移完成']])

    # 10
    doc.add_heading('十、迁移策略(零停机)', 1)
    T(doc, ['步骤', '架构', '风险'],
      [['当前', '工控机+5相机', '已稳定'],
       ['步骤1', '工控机(4路)+Jetson(1路)并行', '零'],
       ['步骤2', '对比1周', '零'],
       ['步骤3', 'Jetson接入PLC', '低'],
       ['步骤4', '逐台替换', '低'],
       ['步骤5', '去掉工控机', '低']])
    doc.add_paragraph('任何步骤可回退到工控机方案。')

    # 11
    doc.add_heading('十一、风险与缓解', 1)
    T(doc, ['风险', '缓解'],
      [['散热(高温粉尘)', 'IP65外壳+散热片+温度监控'],
       ['YOLO不够准', 'CV双模式备用'],
       ['Jetson故障', 'PLC心跳检测+CanTip=False'],
       ['USB相机不稳', '自动重连+GigE备选'],
       ['训练数据不足', '先用CV积累数据']])

    # 12
    doc.add_heading('十二、验收标准', 1)
    T(doc, ['项目', '标准', '方法'],
      [['通信', '心跳持续递增', 'PLC监控'],
       ['准确', '误报<1% 漏报<5%', '100次测试'],
       ['速度', 'YOLO<20ms', 'profiler'],
       ['隔离', '拔1台不影响其他', '现场测试'],
       ['重连', '断电30秒内恢复', '断电测试'],
       ['安全', '故障→Allow_Tip=False', '拔网线'],
       ['稳定', '48小时无崩溃', '监控'],
       ['温度', '<70度', '传感器']])

    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'docs', 'edge_plan_full_cn_v3.0.docx')
    doc.save(out)
    print(f'OK: {out}')
    print(f'Size: {os.path.getsize(out)} bytes')

if __name__ == '__main__':
    main()
