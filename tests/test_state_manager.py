"""Tests for StateManager with mock drivers."""

import os
import pytest

# Force DEV mode so mock drivers are used
os.environ["COAL_ENV"] = "DEV"

from config.config import Config
from config.devices_config import DevicesConfig, MachineConfig, FunnelConfig
from web.state_manager import StateManager, FunnelState, MachineState


def _sample_devices_config():
    return DevicesConfig(machines=[
        MachineConfig(
            id="machine-1",
            name="1#翻车机",
            plc_ip="127.0.0.1",
            funnels=[
                FunnelConfig(id="funnel-1", name="1#漏斗", camera_ip="127.0.0.1"),
                FunnelConfig(id="funnel-2", name="2#漏斗", camera_ip="127.0.0.2"),
            ],
        ),
        MachineConfig(
            id="machine-2",
            name="2#翻车机",
            plc_ip="127.0.0.2",
            funnels=[
                FunnelConfig(id="funnel-1", name="1#漏斗", camera_ip="127.0.0.3"),
            ],
        ),
    ])


class TestStateManagerInit:
    def test_initialize_creates_machines(self):
        sm = StateManager()
        base = Config()
        base.DEV_MODE = True
        sm.initialize(_sample_devices_config(), base)
        try:
            assert len(sm.machines) == 2
            assert "machine-1" in sm.machines
            assert "machine-2" in sm.machines
        finally:
            sm.shutdown()

    def test_initialize_creates_funnels(self):
        sm = StateManager()
        base = Config()
        base.DEV_MODE = True
        sm.initialize(_sample_devices_config(), base)
        try:
            m1 = sm.machines["machine-1"]
            assert len(m1.funnels) == 2
            assert "funnel-1" in m1.funnels
            assert "funnel-2" in m1.funnels

            m2 = sm.machines["machine-2"]
            assert len(m2.funnels) == 1
        finally:
            sm.shutdown()

    def test_funnel_has_camera_and_detector(self):
        sm = StateManager()
        base = Config()
        base.DEV_MODE = True
        sm.initialize(_sample_devices_config(), base)
        try:
            fs = sm.get_funnel_state("machine-1", "funnel-1")
            assert fs is not None
            assert fs.camera is not None
            assert fs.detector is not None
            assert fs.is_running is True
        finally:
            sm.shutdown()

    def test_machine_has_plc(self):
        sm = StateManager()
        base = Config()
        base.DEV_MODE = True
        sm.initialize(_sample_devices_config(), base)
        try:
            ms = sm.get_machine_state("machine-1")
            assert ms is not None
            assert ms.plc is not None
        finally:
            sm.shutdown()


class TestStateManagerQuery:
    def _make_sm(self):
        sm = StateManager()
        base = Config()
        base.DEV_MODE = True
        sm.initialize(_sample_devices_config(), base)
        return sm

    def test_get_machine_state(self):
        sm = self._make_sm()
        try:
            assert sm.get_machine_state("machine-1") is not None
            assert sm.get_machine_state("nonexistent") is None
        finally:
            sm.shutdown()

    def test_get_funnel_state(self):
        sm = self._make_sm()
        try:
            assert sm.get_funnel_state("machine-1", "funnel-1") is not None
            assert sm.get_funnel_state("machine-1", "funnel-99") is None
            assert sm.get_funnel_state("nonexistent", "funnel-1") is None
        finally:
            sm.shutdown()

    def test_overview_data(self):
        sm = self._make_sm()
        try:
            data = sm.get_overview_data()
            assert len(data) == 2
            m1 = data[0]
            assert m1["id"] == "machine-1"
            assert m1["funnel_count"] == 2
            assert len(m1["funnels"]) == 2
        finally:
            sm.shutdown()


class TestStateManagerShutdown:
    def test_shutdown_clears_machines(self):
        sm = StateManager()
        base = Config()
        base.DEV_MODE = True
        sm.initialize(_sample_devices_config(), base)
        sm.shutdown()
        assert len(sm.machines) == 0

    def test_shutdown_stops_funnels(self):
        sm = StateManager()
        base = Config()
        base.DEV_MODE = True
        sm.initialize(_sample_devices_config(), base)
        fs = sm.get_funnel_state("machine-1", "funnel-1")
        assert fs.is_running is True
        sm.shutdown()
        assert fs.is_running is False


class TestFunnelStateInheritance:
    def test_inherits_stream_app_state(self):
        fs = FunnelState("m1", "f1")
        assert hasattr(fs, "config")
        assert hasattr(fs, "camera")
        assert hasattr(fs, "is_running")
        assert hasattr(fs, "detection_count")
        assert hasattr(fs, "detection_history")

    def test_reset_counters(self):
        fs = FunnelState("m1", "f1")
        fs.detection_count = 10
        fs.detection_history.append({"test": True})
        fs.reset_stream_counters()
        assert fs.detection_count == 0
        assert len(fs.detection_history) == 0


class TestMachineStateProperties:
    def test_worst_alert_level_default(self):
        ms = MachineState(
            machine_id="m1",
            machine_config=MachineConfig(id="m1", name="M1", plc_ip="127.0.0.1"),
        )
        fs = FunnelState("m1", "f1")
        ms.funnels["f1"] = fs
        assert ms.worst_alert_level == "NORMAL"

    def test_plc_connected_false_when_none(self):
        ms = MachineState(
            machine_id="m1",
            machine_config=MachineConfig(id="m1", name="M1", plc_ip="127.0.0.1"),
        )
        assert ms.plc_connected is False
