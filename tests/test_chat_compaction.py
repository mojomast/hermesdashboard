import asyncio
import json
import subprocess

import app as dashboard_app
from tests.dashboard_sources import DASHBOARD_JS, dashboard_source, dashboard_template


class FakeRequest:
    def __init__(self, *, session_id="sess-old", body=None):
        self.path_params = {"session_id": session_id}
        self._body = body if body is not None else b"{}"

    async def body(self):
        return self._body


def response_json(response):
    return json.loads(response.body.decode("utf-8"))


def test_compact_button_and_frontend_contract():
    html = dashboard_template()
    source = dashboard_source()

    assert 'id="compact-chat-btn"' in html
    assert html.index('id="send-btn"') < html.index('id="compact-chat-btn"')
    assert html.index('id="compact-chat-btn"') < html.index('class="clear-btn"')
    assert "async function compactCurrentChat()" in source
    assert "body: JSON.stringify({ profile })" in source
    assert "activeChatSessionId = nextSessionId;" in source
    assert "await hydrateChatFromSession(nextSessionId" in source
    assert "activeChatRoomId === 'shared'" in source
    assert "chatCompactInFlight ? 'Compacting...' : 'Compact'" in source
    assert "manual-compact-20260822" in html


def test_compact_route_is_registered():
    routes = set()
    for route in dashboard_app.routes:
        path = getattr(route, "path", None) or (
            route.args[0] if getattr(route, "args", None) else None
        )
        methods = getattr(route, "methods", None)
        if methods is None:
            methods = getattr(route, "kwargs", {}).get("methods", ["GET"])
        routes.add((path, tuple(sorted(methods))))

    assert ("/api/sessions/{session_id}/compress", ("POST",)) in routes


def test_compact_proxy_uses_profile_api_key_and_returns_continuation(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""
        headers = {"X-Hermes-Session-Id": "sess-next"}

        def json(self):
            return {
                "status": "compressed",
                "old_session_id": "sess-old",
                "session_id": "sess-next",
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, **kwargs):
            captured.update(url=url, **kwargs)
            return FakeResponse()

    monkeypatch.setattr(dashboard_app.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        dashboard_app,
        "_api_key_for_profile",
        lambda profile: f"key-for-{profile}",
    )
    request = FakeRequest(
        body=json.dumps(
            {"profile": "researcher", "focus_topic": "deployment state"}
        ).encode("utf-8")
    )

    response = asyncio.run(dashboard_app.compress_session(request))

    assert response.status_code == 200
    if hasattr(response, "headers"):
        assert response.headers["x-hermes-session-id"] == "sess-next"
    assert response_json(response)["session_id"] == "sess-next"
    assert captured["url"].endswith(
        "/p/researcher/api/sessions/sess-old/compress"
    )
    assert captured["headers"]["Authorization"] == "Bearer key-for-researcher"
    assert captured["json"] == {"focus_topic": "deployment state"}


def test_compact_proxy_rejects_an_active_dashboard_run(monkeypatch):
    monkeypatch.setitem(
        dashboard_app.ACTIVE_RUNS,
        "run-active",
        {"session_id": "sess-old", "done": False},
    )

    response = asyncio.run(dashboard_app.compress_session(FakeRequest()))

    assert response.status_code == 409
    assert "active run" in response_json(response)["error"].lower()


def test_compact_frontend_adopts_rotated_session_before_hydration():
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    start = source.index("async function compactCurrentChat()")
    end = source.index("async function resetCurrentChatRoom", start)
    compact_function = source[start:end]
    script = f"""
let activeChatRoomId = 'main';
let activeChatSessionId = 'sess-old';
let sharedRoomRequestInFlight = false;
let chatResetInFlight = false;
let chatCompactInFlight = false;
let chatRoomSwitchInFlight = false;
let conversation = [];
const streamResumeRooms = new Set();
const events = [];
function profileForRoom() {{ return 'default'; }}
function getActiveRun() {{ return null; }}
function syncChatInputState() {{ events.push(['sync', chatCompactInFlight]); }}
function showToast(message, error) {{ events.push(['toast', message, Boolean(error)]); }}
function log() {{}}
async function fetchJsonOrThrow() {{
  return {{status: 'compressed', session_id: 'sess-next', before_messages: 20, after_messages: 4}};
}}
function saveMainChatSession(sessionId) {{ events.push(['saved', sessionId]); }}
async function saveBotRoom() {{ throw new Error('unexpected bot save'); }}
function invalidateCache() {{}}
async function hydrateChatFromSession(sessionId) {{ events.push(['hydrated', sessionId, activeChatSessionId]); }}
function refreshTokenUsageSoon() {{}}
{compact_function}
(async () => {{
  const result = await compactCurrentChat();
  console.log(JSON.stringify({{result, activeChatSessionId, events}}));
}})();
"""

    result = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["result"] is True
    assert payload["activeChatSessionId"] == "sess-next"
    assert ["saved", "sess-next"] in payload["events"]
    assert ["hydrated", "sess-next", "sess-next"] in payload["events"]
