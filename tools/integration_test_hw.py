"""
翻车机积煤检测系统 V3.0 - 相机+PLC 联调测试

验证完整链路：相机采集 → 算法检测 → PLC 写入 → 心跳

使用方法：
    python tools/integration_test_hw.py
    python tools/integration_test_hw.py --frames 50
    python tools/integration_test_hw.py --camera-only
    python tools/integration_test_hw.py --plc-only
"""

import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from config.config import Config


def test_camera_plc_loop(config: Config, max_frames: int = 20):
    """完整联调：采集 → 检测 → PLC 写入"""
    from drivers.basler_camera import BaslerCamera
    from pycomm3 import LogixDriver
    from algo.detector import CoalDetector, FrameVoter

    print()
    print("=" * 60)
    print("  相机 + PLC 联调测试")
    print("=" * 60)

    # 1. 连接相机
    print("\n[1/3] 连接相机...")
    camera = BaslerCamera(config)
    if not camera.is_connected:
        print(f"  [FAIL] 相机连接失败: {camera.last_error}")
        return False
    print(f"  [OK] 相机已连接: {config.CAMERA_IP}")

    # 2. 连接 PLC
    print("\n[2/3] 连接 PLC...")
    plc = LogixDriver(config.PLC_IP, init_tags=True, init_program_tags=True)
    try:
        plc.open()
        print(f"  [OK] PLC 已连接: {config.PLC_IP}")
    except Exception as e:
        print(f"  [FAIL] PLC 连接失败: {e}")
        camera.release()
        return False

    # 写入上线信号
    plc.write("IPC_Online", True)
    print("  [OK] IPC_Online = True")

    # 3. 初始化检测器
    print("\n[3/3] 初始化检测器...")
    detector = CoalDetector(config)
    voter = FrameVoter(config)
    print("  [OK] 检测器就绪")

    # 联调循环
    print()
    print("=" * 60)
    print(f"  开始联调（{max_frames} 帧），按 Ctrl+C 提前停止")
    print("=" * 60)
    print()
    print(f"  {'帧':>4} | {'采集ms':>6} | {'检测ms':>6} | {'PLC写ms':>7} | {'总计ms':>6} | {'可翻转':>6} | {'故障码':>4} | {'心跳':>5}")
    print(f"  {'-'*4} | {'-'*6} | {'-'*6} | {'-'*7} | {'-'*6} | {'-'*6} | {'-'*4} | {'-'*5}")

    heartbeat_value = 0
    last_heartbeat_time = time.time()
    plc_write_count = 0
    plc_fail_count = 0
    grab_ok_count = 0
    total_loop_ms = 0

    try:
        for frame_id in range(max_frames):
            t_total = time.perf_counter()

            # --- 采集 ---
            t0 = time.perf_counter()
            try:
                frame = camera.grab()
                grab_ok_count += 1
            except Exception as e:
                print(f"  {frame_id:4d} | 采集失败: {e}")
                time.sleep(0.5)
                continue
            t_grab = (time.perf_counter() - t0) * 1000

            # --- 检测 ---
            t0 = time.perf_counter()
            result = detector.detect(frame, frame_id)
            voted = voter.vote(result)
            t_detect = (time.perf_counter() - t0) * 1000

            # --- PLC 写入 ---
            t0 = time.perf_counter()

            coal_present = voted.has_coal or False
            need_manual = voted.need_manual_confirm
            confidence = voted.confidence

            if not voted.quality_ok:
                fault_code = 3
            elif need_manual:
                fault_code = 4
            else:
                fault_code = 0

            can_tip = (not coal_present) and (not need_manual)
            result_valid = confidence in ("HIGH", "MEDIUM")

            # 心跳（500ms 间隔）
            now = time.time()
            if (now - last_heartbeat_time) * 1000 >= config.PLC_HEARTBEAT_INTERVAL_MS:
                heartbeat_value = (heartbeat_value + 1) % 65536
                hb_result = plc.write("IPC_Heartbeat", heartbeat_value)
                if not hb_result.error:
                    last_heartbeat_time = now
                    plc_write_count += 1
                else:
                    plc_fail_count += 1

            # 批量写入检测结果
            write_results = plc.write(
                ("Vision_CanTip", can_tip),
                ("Vision_FaultCode", fault_code),
                ("Vision_ResultValid", result_valid),
            )
            for wr in write_results:
                if wr.error:
                    plc_fail_count += 1
                else:
                    plc_write_count += 1

            t_plc = (time.perf_counter() - t0) * 1000
            t_loop = (time.perf_counter() - t_total) * 1000
            total_loop_ms += t_loop

            print(f"  {frame_id:4d} | {t_grab:6.1f} | {t_detect:6.1f} | {t_plc:7.1f} | {t_loop:6.1f} | {str(can_tip):>6} | {fault_code:4d} | {heartbeat_value:5d}")

            # 帧率控制
            elapsed = time.perf_counter() - t_total
            sleep_time = config.frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n  [中断] 收到停止信号")

    # 清理
    plc.write("IPC_Online", False)
    plc.close()
    camera.release()

    # 汇总
    frames_done = max(grab_ok_count, 1)
    avg_loop = total_loop_ms / frames_done

    print()
    print("=" * 60)
    print("  联调结果汇总")
    print("=" * 60)
    print(f"  采集帧数:    {grab_ok_count}/{max_frames}")
    print(f"  PLC 写入:    {plc_write_count} 成功, {plc_fail_count} 失败")
    print(f"  心跳终值:    {heartbeat_value}")
    print(f"  平均周期:    {avg_loop:.1f} ms")
    print(f"  目标周期:    {config.frame_interval*1000:.1f} ms ({config.TARGET_FPS} FPS)")
    print()

    if plc_fail_count == 0 and grab_ok_count == max_frames:
        print("  >>> 联调通过 <<<")
    elif plc_fail_count > 0:
        print(f"  >>> PLC 写入有 {plc_fail_count} 次失败，请检查 <<<")
    elif grab_ok_count < max_frames:
        print(f"  >>> 相机采集有 {max_frames - grab_ok_count} 帧丢失 <<<")
    print()

    return plc_fail_count == 0 and grab_ok_count == max_frames


