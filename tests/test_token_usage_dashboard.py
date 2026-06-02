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
        routing.WebSocketRoute = Route
        templating.Jinja2Templates = Jinja2Templates
        responses.JSONResponse = JSONResponse
        responses.PlainTextResponse = PlainTextResponse
        responses.StreamingResponse = PlainTextResponse

        sys.modules["starlette"] = starlette
        sys.modules["starlette.applications"] = applications
        sys.modules["starlette.routing"] = routing
        sys.modules["starlette.templating"] = templating
        sys.modules["starlette.responses"] = responses

    if "starlette.websockets" not in sys.modules:
        websockets = types.ModuleType("starlette.websockets")

        class WebSocket:
            pass

        class WebSocketDisconnect(Exception):
            pass

        websockets.WebSocket = WebSocket
        websockets.WebSocketDisconnect = WebSocketDisconnect
        sys.modules["starlette.websockets"] = websockets

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


class FakeRequest:
    def __init__(self, query_params=None, path_params=None):
        self.query_params = query_params or {}
        self.path_params = path_params or {}


def _decode(response):
    return json.loads(response.body.decode("utf-8"))


def _seed_token_usage_db(root):
    db = root / "state.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE api_calls (
            api_call_id TEXT PRIMARY KEY,
            session_id TEXT,
            provider TEXT,
            model TEXT,
            start_time REAL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cache_read_tokens INTEGER,
            cache_write_tokens INTEGER,
            reasoning_tokens INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            started_at REAL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cache_read_tokens INTEGER,
            cache_write_tokens INTEGER,
            reasoning_tokens INTEGER
        )
        """
    )
    now = datetime.datetime(2026, 5, 13, 12, 30, tzinfo=datetime.timezone.utc)
    ts = lambda dt: dt.timestamp()
    rows = [
        ("call-session", "sess-a", "zai", "glm", ts(now), 100, 40, 10, 5, 3),
        ("call-today", "sess-b", "zai", "glm", ts(now.replace(hour=9)), 50, 25, 0, 0, 0),
        ("call-week", "sess-c", "zai", "glm", ts(datetime.datetime(2026, 5, 11, 10, tzinfo=datetime.timezone.utc)), 200, 100, 0, 0, 10),
        ("call-month", "sess-d", "zai", "glm", ts(datetime.datetime(2026, 5, 1, 10, tzinfo=datetime.timezone.utc)), 10, 5, 0, 0, 0),
        ("call-overall", "sess-e", "zai", "glm", ts(datetime.datetime(2026, 4, 30, 10, tzinfo=datetime.timezone.utc)), 1000, 500, 0, 0, 0),
        ("call-null", "sess-f", "zai", "glm", ts(now.replace(hour=13)), None, None, None, None, None),
    ]
    conn.executemany("INSERT INTO api_calls VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    conn.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?)", ("sess-fallback", ts(now), 7, 8, 9, 10, 11))
    conn.commit()
    conn.close()


def test_token_usage_aggregate_reports_session_day_week_month_and_overall(tmp_path, monkeypatch):
    _seed_token_usage_db(tmp_path)
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)
    now = datetime.datetime(2026, 5, 13, 12, 30, tzinfo=datetime.timezone.utc)

    report = dashboard_app.get_token_usage_summary(now=now, current_session_id="sess-a")

    assert report["metric"] == "consumed_tokens"
    assert report["source_preference"] == "api_calls"
    assert report["current_session_id"] == "sess-a"
    assert report["windows"]["current_session"]["total_tokens"] == 158
    assert report["windows"]["current_session"]["call_count"] == 1
    assert report["windows"]["current_day"]["total_tokens"] == 233
    assert report["windows"]["current_week"]["total_tokens"] == 543
    assert report["windows"]["current_month"]["total_tokens"] == 558
    assert report["windows"]["overall"]["total_tokens"] == 2058


def test_token_usage_current_session_falls_back_to_sessions(tmp_path, monkeypatch):
    _seed_token_usage_db(tmp_path)
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)
    now = datetime.datetime(2026, 5, 13, 12, 30, tzinfo=datetime.timezone.utc)

    report = dashboard_app.get_token_usage_summary(now=now, current_session_id="sess-fallback")

    session = report["windows"]["current_session"]
    assert session["source"] == "sessions"
    assert session["total_tokens"] == 45


def test_token_usage_windows_fall_back_to_sessions_when_api_call_tokens_are_empty(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE api_calls (
            api_call_id TEXT PRIMARY KEY,
            session_id TEXT,
            start_time REAL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cache_read_tokens INTEGER,
            cache_write_tokens INTEGER,
            reasoning_tokens INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            started_at REAL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cache_read_tokens INTEGER,
            cache_write_tokens INTEGER,
            reasoning_tokens INTEGER
        )
        """
    )
    now = datetime.datetime(2026, 5, 13, 12, 30, tzinfo=datetime.timezone.utc)
    conn.execute("INSERT INTO api_calls VALUES (?,?,?,?,?,?,?,?)", ("empty-call", "sess-a", now.timestamp(), 0, 0, 0, 0, 0))
    conn.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?)", ("sess-a", now.timestamp(), 9, 8, 7, 6, 5))
    conn.commit()
    conn.close()
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    report = dashboard_app.get_token_usage_summary(now=now, current_session_id="sess-a")

    assert report["windows"]["current_session"]["source"] == "sessions"
    assert report["windows"]["current_session"]["total_tokens"] == 35
    assert report["windows"]["current_day"]["source"] == "sessions"
    assert report["windows"]["current_day"]["total_tokens"] == 35
    assert report["windows"]["overall"]["total_tokens"] == 35


