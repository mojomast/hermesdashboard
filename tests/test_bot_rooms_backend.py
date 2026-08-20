import asyncio
import json
import threading
from pathlib import Path

import pytest

from dashboard_backend.services import bot_rooms
from dashboard_backend.routes import bot_rooms as bot_room_routes


def test_room_persistence_is_durable_and_isolated(tmp_path):
    db_path = tmp_path / "dashboard_bots.db"
    lock = threading.Lock()
    bot_rooms.save_room(
        "shared", conversation=[{"role": "user", "content": "shared"}],
        session_id="shared-session", sessions={"default": "member-session"},
        db_path=db_path, lock=lock,
    )
    bot_rooms.save_room(
        "bot:writer", conversation=[{"role": "assistant", "content": "private"}],
        session_id="private-session", db_path=db_path, lock=lock,
    )

    new_lock = threading.Lock()
    shared = bot_rooms.load_room("shared", db_path=db_path, lock=new_lock)
    private = bot_rooms.load_room("bot:writer", db_path=db_path, lock=new_lock)
    assert shared["conversation"][0]["content"] == "shared"
    assert shared["sessions"] == {"default": "member-session"}
    assert private["conversation"][0]["content"] == "private"
    assert private["session_id"] == "private-session"
    assert len(bot_rooms.list_rooms(db_path=db_path, lock=new_lock)) == 2

    with pytest.raises(ValueError):
        bot_rooms.load_room("bot:../escape", db_path=db_path, lock=new_lock)


class FakeResponse:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    calls = []
    sessions = {}

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        base = url.rsplit("/api/sessions", 1)[0]
        session = self.sessions.get(base)
        return FakeResponse(data={"sessions": [session] if session else []})

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if url.endswith("/api/sessions"):
            base = url.rsplit("/api/sessions", 1)[0]
            session = {"id": f"session-{len(self.sessions) + 1}", "title": bot_rooms.GROUP_TITLE}
            self.sessions[base] = session
            return FakeResponse(status=201, data={"session": session})
        name = "writer" if "/p/writer/" in url else "default"
        content = json.dumps(
            {"action": "pass", "content": "", "invite": [], "expects_reply": False}
            if name == "writer" else
            {"action": "speak", "content": "Hello @writer", "invite": [], "expects_reply": False}
        )
        return FakeResponse(data={"message": {"role": "assistant", "content": content}})

    def patch(self, url, **kwargs):
        self.calls.append(("PATCH", url, kwargs))
        return FakeResponse(data={"session": {}})


def test_shared_orchestration_is_serial_bounded_and_profile_aware(tmp_path):
    FakeClient.calls = []
    FakeClient.sessions = {}
    result = bot_rooms.orchestrate_shared_message(
        "Hi room",
        bots=[
            {"name": "writer", "hidden": False, "is_default": False},
            {"name": "secret", "hidden": True, "is_default": False},
            {"name": "default", "hidden": False, "is_default": True},
        ],
        db_path=tmp_path / "dashboard_bots.db",
        lock=threading.Lock(),
        hermes_api="http://hermes.test",
        api_key="do-not-leak",
        client_factory=FakeClient,
    )

    assert [entry.get("bot") for entry in result["conversation"]] == [None, "default"]
    assert result["errors"] == []
    assert result["room"]["sessions"].keys() == {"default", "writer"}
    urls = [call[1] for call in FakeClient.calls]
    assert any(url == "http://hermes.test/api/sessions" for url in urls)
    assert any(url == "http://hermes.test/p/writer/api/sessions" for url in urls)
    assert not any("secret" in url for url in urls)
    create_calls = [call for call in FakeClient.calls if call[0] == "POST" and call[1].endswith("/api/sessions")]
    assert all(call[2]["json"]["title"] == bot_rooms.GROUP_TITLE for call in create_calls)
    assert "do-not-leak" not in str(result)

    second = bot_rooms.orchestrate_shared_message(
        "Again", bots=[{"name": "default", "hidden": False, "is_default": True}],
        db_path=tmp_path / "dashboard_bots.db", lock=threading.Lock(),
        hermes_api="http://hermes.test", api_key="do-not-leak", client_factory=FakeClient,
    )
    assert second["room"]["sessions"]["default"] == result["room"]["sessions"]["default"]


