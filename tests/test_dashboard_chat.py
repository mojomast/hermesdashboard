import asyncio
import json

import app as dashboard_app
from tests.dashboard_sources import dashboard_source, dashboard_template


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
    assert "requestInterrupt(getActiveRun()?.sessionId || null, getActiveRun()?.runId || null)" in source
    assert "const chatRunStopBtn = document.getElementById('chat-run-stop-btn');" in source
    assert "function requestInterrupt(sessionId, runId = null)" in source
    assert "if (!sessionId && !runId) return;" in source
    assert "Emergency stop the running main agent?" in source
    assert "'/api/runs/' + encodeURIComponent(runId) + '/stop'" in source
    assert "body: JSON.stringify({ action: 'stop', run_id: runId || '' })" in source
    assert "data.status === 'interrupt_queued' || data.status === 'stop_queued'" in source
    assert "btn.textContent = 'Stopping...'" in source
    assert "msg.textContent = 'Emergency stop queued.'" in source
    assert ".emergency-stop-btn" in source
    assert "const btn = chatRunStopBtn;" in source
    assert "interrupt-btn-wrapper" not in source
    assert "chatRunStopBtn.disabled = stopQueued;" in source
    assert "streamResumeInFlight || stopQueued" not in source
    assert "type=\"module\"" not in source


def test_chat_header_run_disclosure_and_bottom_context_contract():
    html = dashboard_template()
    source = dashboard_source()

    heading_start = html.index('<header class="chat-room-heading">')
    heading_end = html.index("</header>", heading_start)
    run_status = html.index('id="chat-run-status"')
    run_details = html.index('id="chat-run-status-details"')
    details_end = html.index("</details>", run_details)
    run_actions = html.index('class="chat-run-status-actions"')
    input_position = html.index('class="input-container"')
    context_position = html.index('id="chat-context-panel"')

    assert heading_start < run_status < heading_end
    assert heading_start < run_details < details_end < run_actions < heading_end
    assert 'class="chat-working-spark"' in html
    assert '>Reattach<' in html
    assert '>Follow stream<' in html
    assert input_position < context_position
    assert 'id="chat-context-pills"' not in html
    assert 'id="chat-context-breakdown"' not in html
    assert 'role="progressbar"' in source
    assert 'aria-valuetext="${escapeHtml(title)}"' in source
    assert "renderContextGaugeHtml(percent, contextGaugeTooltip(info), 'chat')" in source
    assert ".chat-context .context-gauge { height: 9px;" in source
    assert "const cachedInfo = sessionContextCache.info;" in source
    assert "Stream ended before completion" in source
    assert "if (sawDone)" in source


def test_new_command_and_clear_chat_reset_session_contract():
    source = dashboard_source()

    assert "async function resetCurrentChatRoom(options = {})" in source
    assert "/^\\/(?:new|mew)$/i.test(message)" in source
    assert "if (await resetCurrentChatRoom({ freshSession: true }))" in source
    assert "async function clearChat()" in source
    assert "return resetCurrentChatRoom();" in source
    assert "saveMainChatSession(null);" in source
    assert "await saveBotRoom(roomId, [], null);" in source
    assert "getActiveRun(roomId) || streamResumeRooms.has(roomId) || sharedRoomRequestInFlight" in source
    assert "options.freshSession && roomId === 'shared'" in source
    assert "chatResetInFlight = true;" in source
    assert "if (!persisted)" in source
    assert "pendingImageAttachmentGeneration += 1;" in source
    reset_start = source.index("async function resetCurrentChatRoom(options = {})")
    reset_source = source[reset_start:source.index("function debounce", reset_start)]
    assert "clearActiveRun(" not in reset_source


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


def test_interrupt_session_hard_stops_active_child_and_closes_stream(monkeypatch):
    child_id = "child-emergency-stop"
    captured = {}
    state = {"done": False, "updated_at": 0, "events": []}
    monkeypatch.setitem(dashboard_app.ACTIVE_CHILD_STREAMS, child_id, state)
    dashboard_app.INTERRUPT_FLAGS.pop(child_id, None)

    class FakeResponse:
        text = ""

        def json(self):
            return {"status": "stop_queued"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, **kwargs):
            captured.update(url=url, **kwargs)
            return FakeResponse()

    monkeypatch.setattr(dashboard_app.httpx, "AsyncClient", FakeAsyncClient)
    request = FakeRequest(
        path_params={"session_id": child_id},
        body=json.dumps({"action": "stop", "mode": "hard"}).encode("utf-8"),
    )

    response = asyncio.run(dashboard_app.interrupt_session(request))
    payload = response_json(response)

    assert payload["status"] == "stop_queued"
    assert payload["mode"] == "hard"
    assert captured["url"].endswith(f"/api/subagents/{child_id}/control")
    assert captured["json"] == {"action": "stop", "mode": "hard"}
    assert state["done"] is True
    assert state["events"][-1] == {"data": "[DONE]"}
    assert dashboard_app.INTERRUPT_FLAGS[child_id] is True

    dashboard_app.ACTIVE_CHILD_STREAMS.pop(child_id, None)
    dashboard_app.INTERRUPT_FLAGS.pop(child_id, None)


def test_run_chat_stream_sync_routes_child_events_from_executed_sync_path(monkeypatch):
    child_id = "child-sync-route"

    class FakeResponse:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield 'data: {"hermes":{"type":"child_session_started","child_session_id":"child-sync-route","delegate_call_id":"delegate-1"}}'
            yield 'data: {"hermes":{"type":"tool_call","name":"read_file","call_id":"call-1","child_session_id":"child-sync-route"}}'
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

    state = {"session_id": "parent", "stop_requested": False, "done": False, "events": []}
    monkeypatch.setitem(dashboard_app.ACTIVE_RUNS, "run-sync-child", state)
    monkeypatch.setattr(dashboard_app.httpx, "Client", FakeClient)

    dashboard_app._run_chat_stream_sync("run-sync-child", [], "parent")

    child = dashboard_app.ACTIVE_CHILD_STREAMS[child_id]
    assert child["delegate_call_id"] == "delegate-1"
    assert any('"type": "tool_call"' in event["data"] for event in child["events"])

    dashboard_app.ACTIVE_RUNS.pop("run-sync-child", None)
    dashboard_app.ACTIVE_CHILD_STREAMS.pop(child_id, None)


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
