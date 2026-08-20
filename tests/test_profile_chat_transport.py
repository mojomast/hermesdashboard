import asyncio
import json

import app as dashboard_app


def test_chat_transport_uses_named_profile_upstream(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            pass

        def iter_lines(self):
            yield "data: [DONE]"

    class Stream:
        def __enter__(self):
            return Response()

        def __exit__(self, *args):
            return False

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url, **kwargs):
            captured.update(method=method, url=url, headers=kwargs["headers"])
            return Stream()

    state = {"session_id": "resume-me", "events": [], "done": False}
    monkeypatch.setitem(dashboard_app.ACTIVE_RUNS, "profile-run", state)
    monkeypatch.setattr(dashboard_app.httpx, "Client", Client)
    monkeypatch.setattr(dashboard_app, "_api_key_for_profile", lambda profile: f"{profile}-profile-api-key")

    dashboard_app._run_chat_stream_sync("profile-run", [], "resume-me", "writer")

    assert captured["url"].endswith("/p/writer/v1/chat/completions")
    assert captured["headers"]["X-Hermes-Session-Id"] == "resume-me"
    assert captured["headers"]["X-Hermes-Blocking-Approvals"] == "true"
    assert captured["headers"]["Authorization"] == "Bearer writer-profile-api-key"
    dashboard_app.ACTIVE_RUNS.pop("profile-run", None)


def test_chat_transport_omits_session_header_for_fresh_session(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            pass

        def iter_lines(self):
            yield "data: [DONE]"

    class Stream:
        def __enter__(self):
            return Response()

        def __exit__(self, *args):
            return False

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url, **kwargs):
            captured.update(headers=kwargs["headers"])
            return Stream()

    state = {"session_id": None, "events": [], "done": False}
    monkeypatch.setitem(dashboard_app.ACTIVE_RUNS, "fresh-run", state)
    monkeypatch.setattr(dashboard_app.httpx, "Client", Client)

    dashboard_app._run_chat_stream_sync("fresh-run", [], None, "default")

    assert "X-Hermes-Session-Id" not in captured["headers"]
    dashboard_app.ACTIVE_RUNS.pop("fresh-run", None)


class Request:
    def __init__(self, body):
        self._body = body

    async def body(self):
        return json.dumps(self._body).encode()


def test_chat_handler_passes_profile_to_worker(monkeypatch):
    captured = {}

    async def fake_run(run_id, messages, session_id, profile):
        captured.update(run_id=run_id, session_id=session_id, profile=profile)
        state = dashboard_app.ACTIVE_RUNS[run_id]
        state["done"] = True
        state["events"].append({"data": "[DONE]"})

    monkeypatch.setattr(dashboard_app, "_run_chat_stream", fake_run)
    monkeypatch.setattr(dashboard_app.uuid, "uuid4", lambda: type("UUID", (), {"hex": "fresh"})())
    asyncio.run(dashboard_app.chat_stream(Request({
        "run_id": "profile-handler-run",
        "profile": "writer",
        "messages": [{"role": "user", "content": "hello"}],
    })))
    assert captured["profile"] == "writer"
    assert captured["session_id"] == "dashboard-fresh"
    assert dashboard_app.ACTIVE_RUNS["profile-handler-run"]["session_id"] == "dashboard-fresh"
    assert dashboard_app.ACTIVE_RUNS["profile-handler-run"]["profile"] == "writer"
    dashboard_app.ACTIVE_RUNS.pop("profile-handler-run", None)


def test_chat_handler_rejects_invalid_profile():
    response = asyncio.run(dashboard_app.chat_stream(Request({
        "profile": "../escape",
        "messages": [{"role": "user", "content": "hello"}],
    })))
    assert response.status_code == 400


def test_bot_chat_session_is_hidden_and_pinned(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            pass

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def patch(self, url, **kwargs):
            captured.update(url=url, json=kwargs["json"], headers=kwargs["headers"])
            return Response()

    monkeypatch.setattr(dashboard_app.httpx, "Client", Client)
    monkeypatch.setattr(dashboard_app, "_api_key_for_profile", lambda profile: f"{profile}-profile-api-key")
    dashboard_app._canonicalize_bot_chat_session("writer", "session/one")

    assert captured["url"].endswith("/p/writer/api/sessions/session%2Fone")
    assert captured["json"] == {"title": "Bot Chat", "hidden": True, "pinned": True}
    assert captured["headers"]["Authorization"] == "Bearer writer-profile-api-key"
