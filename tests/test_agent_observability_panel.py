import asyncio
import datetime
import json
import sqlite3
import sys
import types


def _install_framework_stubs() -> None:
    if "starlette.applications" not in sys.modules:
        starlette = types.ModuleType("starlette")
        applications = types.ModuleType("starlette.applications")
        routing = types.ModuleType("starlette.routing")
        templating = types.ModuleType("starlette.templating")
        responses = types.ModuleType("starlette.responses")

        class Starlette:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        class Route:
            def __init__(self, path, endpoint, **kwargs):
                self.path = path
                self.endpoint = endpoint
                self.kwargs = kwargs

        class Jinja2Templates:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

            def TemplateResponse(self, *args, **kwargs):
                return None

        class _Response:
            def __init__(self, content=None, status_code=200):
                self.status_code = status_code
                if isinstance(content, (dict, list)):
                    self.body = json.dumps(content).encode("utf-8")
                elif isinstance(content, bytes):
                    self.body = content
                else:
                    self.body = str(content or "").encode("utf-8")

        class JSONResponse(_Response):
            pass

        class PlainTextResponse(_Response):
            pass

        applications.Starlette = Starlette
        routing.Route = Route
        templating.Jinja2Templates = Jinja2Templates
        responses.JSONResponse = JSONResponse
        responses.PlainTextResponse = PlainTextResponse

        sys.modules["starlette"] = starlette
        sys.modules["starlette.applications"] = applications
        sys.modules["starlette.routing"] = routing
        sys.modules["starlette.templating"] = templating
        sys.modules["starlette.responses"] = responses

    if "sse_starlette.sse" not in sys.modules:
        sse_starlette = types.ModuleType("sse_starlette")
        sse_module = types.ModuleType("sse_starlette.sse")

        class EventSourceResponse:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        sse_module.EventSourceResponse = EventSourceResponse
        sys.modules["sse_starlette"] = sse_starlette
        sys.modules["sse_starlette.sse"] = sse_module


_install_framework_stubs()

import app as dashboard_app
from tests.dashboard_sources import dashboard_source


class FakeRequest:
    def __init__(self, query_params=None):
        self.query_params = query_params or {}


def _decode(response):
    return json.loads(response.body.decode("utf-8"))


def _seed_state_db(root):
    db = root / "state.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            started_at TEXT,
            ended_at TEXT,
            source TEXT,
            model TEXT,
            summary TEXT,
            end_reason TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TEXT,
            tool_calls TEXT,
            tool_call_id TEXT,
            tool_name TEXT
        )
        """
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    fresh = now.isoformat().replace("+00:00", "Z")
    stale = (now - datetime.timedelta(hours=8)).isoformat().replace("+00:00", "Z")
    conn.executemany(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?)",
        [
            ("sess-ok", "Build dashboard", fresh, fresh, "api_server", "glm-5.1", "Added feature", None),
            ("sess-error", "Broken tool", fresh, fresh, "cli", "gemini-2.5-flash", "", "error"),
            ("sess-stale", "Still running", stale, None, "cron", "glm-5.1", "", None),
        ],
    )
    tool_calls = json.dumps([
        {"id": "call-1", "function": {"name": "terminal", "arguments": "{}"}},
        {"id": "call-2", "function": {"name": "read_file", "arguments": "{}"}},
    ])
    conn.executemany(
        "INSERT INTO messages (session_id, role, content, timestamp, tool_calls, tool_call_id, tool_name) VALUES (?,?,?,?,?,?,?)",
        [
            ("sess-ok", "user", "please add a panel", fresh, None, None, None),
            ("sess-ok", "assistant", "", fresh, tool_calls, None, None),
            ("sess-ok", "tool", json.dumps({"output": "ok", "exit_code": 0}), fresh, None, "call-1", "terminal"),
            ("sess-error", "assistant", "", fresh, json.dumps([{"id": "call-3", "function": {"name": "web_search"}}]), None, None),
            ("sess-error", "tool", json.dumps({"error": "timeout"}), fresh, None, "call-3", "web_search"),
        ],
    )
    conn.commit()
    conn.close()


def test_agent_observability_report_aggregates_sessions_tools_and_alerts(tmp_path, monkeypatch):
    _seed_state_db(tmp_path)
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    report = dashboard_app.get_agent_observability_report(window_hours=24, trace_limit=5)

    assert report["summary"]["sessions"] == 3
    assert report["summary"]["error_sessions"] == 1
    assert report["summary"]["stale_running_sessions"] == 1
    assert report["summary"]["tool_outputs"] == 2
    assert report["summary"]["tool_failures"] == 1
    assert report["summary"]["tool_failure_rate"] == 0.5
    assert {tool["name"] for tool in report["top_tools"]} >= {"terminal", "read_file", "web_search"}
    assert any(alert["title"] == "Tool failure rate elevated" for alert in report["alerts"])
    assert report["recent_traces"][0]["id"] in {"sess-ok", "sess-error"}
    assert "aggregate dashboards" in report["research_basis"][0]


def test_agent_observability_frontend_panel_is_wired():
    html = dashboard_source()

    assert 'data-panel="agent-observability"' in html
    assert 'id="agent-observability-panel"' in html
    assert "loadAgentObservability()" in html
    assert "'/api/agent-observability" in html or "`/api/agent-observability" in html
    assert "'agent-observability':'Agent Ops'" in html


def test_agent_observability_endpoint_and_route_are_wired(tmp_path, monkeypatch):
    _seed_state_db(tmp_path)
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    response = asyncio.run(dashboard_app.get_agent_observability_endpoint(FakeRequest({"window_hours": "24", "trace_limit": "2"})))
    payload = _decode(response)
    paths = [getattr(route, "path", None) for route in dashboard_app.routes]

    assert response.status_code == 200
    assert payload["summary"]["sessions"] == 3
    assert len(payload["recent_traces"]) == 2
    assert "/api/agent-observability" in paths
