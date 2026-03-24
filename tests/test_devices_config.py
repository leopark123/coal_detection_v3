"""Tests for multi-machine device configuration loader."""

import os
import tempfile

import pytest

from config.devices_config import (
    DevicesConfig,
    MachineConfig,
    FunnelConfig,
    build_funnel_config,
)
from config.config import Config


SAMPLE_YAML = """\
machines:
  - id: "machine-1"
    name: "1#翻车机"
    plc_ip: "192.168.1.19"
    plc_timeout_ms: 3000
    plc_heartbeat_interval_ms: 500
    funnels:
      - id: "funnel-1"
        name: "1#漏斗"
        camera_ip: "192.168.1.12"
        pixel_format: "mono"
        camera_timeout_ms: 5000
        grid_count: 125
      - id: "funnel-2"
        name: "2#漏斗"
        camera_ip: "192.168.1.13"
        pixel_format: "color"
        grid_count: 108

  - id: "machine-2"
    name: "2#翻车机"
    plc_ip: "192.168.2.19"
    funnels:
      - id: "funnel-1"
        camera_ip: "192.168.2.12"
"""


def _load_sample() -> DevicesConfig:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(SAMPLE_YAML)
        path = f.name
    try:
        return DevicesConfig.from_yaml(path)
    finally:
        os.unlink(path)


class TestDevicesConfigLoading:
    def test_load_machines(self):
        dc = _load_sample()
        assert len(dc.machines) == 2
        assert dc.machines[0].id == "machine-1"
        assert dc.machines[0].name == "1#翻车机"
        assert dc.machines[1].id == "machine-2"

    def test_load_funnels(self):
        dc = _load_sample()
        m1 = dc.machines[0]
        assert len(m1.funnels) == 2
        assert m1.funnels[0].id == "funnel-1"
        assert m1.funnels[0].camera_ip == "192.168.1.12"
        assert m1.funnels[0].pixel_format == "mono"
        assert m1.funnels[0].grid_count == 125
        assert m1.funnels[1].pixel_format == "color"
        assert m1.funnels[1].grid_count == 108

    def test_plc_config(self):
        dc = _load_sample()
        assert dc.machines[0].plc_ip == "192.168.1.19"
        assert dc.machines[0].plc_timeout_ms == 3000

    def test_defaults(self):
        dc = _load_sample()
        m2 = dc.machines[1]
        assert m2.plc_timeout_ms == 3000  # default
        f1 = m2.funnels[0]
        assert f1.name == f1.id  # no name given, falls back to id
        assert f1.pixel_format == "mono"  # default
        assert f1.grid_count == 125  # default

    def test_get_machine(self):
        dc = _load_sample()
        assert dc.get_machine("machine-1") is not None
        assert dc.get_machine("nonexistent") is None

    def test_get_funnel(self):
        dc = _load_sample()
        assert dc.get_funnel("machine-1", "funnel-2") is not None
        assert dc.get_funnel("machine-1", "funnel-99") is None
        assert dc.get_funnel("nonexistent", "funnel-1") is None

    def test_empty_machines(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write("machines: []\n")
            path = f.name
        try:
            dc = DevicesConfig.from_yaml(path)
            assert len(dc.machines) == 0
        finally:
            os.unlink(path)


class TestBuildFunnelConfig:
    def test_overrides_camera_ip(self):
        base = Config()
        machine = MachineConfig(id="m1", name="M1", plc_ip="10.0.0.1")
        funnel = FunnelConfig(id="f1", name="F1", camera_ip="10.0.0.2")
        cfg = build_funnel_config(base, machine, funnel)
        assert cfg.CAMERA_IP == "10.0.0.2"
        assert cfg.PLC_IP == "10.0.0.1"

    def test_preserves_algo_params(self):
        base = Config()
        base.CLAHE_CLIP_LIMIT = 5.0
        base.VOTE_WINDOW_SIZE = 7
        machine = MachineConfig(id="m1", name="M1", plc_ip="10.0.0.1")
        funnel = FunnelConfig(id="f1", name="F1", camera_ip="10.0.0.2")
        cfg = build_funnel_config(base, machine, funnel)
        assert cfg.CLAHE_CLIP_LIMIT == 5.0
        assert cfg.VOTE_WINDOW_SIZE == 7

    def test_overrides_pixel_format(self):
        base = Config()
        machine = MachineConfig(id="m1", name="M1", plc_ip="10.0.0.1")
        funnel = FunnelConfig(id="f1", name="F1", camera_ip="10.0.0.2", pixel_format="color")
        cfg = build_funnel_config(base, machine, funnel)
        assert cfg.CAMERA_PIXEL_FORMAT == "color"

    def test_overrides_plc_params(self):
        base = Config()
        machine = MachineConfig(
            id="m1", name="M1", plc_ip="10.0.0.1",
            plc_timeout_ms=5000, plc_heartbeat_interval_ms=250,
        )
        funnel = FunnelConfig(id="f1", name="F1", camera_ip="10.0.0.2")
        cfg = build_funnel_config(base, machine, funnel)
        assert cfg.PLC_TIMEOUT_MS == 5000
        assert cfg.PLC_HEARTBEAT_INTERVAL_MS == 250
