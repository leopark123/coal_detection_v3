"""生成项目全面分析报告 Word 文档"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn


def setup(doc):
    s = doc.styles['Normal']
    s.font.name = 'Microsoft YaHei'; s.font.size = Pt(10.5)
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
        for r in c.paragraphs[0].runs: r.bold = True; r.font.size = Pt(9)
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            t.rows[ri+1].cells[ci].text = str(val)
    doc.add_paragraph()

def B(doc, text):
    p = doc.add_paragraph()
    r = p.add_run(text); r.bold = True; return p

def main():
    doc = Document()
    setup(doc)

    # ═══ Cover ═══
    for _ in range(4): doc.add_paragraph()
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run('翻车机积煤检测系统 V3.0'); r.font.size = Pt(26); r.bold = True; r.font.color.rgb = RGBColor(0x1A,0x3C,0x6E)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run('项目全面分析报告'); r.font.size = Pt(18); r.font.color.rgb = RGBColor(0x44,0x72,0xC4)
    doc.add_paragraph()
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run('用途：上线评审 / 技术交接 / 自我复盘').font.size = Pt(12)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run('2026-04-05').font.size = Pt(12)
    doc.add_page_break()

    # ═══ 目录 ═══
    doc.add_heading('目录', 1)
    toc = ['一、项目成果总结','二、系统架构分析','三、安全连锁完整性','四、代码质量评估',
           '五、稳定性验证报告','六、漏洞修复全记录','七、已知限制与风险',
           '八、部署运维手册','九、下一步路线图','十、经验教训']
    for t_item in toc: doc.add_paragraph(t_item, style='List Number')
    doc.add_page_break()

    # ═══ 一、项目成果总结 ═══
    doc.add_heading('一、项目成果总结', 1)
    doc.add_paragraph('从零搭建了一套工业级计算机视觉安全连锁系统，实现从相机采集到PLC控制翻车机的完整闭环。')
    doc.add_heading('1.1 核心指标', 2)
    T(doc, ['指标','值'],
      [['代码量','42个Python文件, 12,245行'],
       ['前端','6个HTML模板, 2,205行 + CSS 245行'],
       ['测试','10个测试文件, 119个测试函数, 116 passed'],
       ['安全修复','35个漏洞(6 CRITICAL+13 HIGH+8 MEDIUM+8审查轮)'],
       ['稳定运行','49.4小时无崩溃(修复前每2小时崩溃)'],
       ['PLC集成','19个标签, 10个Rung梯形图, 2700+采集周期'],
       ['文档','README+CLAUDE.md+部署报告+整改记录+3份CODEX提示词']])

    doc.add_heading('1.2 交付物清单', 2)
    T(doc, ['类别','文件','说明'],
      [['核心程序','web/unified_app.py','统一Web应用(FastAPI)'],
       ['检测算法','algo/detector.py + device_detector.py','ECC+CLAHE+双因素+三级置信度'],
       ['PLC通信','plc/allen_bradley.py','6标签写入+心跳+重连'],
       ['采集控制','core/capture_window.py','PLC触发+投票+安全上限'],
       ['状态管理','web/state_manager.py','后台worker+多机管理+故障收集'],
       ['相机驱动','drivers/basler_camera.py','GigE+Mono8→BGR+自动重连'],
       ['运维工具','start_production.bat','看门狗自动重启'],
       ['监控工具','tools/system_monitor.py','内存/线程/PLC/采集监控'],
       ['部署报告','docs/*.docx','部署+整改+分析 Word文档']])
    doc.add_page_break()

    # ═══ 二、系统架构分析 ═══
    doc.add_heading('二、系统架构分析', 1)
    doc.add_heading('2.1 三级层次架构', 2)
    doc.add_paragraph('服务器(工控机) → 翻车机(PLC) → 漏斗(相机+格栅)')
    T(doc, ['层级','组件','数量','说明'],
      [['服务器','StateManager','1','中央状态管理器，管理所有翻车机'],
       ['翻车机','MachineState+PLC','N','每台独立PLC，可动态增减'],
       ['漏斗','FunnelState+Camera+Detector','M/台','每个漏斗独立相机和检测器']])

    doc.add_heading('2.2 线程模型', 2)
    T(doc, ['线程/池','Workers','职责','超时'],
      [['主线程(asyncio)','1','FastAPI事件循环，WebSocket，HTTP','—'],
       ['_grab_executor','4','camera.grab() 相机采集','10秒'],
       ['_detect_executor','8','detect_frame() 检测算法','10秒'],
       ['bg-detect-*','每漏斗1个','后台检测worker(独立于WebSocket)','—'],
       ['plc-heartbeat','每PLC 1个','500ms心跳递增','2秒锁超时'],
       ['PLC _io_lock','—','所有PLC读写互斥','5秒']])

    doc.add_heading('2.3 数据流', 2)
    doc.add_paragraph('PLC触发 → 后台worker抓帧 → 检测算法 → 窗口投票 → PLC写入')
    doc.add_paragraph('WebSocket ← 只读 last_frame/last_result（纯展示，不驱动检测）')

    doc.add_heading('2.4 采集时序', 2)
    doc.add_paragraph('翻车机回位 → PLC延时10秒 → PLC写CaptureCmd=1 → 服务器采集+检测')
    doc.add_paragraph('→ 多帧投票 → 结果写PLC → PLC复位 → 回位消失立即停止')
    doc.add_page_break()

    # ═══ 三、安全连锁完整性 ═══
    doc.add_heading('三、安全连锁完整性', 1)
    doc.add_heading('3.1 安全信号链路', 2)
    T(doc, ['步骤','组件','安全保护'],
      [['1.抓帧','BaslerCamera','未匹配IP拒绝连接(不回退第一台)'],
       ['2.画质检','detector._check_quality','分区评估+对比度+自适应模糊(不一刀切)'],
       ['3.检测','device_detector.detect_device','异常分支fail-safe(fault_code=3)'],
       ['4.投票','capture_window._finalize_window','故障帧排除+全故障→LOW+安全上限零帧fail-safe'],
       ['5.写PLC','allen_bradley.send_detection_result','can_tip=is False严格判断+fault_code检查'],
       ['6.PLC判','梯形图Rung4','Alive+CanTip+ResultValid+FaultCode=0四条件'],
       ['7.停用','Vision_Enable=False','PLC强制Allow_Tip=1+服务器停止采集']])

    doc.add_heading('3.2 核心安全公式', 2)
    doc.add_paragraph('can_tip = (coal_present is False) and (not need_manual) and (fault_code == 0)')
    doc.add_paragraph('result_valid = confidence in ("HIGH","MEDIUM") and (fault_code == 0) and (coal_present is not None)')
    doc.add_paragraph('Allow_Tip = Vision_Enable=0 OR (Alive AND CanTip AND Valid AND Fault=0)')
    doc.add_page_break()

    # ═══ 四、代码质量评估 ═══
    doc.add_heading('四、代码质量评估', 1)
    doc.add_heading('4.1 代码统计', 2)
    T(doc, ['目录','文件数','行数','职责'],
      [['algo/','7','1,569','检测算法'],
       ['core/','6','2,156','采集控制+双缓冲'],
       ['drivers/','4','891','相机+Mock驱动'],
       ['plc/','2','690','PLC通信'],
       ['web/','8','2,936','Web应用+状态管理'],
       ['config/','3','460','配置管理'],
       ['tools/','7','1,663','运维工具'],
       ['tests/','11','1,880','测试'],
       ['合计','42+6模板','12,245+2,205','—']])

    doc.add_heading('4.2 测试覆盖', 2)
    T(doc, ['测试类型','文件','测试数','覆盖内容'],
      [['算法单元','test_detector.py','20','检测逻辑、阈值、边界'],
       ['集成测试','test_integration.py','20','端到端流程'],
       ['性能测试','test_performance.py','12','延迟、吞吐量'],
       ['Web契约','test_web_routes_contract.py','3','路由存在性'],
       ['Web通用','test_web_common.py','9','WebSocket推流'],
       ['配置加载','test_devices_config.py+config_env','13','YAML加载、环境切换'],
       ['状态管理','test_state_manager.py','13','增删翻车机/漏斗'],
       ['管理API','test_admin_api.py','18','CRUD+鉴权'],
       ['统一路由','test_unified_app.py','11','路由契约'],
       ['合计','10文件','119','116 passed']])

    doc.add_heading('4.3 技术债', 2)
    T(doc, ['技术债','影响','优先级'],
      [['L1:采集控制器per-funnel','多相机时PLC标签争抢','P0(接第2台相机前)'],
       ['旧Web应用未删除(app.py等)','代码冗余','P2'],
       ['DetectionResult仍有dict-like方法','接口不清晰','P3'],
       ['detect_process.py旧代码','多进程模式未维护','P3']])
    doc.add_page_break()

    # ═══ 五、稳定性验证报告 ═══
    doc.add_heading('五、稳定性验证报告', 1)
    doc.add_heading('5.1 长时间运行数据', 2)
    T(doc, ['指标','修复前','修复后'],
      [['连续运行','每2小时崩溃','49.4+小时无崩溃'],
       ['内存','持续增长','177-214MB稳定'],
       ['线程','可能泄漏','63-79稳定(含5漏斗worker)'],
       ['采集周期','—','2700+次正常循环'],
       ['PLC心跳','—','连续递增无中断'],
       ['日志错误(funnel-1)','—','0条(今日)']])

    doc.add_heading('5.2 崩溃原因与修复', 2)
    T(doc, ['根因','C4修复方案'],
      [['线程池共用→饥饿','三个独立线程池(grab/detect/default)'],
       ['_io_lock无超时→死锁','全部acquire(timeout=5s)'],
       ['WebSocket和worker并发grab','WebSocket改纯展示模式'],
       ['tick()多线程驱动','只由后台worker驱动']])
    doc.add_page_break()

    # ═══ 六、漏洞修复全记录 ═══
    doc.add_heading('六、漏洞修复全记录', 1)
    T(doc, ['轮次','编号','严重度','问题简述'],
      [['初始','C1-C6','CRITICAL×6','dict继承/心跳竞态/None允许翻车/线程饥饿/画质丢失/无人检测'],
       ['初始','H1-H13','HIGH×13','grid_mask/置信度/PLC重连/WS不退出/启停无鉴权/等13项'],
       ['初始','M1-M8','MEDIUM×8','reset/健康检查/历史/阈值/画质/投票等8项'],
       ['R1审查','F1-F4','FAIL×4','相机回退/异常无fault/锁超时/WS超时'],
       ['R2审查','F1-F2+W1-W2','4项','零帧fail-safe/总览WS/atexit/heartbeat废弃'],
       ['','','合计35项','']])

    doc.add_heading('6.1 三轮审查过程', 2)
    doc.add_paragraph('第一轮(R1)：静态审查发现4个FAIL → 修复 → 第二轮(R2)：验证修复+发现遗漏4项 → 修复 → 第三轮(R3)：最终验证34项检查点')
    doc.add_page_break()

    # ═══ 七、已知限制与风险 ═══
    doc.add_heading('七、已知限制与风险', 1)
    T(doc, ['编号','限制','影响','接受条件','改进时间'],
      [['L1','采集控制器per-funnel','多漏斗争抢PLC标签','单相机规避','接第2台相机前'],
       ['L2','配置变更非原子','保存失败内存已变','错误提示明确','V3.1'],
       ['L3','运行时add不区分ImportError','极罕见','启动时已验证','V3.1'],
       ['L4','启动中途资源残留','OS级回收','进程退出清理','V3.1'],
       ['L5','Token无过期','泄露长期有效','内网+改密码','V3.2'],
       ['L6','WebSocket无鉴权','可看视频','内网风险低','V3.2'],
       ['L7','报警不持久化','重启丢失','日志可追溯','V3.2'],
       ['L8','images无自动清理','磁盘满','手动清理','V3.1'],
       ['L9','PLC被挤掉不恢复','需重启','正常不出现','—'],
       ['L10','单进程5秒空窗','看门狗重启','PLC 2秒保护','—']])
    doc.add_page_break()

    # ═══ 八、部署运维手册 ═══
    doc.add_heading('八、部署运维手册', 1)
    doc.add_heading('8.1 硬件清单', 2)
    T(doc, ['序号','设备','数量','说明'],
      [['1','工控机(Win10+Python3.10+)','1台','运行检测服务'],
       ['2','Basler acA1600-60gm','N台','每漏斗1台'],
       ['3','AB 1769-L16ER/B','N台','每翻车机1台PLC'],
       ['4','千兆工业交换机','1台','所有设备互联'],
       ['5','LED补光灯','N台','每漏斗1台'],
       ['6','Cat6网线+12V电源','若干','按现场配置']])

    doc.add_heading('8.2 部署15步', 2)
    steps = ['安装Python+依赖(requirements.txt+pypylon+pycomm3)',
             '安装Basler Pylon SDK', '复制项目到D:\\coal_detection_project',
             '配置devices.yaml(翻车机/漏斗/IP)', '设置管理员密码(ADMIN_PASSWORD环境变量)',
             '测试硬件(python tools/hardware_test.py)',
             'PLC编程(Studio 5000, 10个Rung+3个模拟Rung)',
             '联调测试(python tools/integration_test_hw.py)',
             '安装补光灯并调光', '拍基准图(config/reference.jpg)',
             '标定格栅ROI(config/grid_manual.yaml)', '调检测阈值',
             '安装开机自启(install_autostart.bat)',
             '启动服务(start_production.bat)',
             '启动监控(start_monitor.bat)']
    for s in steps: doc.add_paragraph(s, style='List Number')

    doc.add_heading('8.3 故障排查', 2)
    T(doc, ['故障','原因','排查'],
      [['相机连不上','IP/网线/被占','ping+等3秒GigE超时'],
       ['PLC连不上','IP/RSLinx','ping+检查驱动'],
       ['画面全黑','无补光灯','检查灯+调曝光'],
       ['误报率高','阈值不合适','调GRID_VISIBLE_THRESHOLD'],
       ['服务崩溃','内存/线程','查unified_*.log+monitor'],
       ['心跳超时','网络中断','检查网线+reconnect日志']])
    doc.add_page_break()

    # ═══ 九、下一步路线图 ═══
    doc.add_heading('九、下一步路线图', 1)
    T(doc, ['阶段','时间','内容','前置条件'],
      [['Phase 0','现在','补光灯采购安装','—'],
       ['Phase 1','灯到后1-2周','装灯+标定+调参+真实测试','补光灯到位'],
       ['Phase 2','调参后1周','并行验证(只记录不联锁)','准确率达标'],
       ['Phase 3','验证通过','正式上线7×24运行','误报率<1%'],
       ['Phase 4','上线1月后','接第2台相机+L1架构改进','稳定运行'],
       ['Phase 5','3月后','积累数据+YOLO模型训练','500+标注图片'],
       ['Phase 6','YOLO达标','双模式融合(CV+YOLO)','GPU采购']])

    doc.add_heading('9.1 L1架构改进（Phase 4必做）', 2)
    doc.add_paragraph('将CaptureWindowController从FunnelState提升到MachineState级别，每台翻车机唯一控制器读写PLC标签。预计2-3天。')
    doc.add_page_break()

    # ═══ 十、经验教训 ═══
    doc.add_heading('十、经验教训', 1)
    doc.add_heading('10.1 设计决策回顾', 2)
    T(doc, ['决策','结果','教训'],
      [['PLC控制采集时序(不是服务器)','正确','工业现场时序判断应由PLC完成'],
       ['DEV/PROD虚实分离','正确','Mock驱动让无硬件开发成为可能'],
       ['WebSocket推流绑定检测','错误','后来改为后台worker独立驱动'],
       ['全局mean画质判断','错误','后来改为分区+对比度+自适应'],
       ['dict继承DetectionResult','错误','后来移除，应一开始用纯dataclass'],
       ['单线程池共用','错误','导致C4(每2h崩溃)，改为三个独立池']])

    doc.add_heading('10.2 踩过的坑', 2)
    T(doc, ['坑','代价','避免方法'],
      [['相机型号660gm vs 60gm','全项目grep替换','确认硬件型号后立即更新所有文档'],
       ['GigE心跳超时默认10秒','每次重启等30秒','一开始就设3秒'],
       ['PycommP不是线程安全的','C4崩溃','所有PLC读写加锁+超时'],
       ['画面全黑允许翻车','安全漏洞','质量失败必须设fault_code'],
       ['没人看页面不检测','CRITICAL漏洞','检测必须独立于展示层'],
       ['多漏斗争抢PLC标签','架构限制','PLC标签应per-machine不是per-funnel']])

    doc.add_heading('10.3 做对的事', 2)
    doc.add_paragraph('1. 安全优先原则贯穿始终：宁可漏报不可误报', style='List Bullet')
    doc.add_paragraph('2. 三轮CODEX审查：每轮修复+验证，累计发现35个漏洞', style='List Bullet')
    doc.add_paragraph('3. 长时间稳定性测试：49.4小时实测验证', style='List Bullet')
    doc.add_paragraph('4. 整改文档完整记录：每个漏洞有编号、修复方案、日期', style='List Bullet')
    doc.add_paragraph('5. PLC梯形图与软件同步设计：安全连锁双重保护', style='List Bullet')

    # Save
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'docs', 'project_analysis_report_v3.0.docx')
    doc.save(out)
    print(f'OK: {out}')
    print(f'Size: {os.path.getsize(out)} bytes')


if __name__ == '__main__':
    main()
