"""Route contract tests for the unified multi-machine web app."""

import os

os.environ["COAL_ENV"] = "DEV"

from web.unified_app import app


def _route_methods(application):
    """Extract HTTP route → methods map."""
    methods = {}
    for route in application.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            methods[route.path] = route.methods
    return methods


def _websocket_paths(application):
    """Extract WebSocket paths."""
    paths = set()
    for route in application.routes:
        if not hasattr(route, "methods") and hasattr(route, "path"):
            if "ws" in route.path:
                paths.add(route.path)
    return paths


class TestUnifiedAppRouteContract:
    def test_overview_page(self):
        methods = _route_methods(app)
        assert "/" in methods and "GET" in methods["/"]

    def test_machine_detail_page(self):
        methods = _route_methods(app)
        assert "/machine/{machine_id}" in methods
        assert "GET" in methods["/machine/{machine_id}"]

    def test_funnel_detail_page(self):
        methods = _route_methods(app)
        assert "/machine/{machine_id}/funnel/{funnel_id}" in methods
        assert "GET" in methods["/machine/{machine_id}/funnel/{funnel_id}"]

    def test_api_overview(self):
        methods = _route_methods(app)
        assert "/api/overview" in methods
        assert "GET" in methods["/api/overview"]

    def test_api_machine_status(self):
        methods = _route_methods(app)
        assert "/api/machine/{machine_id}/status" in methods

    def test_api_funnel_status(self):
        methods = _route_methods(app)
        assert "/api/machine/{machine_id}/funnel/{funnel_id}/status" in methods

    def test_api_funnel_statistics(self):
        methods = _route_methods(app)
        assert "/api/machine/{machine_id}/funnel/{funnel_id}/statistics" in methods

    def test_api_funnel_history(self):
        methods = _route_methods(app)
        assert "/api/machine/{machine_id}/funnel/{funnel_id}/history" in methods

    def test_api_funnel_reset_stats(self):
        methods = _route_methods(app)
        path = "/api/machine/{machine_id}/funnel/{funnel_id}/reset_stats"
        assert path in methods
        assert "POST" in methods[path]

    def test_websocket_overview(self):
        ws_paths = _websocket_paths(app)
        assert "/ws/overview" in ws_paths

    def test_websocket_funnel(self):
        ws_paths = _websocket_paths(app)
        assert "/ws/funnel/{machine_id}/{funnel_id}" in ws_paths
