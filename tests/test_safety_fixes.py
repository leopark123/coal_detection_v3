import time
from types import SimpleNamespace

import pytest

from algo.device_detector import DeviceDetector
from config.config import Config
from core.capture_window import CapturePhase, CaptureWindowConfig, CaptureWindowController
from drivers.mock_drivers import MockPLC
from web.state_manager import StateManager
from web.state_manager import FunnelState, MachineState
from config.devices_config import MachineConfig


class _FakePLC:
    def __init__(self):
        self.tags = {"PLC_CaptureCmd": 0}

    def read(self, tag):
        return self.tags.get(tag, 0)

    def write(self, tag, value):
        self.tags[tag] = value
        return True


def test_capture_window_finishes_on_window_duration_without_waiting_for_cmd_reset():
    plc = _FakePLC()
    controller = CaptureWindowController(
        CaptureWindowConfig(window_duration_s=0.1, poll_interval_s=0.0, max_capture_s=10.0),
        plc=plc,
    )
    controller.start()

    plc.tags["PLC_CaptureCmd"] = controller.CMD_START
    assert controller.tick() == CapturePhase.CAPTURING
    assert plc.tags["Vision_CaptureState"] == controller.STATE_CAPTURING

    controller.feed_result({"has_coal": False, "coal_grids": 0, "fault_code": 0})
    controller._window_start_time = time.time() - 0.2

    assert controller.tick() == CapturePhase.COMPLETE
    assert plc.tags["PLC_CaptureCmd"] == controller.CMD_START
    assert plc.tags["Vision_CaptureState"] == controller.STATE_COMPLETE
    assert controller.last_window_result is not None
    assert controller.last_window_result.fault_code == 0


def test_device_detector_low_grid_visibility_is_fail_safe(monkeypatch):
    config = Config()
    config.GRID_VISIBLE_THRESHOLD = 0.85

    detector = object.__new__(DeviceDetector)
    detector.config = config
    detector.device_id = "test-device"
    detector.device_grids = list(range(10))
    detector.detection_count = 0
    detector.device_coal_detections = 0
    detector.avg_process_time = 0.0

    grid_details = [
        SimpleNamespace(is_visible=True, has_coal=False) for _ in range(4)
    ] + [
        SimpleNamespace(is_visible=False, has_coal=False) for _ in range(6)
    ]
    detection_result = SimpleNamespace(
        quality_ok=True,
        grid_details=grid_details,
        process_time_ms=1.0,
    )
    monkeypatch.setattr(detector, "detect", lambda frame, frame_id=0: detection_result)

    result = detector.detect_device(SimpleNamespace(), frame_id=1)

    assert result.visible_grids == 4
    assert result.coal_grids == 0
    assert result.quality_ok is False
    assert result.fault_code == 3
    assert result.device_has_coal is False
    assert result.device_confidence == "LOW"
    assert result.device_alert_level == "WARNING"


def test_update_thresholds_invalid_vote_combination_does_not_mutate_state():
    manager = StateManager()
    manager.base_config = Config()
    manager.base_config.VOTE_WINDOW_SIZE = 5
    manager.base_config.VOTE_THRESHOLD = 3

    with pytest.raises(ValueError):
        manager.update_thresholds({"VOTE_WINDOW_SIZE": 2, "VOTE_THRESHOLD": 3})

    assert manager.base_config.VOTE_WINDOW_SIZE == 5
    assert manager.base_config.VOTE_THRESHOLD == 3


def test_initially_unconnected_camera_is_retried_by_background_worker():
    class FakeCamera:
        def __init__(self):
            self.is_connected = False
            self.last_error = "initial connect failed"
            self.reconnect_calls = 0

        def reconnect(self):
            self.reconnect_calls += 1
            self.is_connected = True
            return True

    class FakeCaptureController:
        def __init__(self, manager):
            self.manager = manager

        def tick(self):
            self.manager._bg_stop_event.set()

        def should_capture(self):
            return False

    manager = StateManager()
    machine_config = MachineConfig(id="m1", name="M1", plc_ip="127.0.0.1")
    machine_state = MachineState(machine_id="m1", machine_config=machine_config)
    funnel_state = FunnelState("m1", "f1")
    funnel_state.camera = FakeCamera()
    funnel_state.detector = object()
    funnel_state.capture_controller = FakeCaptureController(manager)
    funnel_state.is_running = True
    funnel_state._ever_connected = False
    funnel_state.fault_info["camera"] = {
        "status": "not_available",
        "error": "initial connect failed",
        "since": time.time(),
        "reconnect_attempts": 0,
    }

    machine_state.funnels["f1"] = funnel_state
    manager.machines["m1"] = machine_state

    manager._bg_detection_loop(machine_state, funnel_state, "m1/f1")

    assert funnel_state.camera.reconnect_calls == 1
    assert funnel_state._ever_connected is True
    assert funnel_state.fault_info["camera"]["status"] == "connected"


def test_mock_plc_send_detection_result_matches_real_plc_tags():
    config = Config()
    config.DEV_MODE = True
    plc = MockPLC(config)

    plc.send_detection_result(
        coal_present=False,
        confidence="HIGH",
        need_manual=False,
        fault_code=0,
    )

    assert plc.read("Vision_CanTip") is True
    assert plc.read("Vision_FaultCode") == 0
    assert plc.read("Vision_ResultValid") is True

    plc.send_detection_result(
        coal_present=True,
        confidence="HIGH",
        need_manual=False,
        fault_code=0,
    )

    assert plc.read("Vision_CanTip") is False
    assert plc.read("Vision_ResultValid") is True