class ScriptedClient(FakeClient):
    responses = {}
    prompts = []

    def post(self, url, **kwargs):
        if url.endswith("/api/sessions"):
            return super().post(url, **kwargs)
        self.calls.append(("POST", url, kwargs))
        name = next((part for part in url.split("/") if part in self.responses), "default")
        self.prompts.append((name, kwargs["json"]["message"]))
        replies = self.responses[name]
        reply = replies.pop(0) if len(replies) > 1 else replies[0]
        return FakeResponse(data={"message": {"content": reply}})


def envelope(action="speak", content="ok", invite=None, expects_reply=False):
    return json.dumps({
        "action": action, "content": content, "invite": invite or [],
        "expects_reply": expects_reply,
    })


def run_shared(tmp_path, message, responses, *, events=None):
    ScriptedClient.calls = []
    ScriptedClient.sessions = {}
    ScriptedClient.prompts = []
    ScriptedClient.responses = {name: list(values) for name, values in responses.items()}
    roster = [
        {"name": name, "hidden": False, "is_default": name == "default"}
        for name in responses
    ]
    return bot_rooms.orchestrate_shared_message(
        message, bots=roster, db_path=tmp_path / "rooms.db", lock=threading.Lock(),
        hermes_api="http://hermes.test", api_key="secret-key", client_factory=ScriptedClient,
        on_event=(events.append if events is not None else None),
    )


def test_mentions_choose_lead_and_context_is_progressive(tmp_path):
    result = run_shared(tmp_path, "Please ask @writer", {
        "default": [envelope(content="unused")],
        "writer": [envelope(content="Question for @reviewer?", invite=["reviewer"], expects_reply=True)],
        "reviewer": ["Plain answer"],
    })

    assert result["summary"]["spoken"] == ["writer", "reviewer", "writer"]
    assert [name for name, _ in ScriptedClient.prompts] == ["writer", "reviewer", "writer"]
    reviewer_prompt = ScriptedClient.prompts[1][1]
    assert "writer: Question for @reviewer?" in reviewer_prompt
    assert "<untrusted-shared-transcript>" in reviewer_prompt
    assert "private direct sessions" in reviewer_prompt
    assert "default" not in result["room"]["sessions"]
    persisted = bot_rooms.load_room("shared", db_path=tmp_path / "rooms.db", lock=threading.Lock())
    assert [entry.get("bot") for entry in persisted["conversation"]] == [None, "writer", "reviewer", "writer"]


def test_plain_fallback_mentions_schedule_questions_and_followup(tmp_path):
    result = run_shared(tmp_path, "@default start", {
        "default": ["@auditbot, what should we verify?", "Thanks, that answers it."],
        "auditbot": ["Verify persistence and the live transport."],
    })

    assert [name for name, _ in ScriptedClient.prompts] == ["default", "auditbot", "default"]
    assert result["summary"]["spoken"] == ["default", "auditbot", "default"]
    assert result["errors"] == []


def test_near_valid_envelope_is_salvaged_without_response_failure():
    reply = bot_rooms._parse_coordinator_reply(
        '{"content":"@writer, can you check this?","invite":"writer"}',
        ["default", "writer"],
    )

    assert reply == {
        "action": "speak",
        "content": "@writer, can you check this?",
        "invite": ["writer"],
        "expects_reply": True,
    }


def test_shared_room_uses_profile_scoped_api_keys(tmp_path):
    ScriptedClient.calls = []
    ScriptedClient.sessions = {}
    ScriptedClient.prompts = []
    ScriptedClient.responses = {
        "default": [envelope(content="default reply")],
        "writer": [envelope(content="writer reply")],
    }
    keys = {
        "default": "default-profile-api-key",
        "writer": "writer-profile-api-key",
    }

    result = bot_rooms.orchestrate_shared_message(
        "@default @writer answer",
        bots=[
            {"name": "default", "hidden": False, "is_default": True},
            {"name": "writer", "hidden": False, "is_default": False},
        ],
        db_path=tmp_path / "rooms.db",
        lock=threading.Lock(),
        hermes_api="http://hermes.test",
        api_key=lambda profile: keys[profile],
        client_factory=ScriptedClient,
    )

    auth_by_profile = {}
    for method, url, kwargs in ScriptedClient.calls:
        if method != "POST" or not url.endswith("/chat"):
            continue
        profile = "writer" if "/p/writer/" in url else "default"
        auth_by_profile[profile] = kwargs["headers"]["Authorization"]
    assert auth_by_profile == {
        "default": "Bearer default-profile-api-key",
        "writer": "Bearer writer-profile-api-key",
    }
    assert not any(key in json.dumps(result) for key in keys.values())