def test_token_usage_endpoint_and_route_are_wired(tmp_path, monkeypatch):
    _seed_token_usage_db(tmp_path)
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    response = asyncio.run(dashboard_app.get_token_usage_endpoint(FakeRequest({"session_id": "sess-a"})))
    payload = _decode(response)
    paths = [getattr(route, "path", None) for route in dashboard_app.routes]

    assert response.status_code == 200
    assert payload["windows"]["current_session"]["total_tokens"] >= 158
    assert payload["current_session_id"] == "sess-a"
    assert "/api/token-usage" in paths


def test_token_usage_missing_database_returns_zero_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    report = dashboard_app.get_token_usage_summary(current_session_id="missing")

    assert report["available"] is False
    assert all(window["total_tokens"] == 0 for window in report["windows"].values())


def test_session_tokens_endpoint_reports_all_canonical_buckets_and_api_call_steps(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cache_read_tokens INTEGER,
            cache_write_tokens INTEGER,
            reasoning_tokens INTEGER,
            estimated_cost_usd REAL,
            cost_status TEXT,
            cost_source TEXT,
            model TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE api_calls (
            api_call_id TEXT PRIMARY KEY,
            session_id TEXT,
            start_time REAL,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cache_read_tokens INTEGER,
            cache_write_tokens INTEGER,
            reasoning_tokens INTEGER
        )
        """
    )
    conn.execute(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("sess-canonical", 100, 50, 25, 10, 5, 0.123, "estimated", "provider_models_api", "model-a"),
    )
    conn.executemany(
        "INSERT INTO api_calls VALUES (?,?,?,?,?,?,?,?,?)",
        [
            ("call-1", "sess-canonical", 1.0, "model-a", 60, 20, 10, 5, 2),
            ("call-2", "sess-canonical", 2.0, "model-a", 40, 30, 15, 5, 3),
        ],
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    response = asyncio.run(dashboard_app.get_session_tokens(FakeRequest(path_params={"session_id": "sess-canonical"})))
    payload = _decode(response)

    assert response.status_code == 200
    assert payload["input_tokens"] == 100
    assert payload["output_tokens"] == 50
    assert payload["cache_read_tokens"] == 25
    assert payload["cache_write_tokens"] == 10
    assert payload["reasoning_tokens"] == 5
    assert payload["total_tokens"] == 190
    assert payload["estimated_cost_usd"] == 0.123
    assert payload["cost_status"] == "estimated"
    assert payload["cost_source"] == "provider_models_api"
    assert [step["total_tokens"] for step in payload["steps"]] == [97, 93]
    assert payload["steps"][0]["cache_read_tokens"] == 10


def test_session_tokens_endpoint_falls_back_to_message_token_counts(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            input_tokens INTEGER,
            output_tokens INTEGER,
            model TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            role TEXT,
            token_count INTEGER,
            timestamp TEXT
        )
        """
    )
    conn.execute("INSERT INTO sessions VALUES (?,?,?,?)", ("sess-legacy", 0, 0, "model-b"))
    conn.executemany(
        "INSERT INTO messages VALUES (?,?,?,?,?)",
        [
            ("m1", "sess-legacy", "user", 11, "2026-01-01T00:00:00Z"),
            ("m2", "sess-legacy", "assistant", 17, "2026-01-01T00:00:01Z"),
        ],
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    response = asyncio.run(dashboard_app.get_session_tokens(FakeRequest(path_params={"session_id": "sess-legacy"})))
    payload = _decode(response)

    assert response.status_code == 200
    assert payload["input_tokens"] is None
    assert payload["output_tokens"] is None
    assert payload["cache_read_tokens"] == 0
    assert payload["cache_write_tokens"] == 0
    assert payload["reasoning_tokens"] == 0
    assert payload["total_tokens"] == 28
    assert [step["total_tokens"] for step in payload["steps"]] == [11, 17]
