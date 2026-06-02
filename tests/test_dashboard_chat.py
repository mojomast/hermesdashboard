import asyncio
import json

import app as dashboard_app
from tests.dashboard_sources import dashboard_source


class FakeTask:
    def __init__(self):
        self.cancelled = False

    def done(self):
        return False

    def cancel(self):
        self.cancelled = True


class FakeRequest:
    def __init__(self, *, path_params=None, body=None):
        self.path_params = path_params or {}
        self._body = body if body is not None else b"{}"

    async def body(self):
        return self._body


def response_json(response):
    return json.loads(response.body.decode("utf-8"))


def test_chat_message_sanitizer_preserves_multimodal_image_content():
    messages = dashboard_app._sanitize_chat_messages([
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what is this?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                {"type": "unsupported", "value": "drop me"},
            ],
        },
        {"role": "assistant", "content": "ok"},
    ])

    assert isinstance(messages[0]["content"], list)
    assert messages[0]["content"] == [
        {"type": "text", "text": "what is this?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
    ]
    assert messages[1] == {"role": "assistant", "content": "ok"}


def test_chat_message_sanitizer_keeps_string_messages_and_filters_gateway_errors():
    messages = dashboard_app._sanitize_chat_messages([
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "Error: Hermes gateway unavailable"},
        {"role": "nonsense", "content": "drop"},
    ])

    assert messages == [{"role": "user", "content": "hello"}]


def test_chat_emergency_stop_frontend_contract():
    source = dashboard_source()

    assert 'id="chat-run-stop-btn"' in source
    assert 'class="btn emergency-stop-btn"' in source
    assert "Stop main agent" in source
    assert "requestInterrupt(activeRun?.sessionId || null, activeRun?.runId || null)" in source
    assert "const chatRunStopBtn = document.getElementById('chat-run-stop-btn');" in source
    assert "function requestInterrupt(sessionId, runId = null)" in source
    assert "if (!sessionId && !runId) return;" in source
    assert "Emergency stop the running main agent?" in source
    assert "'/api/runs/' + encodeURIComponent(runId) + '/stop'" in source
    assert "body: JSON.stringify({ action: 'stop', run_id: runId || '' })" in source
    assert "data.status === 'interrupt_queued' || data.status === 'stop_queued'" in source
    assert "btn.textContent = 'Stopping…'" in source
    assert "msg.textContent = 'Emergency stop queued.'" in source
    assert ".emergency-stop-btn" in source
    assert "type=\"module\"" not in source


def test_chat_stop_routes_are_registered():
    routes = set()
    for route in dashboard_app.routes:
        path = getattr(route, "path", None) or (route.args[0] if getattr(route, "args", None) else None)
        methods = getattr(route, "methods", None)
        if methods is None:
            methods = getattr(route, "kwargs", {}).get("methods", ["GET"])
        routes.add((path, tuple(sorted(methods))))

    assert ("/api/sessions/{session_id}/interrupt", ("POST",)) in routes
    assert ("/api/runs/{run_id}/stop", ("POST",)) in routes


def test_stop_run_marks_active_run_done_and_sets_interrupt_flag(monkeypatch):
    task = FakeTask()
    state = {
        "session_id": "sess-stop",
        "task": task,
        "done": False,
        "events": [],
    }
    monkeypatch.setitem(dashboard_app.ACTIVE_RUNS, "run-stop", state)
    dashboard_app.INTERRUPT_FLAGS.pop("sess-stop", None)

    response = asyncio.run(
        dashboard_app.stop_run(FakeRequest(path_params={"run_id": "run-stop"}))
    )
    payload = response_json(response)

    assert payload["status"] == "stop_queued"
    assert state["stop_requested"] is True
    assert state["done"] is True
    assert task.cancelled is True
    assert dashboard_app.INTERRUPT_FLAGS["sess-stop"] is True
    assert any("Stopped by user." in event.get("data", "") for event in state["events"])
    assert state["events"][-1] == {"data": "[DONE]"}

    dashboard_app.ACTIVE_RUNS.pop("run-stop", None)
    dashboard_app.INTERRUPT_FLAGS.pop("sess-stop", None)


def test_interrupt_session_stop_matches_active_main_run(monkeypatch):
    task = FakeTask()
    state = {
        "session_id": "sess-main",
        "task": task,
        "done": False,
        "events": [],
    }
    monkeypatch.setitem(dashboard_app.ACTIVE_RUNS, "run-main", state)
    dashboard_app.INTERRUPT_FLAGS.pop("sess-main", None)
    request = FakeRequest(
        path_params={"session_id": "sess-main"},
        body=json.dumps({"action": "stop"}).encode("utf-8"),
    )

    response = asyncio.run(dashboard_app.interrupt_session(request))
    payload = response_json(response)

    assert payload["status"] == "stop_queued"
    assert payload["session_id"] == "sess-main"
    assert state["stop_requested"] is True
    assert state["done"] is True
    assert task.cancelled is True
    assert dashboard_app.INTERRUPT_FLAGS["sess-main"] is True
    assert state["events"][-1] == {"data": "[DONE]"}

    dashboard_app.ACTIVE_RUNS.pop("run-main", None)
    dashboard_app.INTERRUPT_FLAGS.pop("sess-main", None)


def test_run_chat_stream_sync_honors_stop_requested(monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield 'data: {"type":"content","content":"should not render"}'
            yield 'data: [DONE]'

    class FakeStream:
        def __enter__(self):
            return FakeResponse()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def stream(self, *args, **kwargs):
            return FakeStream()

    state = {
        "session_id": "sess-sync",
        "stop_requested": True,
        "done": False,
        "events": [],
    }
    monkeypatch.setitem(dashboard_app.ACTIVE_RUNS, "run-sync-stop", state)
    monkeypatch.setattr(dashboard_app.httpx, "Client", FakeClient)

    dashboard_app._run_chat_stream_sync("run-sync-stop", [], "sess-sync")

    assert state["done"] is True
    assert any("Stopped by user." in event.get("data", "") for event in state["events"])
    assert not any("should not render" in event.get("data", "") for event in state["events"])
    assert state["events"][-1] == {"data": "[DONE]"}

    dashboard_app.ACTIVE_RUNS.pop("run-sync-stop", None)