def test_pass_consults_only_one_alternate_and_session_is_reused(tmp_path):
    responses = {
        "default": [envelope("pass", "")],
        "writer": [envelope(content="I can help")],
        "reviewer": [envelope(content="must not run")],
    }
    first = run_shared(tmp_path, "hello", responses)
    assert [name for name, _ in ScriptedClient.prompts] == ["default", "reviewer"]
    session = first["room"]["sessions"]["default"]

    ScriptedClient.responses = {name: list(values) for name, values in responses.items()}
    second = bot_rooms.orchestrate_shared_message(
        "again", bots=[{"name": name, "hidden": False, "is_default": name == "default"} for name in responses],
        db_path=tmp_path / "rooms.db", lock=threading.Lock(), hermes_api="http://hermes.test",
        api_key="secret-key", client_factory=ScriptedClient,
    )
    assert second["room"]["sessions"]["default"] == session
    assert ScriptedClient.calls[-1][2]["json"]["message"]


def test_turn_time_and_consecutive_pass_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(bot_rooms, "MAX_COORDINATOR_TURNS", 1)
    limited = run_shared(tmp_path, "@default go", {
        "default": [envelope(content="ask @writer", invite=["writer"])],
        "writer": [envelope(content="too late")],
    })
    assert limited["summary"]["turns"] == 1
    assert limited["summary"]["stopped_reason"] == "turn_limit"

    monkeypatch.setattr(bot_rooms, "MAX_COORDINATOR_TURNS", 8)
    passed = run_shared(tmp_path / "passes", "hello", {
        "default": [envelope("pass", "")],
        "writer": [envelope(content="not consulted")],
        "reviewer": [envelope("pass", "")],
    })
    assert passed["summary"]["passes"] == 2
    assert passed["summary"]["stopped_reason"] == "pass_limit"
    assert len(ScriptedClient.prompts) == 2

    ticks = iter([0, 151])
    timed = bot_rooms.orchestrate_shared_message(
        "hello", bots=[{"name": "default", "hidden": False, "is_default": True}],
        db_path=tmp_path / "timed.db", lock=threading.Lock(), hermes_api="http://hermes.test",
        api_key="secret-key", client_factory=ScriptedClient, monotonic=lambda: next(ticks),
    )
    assert timed["summary"]["turns"] == 0
    assert timed["summary"]["stopped_reason"] == "time_limit"


def test_cycles_and_per_bot_turn_limits_are_prevented(tmp_path):
    result = run_shared(tmp_path, "@default start", {
        "default": [envelope(content="@writer?", invite=["writer"], expects_reply=True), envelope(content="done")],
        "writer": [envelope(content="@default?", invite=["default"], expects_reply=True)],
    })
    assert result["summary"]["turns"] <= bot_rooms.MAX_COORDINATOR_TURNS
    assert result["summary"]["spoken"].count("default") <= bot_rooms.MAX_TURNS_PER_BOT
    assert result["summary"]["spoken"].count("writer") <= bot_rooms.MAX_TURNS_PER_BOT
    assert [name for name, _ in ScriptedClient.prompts] == ["default", "writer", "default"]


class FakeRequest:
    def __init__(self, body):
        self._body = body

    async def body(self):
        return self._body


def test_stream_route_emits_assistant_then_complete_ndjson():
    async def scenario():
        async def send(message, emit):
            await asyncio.to_thread(emit, {"type": "message", "message": {"role": "assistant", "bot": "writer", "content": message}})
            return {"room": {"conversation": []}, "summary": {"turns": 1}, "errors": []}

        response = await bot_room_routes.shared_message_stream_endpoint(
            FakeRequest(b'{"message":"hello"}'), send_message=send,
        )
        chunks = [chunk async for chunk in response.body_iterator]
        return [json.loads(chunk) for chunk in chunks]

    events = asyncio.run(scenario())
    assert [event["type"] for event in events] == ["message", "complete"]
    assert events[0]["message"]["bot"] == "writer"
    assert events[1]["summary"]["turns"] == 1
    assert events[1]["room"] == {"conversation": []}
