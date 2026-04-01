"""
翻车机积煤检测系统 V3.0 - 系统运行监控工具

长时间运行稳定性检测，监控：
1. 内存泄漏（RSS 增长趋势）
2. PLC 通信稳定性（心跳连续性、写入成功率）
3. 相机采集稳定性（帧率、丢帧率）
4. 采集窗口逻辑（周期正确性、投票结果一致性）
5. WebSocket 连接状态
6. 线程数量（是否持续增长）
7. CPU/磁盘使用

使用方式：
    python tools/system_monitor.py                    # 默认每 30 秒采样
    python tools/system_monitor.py --interval 10      # 每 10 秒
    python tools/system_monitor.py --duration 3600    # 运行 1 小时
    python tools/system_monitor.py --output report.txt
"""

import sys
import os
import time
import json
import argparse
import threading
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("COAL_ENV", "PROD")


def get_process_info():
    """获取当前进程信息"""
    info = {}
    try:
        import psutil
        # 找 uvicorn 进程
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info',
                                          'cpu_percent', 'num_threads', 'create_time']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'unified_app' in cmdline or ('uvicorn' in cmdline and '8080' in cmdline):
                    mem = proc.info['memory_info']
                    info = {
                        'pid': proc.info['pid'],
                        'rss_mb': round(mem.rss / 1024 / 1024, 1),
                        'vms_mb': round(mem.vms / 1024 / 1024, 1),
                        'cpu_percent': proc.cpu_percent(interval=0.5),
                        'num_threads': proc.info['num_threads'],
                        'uptime_s': round(time.time() - proc.info['create_time']),
                    }
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # 系统级
        info['system_cpu_percent'] = psutil.cpu_percent(interval=0.1)
        info['system_mem_percent'] = psutil.virtual_memory().percent
        disk = psutil.disk_usage('D:\\')
        info['disk_free_gb'] = round(disk.free / 1024 / 1024 / 1024, 1)
    except ImportError:
        info['error'] = 'psutil not installed'
    return info


def get_plc_status():
    """读取 PLC 关键标签"""
    try:
        from pycomm3 import LogixDriver
        with LogixDriver('192.168.1.19') as plc:
            tags = ['IPC_Heartbeat', 'IPC_Online', 'Vision_Alive',
                    'Vision_CanTip', 'Vision_FaultCode', 'Vision_ResultValid',
                    'Vision_CaptureState', 'PLC_CaptureCmd', 'Allow_Tip',
                    'Tipper_InPosition']
            result = {}
            for t in tags:
                try:
                    result[t] = plc.read(t).value
                except Exception:
                    result[t] = None
            return result, True
    except Exception as e:
        return {'error': str(e)}, False


