"""
Web route contract smoke tests.
"""

import importlib.util

import pytest
from fastapi.routing import APIWebSocketRoute

from web.device_app import app as device_app
from web.single_grid_app import app as single_app

_has_web_app = importlib.util.find_spec("web.app") is not None


def _route_methods(app):
    methods_by_path = {}
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue
        methods_by_path.setdefault(route.path, set()).update(methods)
    return methods_by_path


def _websocket_paths(app):
    return {route.path for route in app.router.routes if isinstance(route, APIWebSocketRoute)}


@pytest.mark.skipif(not _has_web_app, reason="web/app.py 已归档到 scripts/legacy/")
def test_main_app_route_contract():
    from web.app import app as main_app

    methods = _route_methods(main_app)
    ws_paths = _websocket_paths(main_app)

    assert "/" in methods and "GET" in methods["/"]
    assert "/api/camera/debug" in methods and "GET" in methods["/api/camera/debug"]
    assert "/api/status" in methods and "GET" in methods["/api/status"]
    assert "/ws" in ws_paths


def test_device_app_route_contract():
    methods = _route_methods(device_app)
    ws_paths = _websocket_paths(device_app)

    assert "/" in methods and "GET" in methods["/"]
    assert "/api/device/statistics" in methods and "GET" in methods["/api/device/statistics"]
    assert "/api/device/history" in methods and "GET" in methods["/api/device/history"]
    assert "/api/device/status" in methods and "GET" in methods["/api/device/status"]
    assert "/api/device/reset_stats" in methods and "POST" in methods["/api/device/reset_stats"]
    assert "/api/device/grid_details" in methods and "GET" in methods["/api/device/grid_details"]
    assert "/ws" in ws_paths


def test_single_grid_app_route_contract():
    methods = _route_methods(single_app)
    ws_paths = _websocket_paths(single_app)

    assert "/" in methods and "GET" in methods["/"]
    assert "/api/statistics" in methods and "GET" in methods["/api/statistics"]
    assert "/api/history" in methods and "GET" in methods["/api/history"]
    assert "/api/grid/switch/{grid_id}" in methods and "GET" in methods["/api/grid/switch/{grid_id}"]
    assert "/api/save_logs" in methods and "POST" in methods["/api/save_logs"]
    assert "/api/status" in methods and "GET" in methods["/api/status"]
    assert "/ws" in ws_paths
