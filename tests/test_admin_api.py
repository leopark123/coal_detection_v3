"""Tests for admin API routes and functionality."""

import os

os.environ["COAL_ENV"] = "DEV"

from web.unified_app import app
from web.admin_api import _hash_password, ADMIN_PASSWORD, ADMIN_TOKEN


def _route_methods(application):
    methods = {}
    for route in application.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            if route.path not in methods:
                methods[route.path] = set()
            methods[route.path].update(route.methods)
    return methods


class TestAdminRouteContract:
    def test_auth_route(self):
        methods = _route_methods(app)
        assert "/api/admin/auth" in methods
        assert "POST" in methods["/api/admin/auth"]

    def test_machines_routes(self):
        methods = _route_methods(app)
        assert "/api/admin/machines" in methods
        assert "GET" in methods["/api/admin/machines"]
        assert "POST" in methods["/api/admin/machines"]

    def test_machine_crud_routes(self):
        methods = _route_methods(app)
        assert "/api/admin/machines/{machine_id}" in methods
        assert "PUT" in methods["/api/admin/machines/{machine_id}"]
        assert "DELETE" in methods["/api/admin/machines/{machine_id}"]

    def test_funnel_crud_routes(self):
        methods = _route_methods(app)
        assert "/api/admin/machines/{machine_id}/funnels" in methods
        assert "POST" in methods["/api/admin/machines/{machine_id}/funnels"]
        assert "/api/admin/machines/{machine_id}/funnels/{funnel_id}" in methods
        assert "PUT" in methods["/api/admin/machines/{machine_id}/funnels/{funnel_id}"]
        assert "DELETE" in methods["/api/admin/machines/{machine_id}/funnels/{funnel_id}"]

    def test_thresholds_routes(self):
        methods = _route_methods(app)
        assert "/api/admin/thresholds" in methods
        assert "GET" in methods["/api/admin/thresholds"]
        assert "PUT" in methods["/api/admin/thresholds"]

    def test_system_info_route(self):
        methods = _route_methods(app)
        assert "/api/admin/system_info" in methods
        assert "GET" in methods["/api/admin/system_info"]

    def test_settings_page_route(self):
        methods = _route_methods(app)
        assert "/settings" in methods
        assert "GET" in methods["/settings"]


class TestAdminAuth:
    def test_hash_password(self):
        h = _hash_password("test123")
        assert len(h) == 64  # SHA-256 hex
        assert h == _hash_password("test123")  # deterministic

    def test_token_matches_password(self):
        assert ADMIN_TOKEN == _hash_password(ADMIN_PASSWORD)


class TestDevicesConfigSerialization:
    def test_to_yaml_roundtrip(self):
        import tempfile
        from config.devices_config import DevicesConfig, MachineConfig, FunnelConfig

        dc = DevicesConfig(machines=[
            MachineConfig(
                id="m1", name="Test Machine", plc_ip="10.0.0.1",
                funnels=[
                    FunnelConfig(id="f1", name="Funnel 1", camera_ip="10.0.0.2"),
                ],
            ),
        ])

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            path = f.name

        try:
            dc.to_yaml(path)
            dc2 = DevicesConfig.from_yaml(path)
            assert len(dc2.machines) == 1
            assert dc2.machines[0].id == "m1"
            assert dc2.machines[0].name == "Test Machine"
            assert len(dc2.machines[0].funnels) == 1
            assert dc2.machines[0].funnels[0].camera_ip == "10.0.0.2"
        finally:
            os.unlink(path)

    def test_add_remove_machine(self):
        from config.devices_config import DevicesConfig, MachineConfig

        dc = DevicesConfig()
        dc.add_machine(MachineConfig(id="m1", name="M1", plc_ip="1.1.1.1"))
        assert len(dc.machines) == 1

        dc.remove_machine("m1")
        assert len(dc.machines) == 0

    def test_add_remove_funnel(self):
        from config.devices_config import DevicesConfig, MachineConfig, FunnelConfig

        dc = DevicesConfig(machines=[
            MachineConfig(id="m1", name="M1", plc_ip="1.1.1.1"),
        ])
        dc.add_funnel("m1", FunnelConfig(id="f1", name="F1", camera_ip="2.2.2.2"))
        assert len(dc.machines[0].funnels) == 1

        dc.remove_funnel("m1", "f1")
        assert len(dc.machines[0].funnels) == 0


class TestStateManagerDynamic:
    def _make_sm(self):
        from config.config import Config
        from config.devices_config import DevicesConfig, MachineConfig, FunnelConfig
        from web.state_manager import StateManager

        sm = StateManager()
        base = Config()
        base.DEV_MODE = True
        dc = DevicesConfig(machines=[
            MachineConfig(id="m1", name="M1", plc_ip="127.0.0.1",
                          funnels=[FunnelConfig(id="f1", name="F1", camera_ip="127.0.0.1")]),
        ])
        sm.initialize(dc, base)
        return sm

    def test_add_machine_dynamic(self):
        from config.devices_config import MachineConfig

        sm = self._make_sm()
        try:
            sm.add_machine(MachineConfig(id="m2", name="M2", plc_ip="127.0.0.2"))
            assert "m2" in sm.machines
            assert len(sm.machines) == 2
        finally:
            sm.shutdown()

    def test_remove_machine_dynamic(self):
        sm = self._make_sm()
        try:
            sm.remove_machine("m1")
            assert "m1" not in sm.machines
        finally:
            sm.shutdown()

    def test_add_funnel_dynamic(self):
        from config.devices_config import FunnelConfig

        sm = self._make_sm()
        try:
            sm.add_funnel("m1", FunnelConfig(id="f2", name="F2", camera_ip="127.0.0.2"))
            assert "f2" in sm.machines["m1"].funnels
        finally:
            sm.shutdown()

    def test_remove_funnel_dynamic(self):
        sm = self._make_sm()
        try:
            sm.remove_funnel("m1", "f1")
            assert "f1" not in sm.machines["m1"].funnels
        finally:
            sm.shutdown()

    def test_update_thresholds(self):
        sm = self._make_sm()
        try:
            applied = sm.update_thresholds({"GRID_VISIBLE_THRESHOLD": 0.9})
            assert applied["GRID_VISIBLE_THRESHOLD"] == 0.9
            assert sm.base_config.GRID_VISIBLE_THRESHOLD == 0.9
            # Check propagated to funnel config
            fs = sm.get_funnel_state("m1", "f1")
            assert fs.config.GRID_VISIBLE_THRESHOLD == 0.9
        finally:
            sm.shutdown()

    def test_get_thresholds(self):
        sm = self._make_sm()
        try:
            th = sm.get_thresholds()
            assert "GRID_VISIBLE_THRESHOLD" in th
            assert "VOTE_WINDOW_SIZE" in th
        finally:
            sm.shutdown()
