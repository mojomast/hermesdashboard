import asyncio
import json
import unittest
from pathlib import Path
from unittest import mock

import app as dashboard_app
from dashboard_backend.routes import dashboard_state as route_module


class FakeRequest:
    def __init__(self, key="conversation", body=b""):
        self.path_params = {"key": key}
        self._body = body

    async def body(self):
        return self._body


def run(coro):
    return asyncio.run(coro)


def response_json(response):
    return json.loads(response.body.decode("utf-8"))


class DashboardStateRouteWrapperTests(unittest.TestCase):
    def test_route_module_get_uses_injected_loader(self):
        calls = []

        def load_state(key):
            calls.append(key)
            return True, {"messages": ["hello"]}

        response = run(
            route_module.get_dashboard_state_endpoint(
                FakeRequest("conversation"),
                load_state=load_state,
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_json(response), {"found": True, "value": {"messages": ["hello"]}})
        self.assertEqual(calls, ["conversation"])

    def test_route_module_get_maps_value_error_to_404(self):
        def load_state(key):
            raise ValueError(f"Unsupported dashboard state key: {key}")

        response = run(
            route_module.get_dashboard_state_endpoint(
                FakeRequest("other"),
                load_state=load_state,
            )
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response_json(response), {"error": "Unsupported dashboard state key: other"})

    def test_route_module_put_rejects_invalid_json(self):
        response = run(
            route_module.set_dashboard_state_endpoint(
                FakeRequest(body=b"{"),
                save_state=lambda key, value: None,
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response_json(response), {"error": "Invalid JSON body"})

    def test_route_module_put_rejects_missing_value(self):
        response = run(
            route_module.set_dashboard_state_endpoint(
                FakeRequest(body=b'{"not_value": 1}'),
                save_state=lambda key, value: None,
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response_json(response), {"error": "Expected JSON object with a value field"})

    def test_route_module_put_accepts_explicit_null_value(self):
        calls = []

        def save_state(key, value):
            calls.append((key, value))

        response = run(
            route_module.set_dashboard_state_endpoint(
                FakeRequest("active_run", body=b'{"value": null}'),
                save_state=save_state,
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_json(response), {"success": True})
        self.assertEqual(calls, [("active_run", None)])

    def test_route_module_put_uses_injected_saver(self):
        calls = []

        def save_state(key, value):
            calls.append((key, value))

        response = run(
            route_module.set_dashboard_state_endpoint(
                FakeRequest("conversation", body=b'{"value": {"roles": ["user"]}}'),
                save_state=save_state,
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_json(response), {"success": True})
        self.assertEqual(calls, [("conversation", {"roles": ["user"]})])

    def test_route_module_delete_uses_injected_deleter(self):
        calls = []

        def delete_state(key):
            calls.append(key)

        response = run(
            route_module.delete_dashboard_state_endpoint(
                FakeRequest("active_run"),
                delete_state=delete_state,
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_json(response), {"success": True})
        self.assertEqual(calls, ["active_run"])

    def test_app_wrappers_delegate_through_live_monkeypatches(self):
        with mock.patch.object(dashboard_app, "_load_dashboard_state", return_value=(True, "loaded")) as load_state:
            get_response = run(dashboard_app.get_dashboard_state(FakeRequest("conversation")))
        self.assertEqual(response_json(get_response), {"found": True, "value": "loaded"})
        load_state.assert_called_once_with("conversation")

        with mock.patch.object(dashboard_app, "_save_dashboard_state") as save_state:
            put_response = run(
                dashboard_app.set_dashboard_state(
                    FakeRequest("active_run", body=b'{"value": {"runId": "r1"}}')
                )
            )
        self.assertEqual(response_json(put_response), {"success": True})
        save_state.assert_called_once_with("active_run", {"runId": "r1"})

        with mock.patch.object(dashboard_app, "_delete_dashboard_state") as delete_state:
            delete_response = run(dashboard_app.delete_dashboard_state(FakeRequest("active_run")))
        self.assertEqual(response_json(delete_response), {"success": True})
        delete_state.assert_called_once_with("active_run")

    def test_route_table_keeps_app_level_endpoint_identity(self):
        registered_routes = getattr(dashboard_app, "routes", None)
        if registered_routes is None:
            registered_routes = getattr(dashboard_app.app, "routes", None)
        if registered_routes is None and hasattr(dashboard_app.app, "router"):
            registered_routes = getattr(dashboard_app.app.router, "routes", [])
        route_entries = [
            route
            for route in registered_routes or []
            if getattr(route, "path", None) == "/api/dashboard-state/{key}"
        ]

        by_method = {}
        for route in route_entries:
            methods = getattr(route, "methods", None)
            if methods is None:
                methods = getattr(route, "kwargs", {}).get("methods")
            methods = set(methods or {"GET"})
            if "PUT" in methods:
                by_method["PUT"] = route.endpoint
            elif "DELETE" in methods:
                by_method["DELETE"] = route.endpoint
            elif "GET" in methods:
                by_method["GET"] = route.endpoint

        self.assertIs(by_method.get("GET"), dashboard_app.get_dashboard_state)
        self.assertIs(by_method.get("PUT"), dashboard_app.set_dashboard_state)
        self.assertIs(by_method.get("DELETE"), dashboard_app.delete_dashboard_state)

    def test_route_module_does_not_import_app_py(self):
        source = Path(route_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("import app", source)
        self.assertNotIn("from app", source)


if __name__ == "__main__":
    unittest.main()
