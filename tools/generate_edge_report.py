"""生成分布式边缘计算方案 Word 文档"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

def setup(doc):
    s=doc.styles['Normal']; s.font.name='Microsoft YaHei'; s.font.size=Pt(10.5)
    s.element.rPr.rFonts.set(qn('w:eastAsia'),'Microsoft YaHei')
    for i in range(1,4):
        h=doc.styles[f'Heading {i}']; h.font.name='Microsoft YaHei'
        h.element.rPr.rFonts.set(qn('w:eastAsia'),'Microsoft YaHei')
        h.font.color.rgb=RGBColor(0x1A,0x3C,0x6E)

def T(doc,headers,rows):
    t=doc.add_table(rows=1+len(rows),cols=len(headers))
    t.style='Light Grid Accent 1'; t.alignment=WD_TABLE_ALIGNMENT.CENTER
    for i,h in enumerate(headers):
        c=t.rows[0].cells[i]; c.text=h
        for r in c.paragraphs[0].runs: r.bold=True; r.font.size=Pt(9)
    for ri,row in enumerate(rows):
        for ci,val in enumerate(row): t.rows[ri+1].cells[ci].text=str(val)
    doc.add_paragraph()

def main():
    doc = Document()
    setup(doc)

    # Cover
    for _ in range(4): doc.add_paragraph()
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run('Distributed Edge Computing Plan'); r.font.size=Pt(26); r.bold=True; r.font.color.rgb=RGBColor(0x1A,0x3C,0x6E)
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run('Plan C - YOLO + Jetson'); r.font.size=Pt(16); r.font.color.rgb=RGBColor(0x44,0x72,0xC4)
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.add_run('2026-04-08').font.size=Pt(12)
    doc.add_page_break()

    doc.add_heading('Overview',1)
    doc.add_paragraph('Each funnel gets an independent Jetson + camera + light, performing capture, YOLO detection, and PLC write independently.')
    T(doc,['Dimension','Current (Centralized)','Plan C (Distributed Edge)'],
      [['Compute','1 IPC','1 Jetson per funnel'],
       ['Algorithm','Traditional CV','YOLO26 + CV fusion'],
       ['Inference','~51ms','~8-15ms (TensorRT)'],
       ['Fault isolation','One fails all stop','Independent'],
       ['Robustness','Low (threshold)','High (deep learning)']])

    doc.add_heading('Hardware per Node',1)
    T(doc,['Component','Model','Price','Notes'],
      [['Edge compute','Jetson Orin Nano 8GB','2500 CNY','40 TOPS, 15W'],
       ['Camera','Basler acA1600-60gm','4300 CNY','Existing, USB3/GigE'],
       ['Light','LED industrial','1000 CNY','PLC controlled'],
       ['Enclosure','IP65 industrial','500 CNY','Dust/water proof'],
       ['Power','12V/5A','200 CNY','Camera + Jetson'],
       ['Cable','Cat6','100 CNY','To switch'],
       ['Total per node','','8600 CNY','']])

    doc.add_heading('Total Cost (1 tipper, 5 funnels)',1)
    T(doc,['Item','Qty','Unit','Total'],
      [['Edge nodes','5','8600','43000'],
       ['PLC (1769-L16ER)','1','15000','15000'],
       ['Switch','1','500','500'],
       ['Grand total','','','58500 CNY']])

    doc.add_heading('PLC Tag Design',1)
    T(doc,['Tag','Type','Description'],
      [['FunnelN_CanTip','BOOL','Funnel N can tip'],
       ['FunnelN_FaultCode','DINT','Funnel N fault code'],
       ['FunnelN_ResultValid','BOOL','Funnel N result valid'],
       ['FunnelN_Heartbeat','DINT','Funnel N heartbeat (500ms)'],
       ['FunnelN_Online','BOOL','Funnel N online'],
       ['All_CanTip','BOOL','All funnels allow = tip'],
       ['Any_Fault','BOOL','Any funnel has fault'],
       ['Allow_Tip','BOOL','Final allow tip']])

    doc.add_heading('YOLO Model Deployment',1)
    T(doc,['Class','Meaning','Action'],
      [['grid_visible','Grid hole visible','Normal'],
       ['coal_cover','Coal coverage','Alarm'],
       ['shadow','Shadow (not coal)','Ignore'],
       ['rust','Rust (not coal)','Ignore'],
       ['foreign_object','Foreign object','Alarm']])

    doc.add_heading('Dual Mode Fusion',1)
    T(doc,['YOLO','CV','Fusion','Confidence'],
      [['Coal','Coal','Coal','HIGH'],
       ['Coal','No coal','Coal','MEDIUM'],
       ['No coal','Coal','Manual confirm','LOW'],
       ['No coal','No coal','No coal','HIGH'],
       ['YOLO fail','Any','Use CV only','Degraded']])

    doc.add_heading('Implementation Roadmap',1)
    T(doc,['Phase','Time','Content','Deliverable'],
      [['1','Week 1-2','Buy 1 Jetson, port code','Single node verified'],
       ['2','Week 3-4','Collect 500+ images, train YOLO','coal_detect.engine'],
       ['3','Week 5-6','TensorRT deploy + fusion','Dual mode verified'],
       ['4','Week 7-8','PLC tag rework, funnel 1 trial','Single funnel online'],
       ['5','Week 9-12','Buy remaining 4, all online','Full system online']])

    doc.add_heading('Risk Mitigation',1)
    T(doc,['Risk','Impact','Mitigation'],
      [['Jetson overheating','Throttle','IP65 enclosure + heatsink'],
       ['YOLO inaccurate','False alarms','Keep CV as fallback'],
       ['Jetson failure','1 funnel down','PLC heartbeat, CanTip=False'],
       ['USB camera unstable','Capture loss','Keep GigE as backup'],
       ['pycomm3 on ARM','PLC comm fail','Pure Python, should work']])

    doc.add_heading('Cost Comparison',1)
    T(doc,['','Current','Plan C','Delta'],
      [['Hardware','50000 CNY','58500 CNY','+17%'],
       ['Inference','51ms','8-15ms','3-6x faster'],
       ['Accuracy','Medium','High','Major improvement'],
       ['Fault isolation','All stop','Independent','Fundamental'],
       ['Power','65W','75W','+10W']])

    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'docs', 'edge_computing_plan_v3.0.docx')
    doc.save(out)
    print(f'OK: {out}')
    print(f'Size: {os.path.getsize(out)} bytes')

if __name__ == '__main__':
    main()
