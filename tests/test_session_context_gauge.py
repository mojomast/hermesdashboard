import asyncio
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


def _create_sessions_table(conn, *, model_config=False):
    columns = "id TEXT PRIMARY KEY, model TEXT"
    if model_config:
        columns += ", model_config TEXT"
    conn.execute(f"CREATE TABLE sessions ({columns})")


def _create_api_calls_table(conn):
    conn.execute(
        """
        CREATE TABLE api_calls (
            api_call_id TEXT PRIMARY KEY,
            session_id TEXT,
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


def _create_prompt_budgets_table(conn):
    conn.execute(
        """
        CREATE TABLE prompt_budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            timestamp REAL,
            total_input_tokens INTEGER,
            system_prompt_tokens INTEGER,
            developer_prompt_tokens INTEGER,
            tool_schema_tokens INTEGER,
            memory_tokens INTEGER,
            conversation_history_tokens INTEGER,
            tool_result_tokens INTEGER,
            current_user_message_tokens INTEGER
        )
        """
    )


def _seed_prompt_budgets_db(root):
    db = root / "state.db"
    conn = sqlite3.connect(db)
    _create_sessions_table(conn, model_config=True)
    _create_api_calls_table(conn)
    _create_prompt_budgets_table(conn)
    conn.execute(
        "INSERT INTO sessions VALUES (?,?,?)",
        (
            "sess-ctx",
            "model-alpha",
            json.dumps({"base_url": "https://api.example.com/v1"}),
        ),
    )
    conn.execute(
        "INSERT INTO api_calls VALUES (?,?,?,?,?,?,?,?,?)",
        ("call-1", "sess-ctx", "model-alpha", 100.0, 5000, 800, 1000, 500, 0),
    )
    conn.executemany(
        "INSERT INTO prompt_budgets (session_id, timestamp, total_input_tokens, system_prompt_tokens, developer_prompt_tokens, tool_schema_tokens, memory_tokens, conversation_history_tokens, tool_result_tokens, current_user_message_tokens) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("sess-ctx", 100.0, 9999, 9000, 0, 0, 0, 999, 0, 0),
            ("sess-ctx", 200.0, 32000, 10000, 2000, 4000, 1000, 12000, 2500, 500),
        ],
    )
    conn.commit()
    conn.close()


def _write_context_length_cache(root, entries):
    lines = ["context_lengths:"]
    for key, value in entries.items():
        lines.append(f"  {key}: {value}")
    (root / "context_length_cache.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_context_gauge_prefers_prompt_budgets_breakdown(tmp_path, monkeypatch):
    _seed_prompt_budgets_db(tmp_path)
    _write_context_length_cache(tmp_path, {"model-alpha@https://api.example.com/v1": 128000})
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    gauge = dashboard_app.get_session_context_gauge("sess-ctx")

    assert gauge["session_id"] == "sess-ctx"
    assert gauge["source"] == "prompt_budgets"
    assert gauge["stale"] is False
    assert gauge["model"] == "model-alpha"
    assert gauge["context_used"] == 32000
    assert gauge["context_max"] == 128000
    assert gauge["percent"] == 25.0
    assert gauge["breakdown"] == {
        "system_prompt_tokens": 10000,
        "developer_prompt_tokens": 2000,
        "tool_schema_tokens": 4000,
        "memory_tokens": 1000,
        "conversation_history_tokens": 12000,
        "tool_result_tokens": 2500,
        "current_user_message_tokens": 500,
    }


def test_context_gauge_falls_back_to_api_calls_without_prompt_budgets(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    _create_sessions_table(conn)
    _create_api_calls_table(conn)
    conn.execute("INSERT INTO sessions VALUES (?,?)", ("sess-calls", "model-beta"))
    conn.executemany(
        "INSERT INTO api_calls VALUES (?,?,?,?,?,?,?,?,?)",
        [
            ("call-old", "sess-calls", "model-beta", 100.0, 1000, 100, 0, 0, 0),
            ("call-new", "sess-calls", "model-beta", 200.0, 5000, 800, 1000, 500, 0),
        ],
    )
    conn.commit()
    conn.close()
    _write_context_length_cache(tmp_path, {"model-beta": 64000})
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    gauge = dashboard_app.get_session_context_gauge("sess-calls")

    assert gauge["source"] == "api_calls"
    assert gauge["stale"] is False
    assert gauge["model"] == "model-beta"
    assert gauge["context_used"] == 6500
    assert gauge["breakdown"] == {}
    assert gauge["context_max"] == 64000
    assert gauge["percent"] == 10.16


def test_context_gauge_stale_when_no_data(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    _create_sessions_table(conn)
    _create_api_calls_table(conn)
    conn.commit()
    conn.close()
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    gauge = dashboard_app.get_session_context_gauge("sess-ghost")

    assert gauge["session_id"] == "sess-ghost"
    assert gauge["source"] == "none"
    assert gauge["stale"] is True
    assert gauge["context_used"] is None
    assert gauge["context_max"] is None
    assert gauge["percent"] is None
    assert gauge["breakdown"] == {}
    assert gauge["model"] is None


def test_context_max_matches_exact_model_at_base_url_key(tmp_path, monkeypatch):
    _seed_prompt_budgets_db(tmp_path)
    _write_context_length_cache(
        tmp_path,
        {
            "model-alpha": 99999,
            "model-alpha@https://api.example.com/v1": 200000,
        },
    )
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    gauge = dashboard_app.get_session_context_gauge("sess-ctx")

    assert gauge["context_max"] == 200000


def test_context_max_falls_back_to_prefixed_cache_key(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    _create_sessions_table(conn)
    conn.execute("INSERT INTO sessions VALUES (?,?)", ("sess-prefix", "model-beta"))
    conn.commit()
    conn.close()
    _write_context_length_cache(tmp_path, {"model-beta@https://other.example.com/": 50000})
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    gauge = dashboard_app.get_session_context_gauge("sess-prefix")

    assert gauge["model"] == "model-beta"
    assert gauge["context_max"] == 50000


def test_context_max_falls_back_to_models_dev_cache(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    _create_sessions_table(conn)
    conn.execute("INSERT INTO sessions VALUES (?,?)", ("sess-dev", "model-gamma"))
    conn.commit()
    conn.close()
    (tmp_path / "models_dev_cache.json").write_text(
        json.dumps({"provider-x": {"models": {"model-gamma": {"limit": {"context": 96000}}}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    gauge = dashboard_app.get_session_context_gauge("sess-dev")

    assert gauge["context_max"] == 96000


def test_context_max_none_without_caches(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    _create_api_calls_table(conn)
    conn.execute(
        "INSERT INTO api_calls VALUES (?,?,?,?,?,?,?,?,?)",
        ("call-1", "sess-nocache", "model-delta", 100.0, 700, 100, 0, 0, 0),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    gauge = dashboard_app.get_session_context_gauge("sess-nocache")

    assert gauge["context_used"] == 700
    assert gauge["context_max"] is None
    assert gauge["percent"] is None


def test_session_context_endpoint_returns_gauge_and_route_is_registered(tmp_path, monkeypatch):
    _seed_prompt_budgets_db(tmp_path)
    _write_context_length_cache(tmp_path, {"model-alpha@https://api.example.com/v1": 128000})
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    response = asyncio.run(dashboard_app.get_session_context_endpoint(FakeRequest(path_params={"session_id": "sess-ctx"})))
    payload = _decode(response)
    paths = [getattr(route, "path", None) for route in dashboard_app.routes]

    assert response.status_code == 200
    assert payload["session_id"] == "sess-ctx"
    assert payload["source"] == "prompt_budgets"
    assert payload["context_used"] == 32000
    assert payload["context_max"] == 128000
    assert payload["percent"] == 25.0
    assert payload["stale"] is False
    assert "/api/sessions/{session_id}/context" in paths


def test_session_context_endpoint_404_when_database_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    response = asyncio.run(dashboard_app.get_session_context_endpoint(FakeRequest(path_params={"session_id": "sess-none"})))
    payload = _decode(response)

    assert response.status_code == 404
    assert payload["error"] == "No sessions database"


def test_token_usage_summary_includes_context_when_session_id_passed(tmp_path, monkeypatch):
    _seed_prompt_budgets_db(tmp_path)
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    report = dashboard_app.get_token_usage_summary(current_session_id="sess-ctx")

    assert report["context"]["session_id"] == "sess-ctx"
    assert report["context"]["source"] == "prompt_budgets"
    assert report["context"]["context_used"] == 32000


def test_token_usage_summary_context_is_none_without_session_id(tmp_path, monkeypatch):
    _seed_prompt_budgets_db(tmp_path)
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    report = dashboard_app.get_token_usage_summary()

    assert report["context"] is None


def test_token_usage_endpoint_includes_context_subobject(tmp_path, monkeypatch):
    _seed_prompt_budgets_db(tmp_path)
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    with_session = asyncio.run(dashboard_app.get_token_usage_endpoint(FakeRequest({"session_id": "sess-ctx"})))
    without_session = asyncio.run(dashboard_app.get_token_usage_endpoint(FakeRequest({})))

    assert with_session.status_code == 200
    assert _decode(with_session)["context"]["session_id"] == "sess-ctx"
    assert _decode(without_session)["context"] is None