def test_camera_only(config: Config, max_frames: int = 20):
    """仅测试相机连续采集"""
    from drivers.basler_camera import BaslerCamera
    import cv2

    print("\n=== 相机连续采集测试 ===")

    camera = BaslerCamera(config)
    if not camera.is_connected:
        print(f"  [FAIL] 连接失败: {camera.last_error}")
        return False

    ok = 0
    for i in range(max_frames):
        try:
            t0 = time.perf_counter()
            frame = camera.grab()
            ms = (time.perf_counter() - t0) * 1000
            print(f"  帧[{i:3d}]: {ms:6.1f}ms, mean={frame.mean():.1f}, shape={frame.shape}")
            ok += 1

            # 保存首帧和末帧
            if i == 0:
                cv2.imwrite("logs/integration_frame_first.jpg", frame)
            if i == max_frames - 1:
                cv2.imwrite("logs/integration_frame_last.jpg", frame)

        except Exception as e:
            print(f"  帧[{i:3d}]: 失败 - {e}")

    camera.release()
    print(f"\n  结果: {ok}/{max_frames} 帧成功")
    return ok == max_frames


def test_plc_only(config: Config):
    """仅测试 PLC 读写"""
    from pycomm3 import LogixDriver

    print("\n=== PLC 读写测试 ===")

    plc = LogixDriver(config.PLC_IP, init_tags=True, init_program_tags=True)
    try:
        plc.open()
        print(f"  [OK] PLC 已连接: {config.PLC_IP}")
    except Exception as e:
        print(f"  [FAIL] 连接失败: {e}")
        return False

    tags = [
        ("IPC_Online", True),
        ("Vision_CanTip", True),
        ("Vision_FaultCode", 0),
        ("Vision_ResultValid", True),
        ("IPC_Heartbeat", 1),
    ]

    all_ok = True

    # 逐个写入并回读验证
    for tag, value in tags:
        w = plc.write(tag, value)
        if w.error:
            print(f"  [FAIL] 写入 {tag}={value}: {w.error}")
            all_ok = False
            continue

        r = plc.read(tag)
        if r.error:
            print(f"  [FAIL] 回读 {tag}: {r.error}")
            all_ok = False
            continue

        match = r.value == value
        print(f"  [{'OK' if match else 'FAIL'}] {tag}: 写入={value}, 回读={r.value}")
        if not match:
            all_ok = False

    # 心跳连续写入测试（5 次，500ms 间隔）
    print("\n  心跳连续测试 (5次, 500ms间隔):")
    for i in range(1, 6):
        w = plc.write("IPC_Heartbeat", i)
        r = plc.read("IPC_Heartbeat")
        ok = not w.error and not r.error and r.value == i
        print(f"    [{i}] 写入={i}, 回读={r.value} {'OK' if ok else 'FAIL'}")
        if not ok:
            all_ok = False
        time.sleep(0.5)

    # 复位
    plc.write("IPC_Online", False)
    plc.write("Vision_CanTip", True)
    plc.write("Vision_FaultCode", 0)
    plc.close()

    print(f"\n  结果: {'全部通过' if all_ok else '存在失败项'}")
    return all_ok


def main():
    parser = argparse.ArgumentParser(description="相机+PLC 联调测试")
    parser.add_argument("--frames", type=int, default=20, help="测试帧数 (默认 20)")
    parser.add_argument("--camera-only", action="store_true", help="仅测试相机")
    parser.add_argument("--plc-only", action="store_true", help="仅测试 PLC")
    args = parser.parse_args()

    config = Config()
    config.DEV_MODE = False

    # 配置日志（减少干扰）
    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    if args.camera_only:
        ok = test_camera_only(config, args.frames)
    elif args.plc_only:
        ok = test_plc_only(config)
    else:
        ok = test_camera_plc_loop(config, args.frames)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