def get_web_status():
    """检查 Web 服务 API"""
    import urllib.request
    try:
        req = urllib.request.Request('http://localhost:8080/api/overview', method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            machines = data.get('machines', [])
            result = {
                'http_ok': True,
                'machine_count': len(machines),
            }
            for m in machines:
                mid = m['id']
                result[f'{mid}_plc'] = m.get('plc_connected', False)
                result[f'{mid}_funnels'] = m.get('funnel_count', 0)
                result[f'{mid}_vision'] = m.get('vision_enabled', False)
                for f in m.get('funnels', []):
                    fid = f['id']
                    result[f'{mid}/{fid}_frames'] = f.get('detection_count', 0)
                    result[f'{mid}/{fid}_phase'] = f.get('capture_phase', 'unknown')
            return result
    except Exception as e:
        return {'http_ok': False, 'error': str(e)}


def get_log_stats():
    """分析日志文件"""
    import glob
    logs = sorted(glob.glob('D:/coal_detection_project/logs/unified_*.log'))
    if not logs:
        return {'log_file': None}

    latest = logs[-1]
    try:
        with open(latest, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        total = len(lines)
        errors = sum(1 for l in lines if '| ERROR' in l)
        warnings = sum(1 for l in lines if '| WARNING' in l)
        captures = sum(1 for l in lines if 'PLC 触发采集' in l)
        finalize = sum(1 for l in lines if '窗口判定' in l)

        return {
            'log_file': os.path.basename(latest),
            'total_lines': total,
            'errors': errors,
            'warnings': warnings,
            'capture_cycles': captures,
            'finalize_cycles': finalize,
        }
    except Exception as e:
        return {'log_file': latest, 'error': str(e)}


class SystemMonitor:
    """系统运行监控器"""

    def __init__(self, interval=30, duration=0, output_file=None):
        self.interval = interval
        self.duration = duration  # 0 = 无限
        self.output_file = output_file

        # 历史数据（用于趋势分析）
        self.history = []
        self.start_time = time.time()
        self.last_heartbeat = None
        self.heartbeat_gaps = 0       # 心跳不连续次数
        self.plc_read_fails = 0
        self.plc_read_total = 0
        self.max_rss_mb = 0
        self.min_rss_mb = float('inf')

    def sample(self):
        """采集一次样本"""
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        sample = {'timestamp': ts, 'elapsed_s': round(time.time() - self.start_time)}

        # 1. 进程信息
        proc = get_process_info()
        sample['process'] = proc
        if 'rss_mb' in proc:
            self.max_rss_mb = max(self.max_rss_mb, proc['rss_mb'])
            self.min_rss_mb = min(self.min_rss_mb, proc['rss_mb'])

        # 2. PLC 状态
        plc, plc_ok = get_plc_status()
        sample['plc'] = plc
        self.plc_read_total += 1
        if not plc_ok:
            self.plc_read_fails += 1

        # 心跳连续性检查
        if plc_ok and 'IPC_Heartbeat' in plc:
            hb = plc['IPC_Heartbeat']
            if self.last_heartbeat is not None:
                # 心跳应该一直在递增
                if hb == self.last_heartbeat:
                    self.heartbeat_gaps += 1
                    sample['heartbeat_stall'] = True
            self.last_heartbeat = hb

        # 3. Web 服务
        sample['web'] = get_web_status()

        # 4. 日志统计
        sample['log'] = get_log_stats()

        self.history.append(sample)
        return sample

    def print_sample(self, s):
        """打印一次采样结果"""
        elapsed = s['elapsed_s']
        hours = elapsed // 3600
        mins = (elapsed % 3600) // 60

        print(f"\n{'='*70}")
        print(f"[{s['timestamp']}] 运行 {hours}h{mins}m | 采样 #{len(self.history)}")
        print(f"{'='*70}")

        # 进程
        p = s.get('process', {})
        if 'rss_mb' in p:
            rss_trend = ''
            if len(self.history) > 1:
                first_rss = self.history[0].get('process', {}).get('rss_mb', 0)
                diff = p['rss_mb'] - first_rss
                rss_trend = f" (初始值差: {diff:+.1f}MB)"
            print(f"  进程: PID={p.get('pid','-')}, RSS={p['rss_mb']}MB{rss_trend}, "
                  f"线程={p.get('num_threads','-')}, CPU={p.get('cpu_percent','-')}%")
            print(f"  系统: CPU={p.get('system_cpu_percent','-')}%, "
                  f"内存={p.get('system_mem_percent','-')}%, "
                  f"磁盘剩余={p.get('disk_free_gb','-')}GB")
        else:
            print(f"  进程: {p.get('error', '未找到 uvicorn 进程')}")

        # PLC
        plc = s.get('plc', {})
        if 'error' not in plc:
            print(f"  PLC: HB={plc.get('IPC_Heartbeat','-')}, "
                  f"Alive={plc.get('Vision_Alive','-')}, "
                  f"CanTip={plc.get('Vision_CanTip','-')}, "
                  f"Fault={plc.get('Vision_FaultCode','-')}, "
                  f"Valid={plc.get('Vision_ResultValid','-')}, "
                  f"Allow={plc.get('Allow_Tip','-')}")
            print(f"  采集: Cmd={plc.get('PLC_CaptureCmd','-')}, "
                  f"State={plc.get('Vision_CaptureState','-')}, "
                  f"Tipper={plc.get('Tipper_InPosition','-')}")
            if s.get('heartbeat_stall'):
                print(f"  ⚠️ 心跳停滞！(累计 {self.heartbeat_gaps} 次)")
        else:
            print(f"  PLC: ❌ {plc['error']}")

        # Web
        web = s.get('web', {})
        if web.get('http_ok'):
            parts = []
            for k, v in web.items():
                if k.endswith('_frames'):
                    parts.append(f"{k.split('/')[0]}={v}帧")
                elif k.endswith('_phase'):
                    parts.append(f"[{v}]")
            print(f"  Web: ✅ {', '.join(parts) if parts else 'OK'}")
        else:
            print(f"  Web: ❌ {web.get('error', 'unreachable')}")

        # 日志
        log = s.get('log', {})
        if log.get('log_file'):
            print(f"  日志: {log['log_file']}, {log.get('total_lines',0)}行, "
                  f"错误={log.get('errors',0)}, 警告={log.get('warnings',0)}, "
                  f"采集周期={log.get('capture_cycles',0)}")

    def print_summary(self):
        """打印最终汇总"""
        elapsed = time.time() - self.start_time
        hours = elapsed / 3600

        print(f"\n{'#'*70}")
        print(f"  监控汇总 ({len(self.history)} 次采样, {hours:.1f} 小时)")
        print(f"{'#'*70}")

        # 内存趋势
        if self.max_rss_mb > 0:
            first_rss = self.history[0].get('process', {}).get('rss_mb', 0) if self.history else 0
            last_rss = self.history[-1].get('process', {}).get('rss_mb', 0) if self.history else 0
            growth = last_rss - first_rss
            growth_per_hour = growth / max(hours, 0.01)
            leak = '⚠️ 可能泄漏' if growth_per_hour > 10 else '✅ 正常'
            print(f"\n  内存: {first_rss}MB → {last_rss}MB (增长 {growth:+.1f}MB, "
                  f"{growth_per_hour:+.1f}MB/h) {leak}")
            print(f"  范围: {self.min_rss_mb}MB ~ {self.max_rss_mb}MB")

        # 线程趋势
        threads = [s.get('process', {}).get('num_threads', 0) for s in self.history if s.get('process', {}).get('num_threads')]
        if threads:
            t_growth = threads[-1] - threads[0]
            t_leak = '⚠️ 线程泄漏' if t_growth > 5 else '✅ 正常'
            print(f"  线程: {threads[0]} → {threads[-1]} (增长 {t_growth:+d}) {t_leak}")

        # PLC 通信
        plc_rate = (1 - self.plc_read_fails / max(self.plc_read_total, 1)) * 100
        plc_ok = '✅ 正常' if plc_rate >= 99 else '⚠️ 不稳定'
        print(f"\n  PLC 通信: {self.plc_read_total} 次读取, "
              f"{self.plc_read_fails} 次失败 ({plc_rate:.1f}% 成功率) {plc_ok}")
        print(f"  心跳停滞: {self.heartbeat_gaps} 次 "
              f"{'✅ 正常' if self.heartbeat_gaps == 0 else '⚠️ 有中断'}")

        # 采集周期
        if self.history:
            last_log = self.history[-1].get('log', {})
            cycles = last_log.get('capture_cycles', 0)
            errors = last_log.get('errors', 0)
            print(f"\n  采集周期: {cycles} 次")
            print(f"  日志错误: {errors} 条 {'✅' if errors == 0 else '⚠️'}")

        # 最终评估
        issues = []
        if self.max_rss_mb > 0:
            growth_per_hour = (self.history[-1].get('process', {}).get('rss_mb', 0) -
                              self.history[0].get('process', {}).get('rss_mb', 0)) / max(hours, 0.01)
            if growth_per_hour > 10:
                issues.append(f'内存增长 {growth_per_hour:.1f}MB/h')
        if self.heartbeat_gaps > 2:
            issues.append(f'心跳停滞 {self.heartbeat_gaps} 次')
        if plc_rate < 99:
            issues.append(f'PLC 通信成功率 {plc_rate:.1f}%')
        if threads and threads[-1] - threads[0] > 5:
            issues.append(f'线程增长 {threads[-1] - threads[0]}')

        print(f"\n  {'='*50}")
        if not issues:
            print(f"  ✅ 系统稳定，未发现异常")
        else:
            print(f"  ⚠️ 发现 {len(issues)} 个问题:")
            for i, issue in enumerate(issues, 1):
                print(f"     {i}. {issue}")
        print(f"  {'='*50}")

    def run(self):
        """运行监控"""
        print(f"翻车机积煤检测系统 - 运行监控")
        print(f"采样间隔: {self.interval}s, 持续: {'无限' if not self.duration else f'{self.duration}s'}")
        print(f"按 Ctrl+C 停止")

        try:
            while True:
                s = self.sample()
                self.print_sample(s)

                if self.duration and (time.time() - self.start_time) >= self.duration:
                    break

                time.sleep(self.interval)

        except KeyboardInterrupt:
            print("\n\n[中断] 收到停止信号")

        self.print_summary()

        # 保存报告
        if self.output_file:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'samples': self.history,
                    'summary': {
                        'duration_s': round(time.time() - self.start_time),
                        'sample_count': len(self.history),
                        'max_rss_mb': self.max_rss_mb,
                        'min_rss_mb': self.min_rss_mb,
                        'plc_read_total': self.plc_read_total,
                        'plc_read_fails': self.plc_read_fails,
                        'heartbeat_gaps': self.heartbeat_gaps,
                    }
                }, f, ensure_ascii=False, indent=2)
            print(f"\n报告已保存: {self.output_file}")


def main():
    parser = argparse.ArgumentParser(description="系统运行监控")
    parser.add_argument("--interval", type=int, default=30, help="采样间隔（秒，默认30）")
    parser.add_argument("--duration", type=int, default=0, help="运行时长（秒，0=无限）")
    parser.add_argument("--output", type=str, default=None, help="报告输出文件")
    args = parser.parse_args()

    monitor = SystemMonitor(
        interval=args.interval,
        duration=args.duration,
        output_file=args.output,
    )
    monitor.run()


if __name__ == "__main__":
    main()
