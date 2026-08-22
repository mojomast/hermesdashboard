import asyncio
import json
from types import SimpleNamespace

import pytest

import app as dashboard_app
import dashboard_backend.routes.tool_intent as tool_intent_route
from dashboard_backend.routes.tool_intent import tool_intent_endpoint
from dashboard_backend.services.tool_intent import (
    MODEL,
    PROVIDER,
    SYSTEM_PROMPT,
    ToolIntentBusy,
    ToolIntentService,
    _hermes_luna_call,
    _redact_call,
)


class FakeRequest:
    def __init__(self, payload, *, origin="http://localhost:8082", content_type="application/json"):
        self._body = json.dumps(payload).encode("utf-8")
        self.headers = {
            "origin": origin,
            "host": "localhost:8082",
            "content-type": content_type,
            "content-length": str(len(self._body)),
        }
        self.url = SimpleNamespace(scheme="http")

    async def stream(self):
        yield self._body


def response_text(response):
    return response.body.decode("utf-8")


def llm_response(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def test_tool_intent_service_uses_current_hermes_codex_luna_route():
    captured = {}

    async def fake_llm_call(**kwargs):
        captured.update(kwargs)
        kwargs["route_info"].update(
            provider="openai-codex",
            model="gpt-5.6-luna",
        )
        return llm_response("Checks repository status and recent commits.")

    service = ToolIntentService(
        llm_call=fake_llm_call,
        redactor=lambda value: value.replace("raw-secret", "redacted-secret"),
    )
    result = asyncio.run(
        service.describe(
            "terminal",
            {"command": "git status --short raw-secret", "workdir": "/workspace"},
        )
    )

    assert result == "Checks repository status and recent commits."
    assert captured["task"] is None
    assert captured["provider"] == "openai-codex"
    assert captured["model"] == "gpt-5.6-luna"
    assert captured["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert captured["messages"][1]["role"] == "user"
    assert "raw-secret" not in captured["messages"][1]["content"]
    assert "redacted-secret" in captured["messages"][1]["content"]
    assert captured["reasoning_config"] == {"enabled": False}
    assert "api_key" not in captured
    assert "base_url" not in captured


def test_tool_intent_service_discards_non_luna_fallback_response():
    async def fake_llm_call(**kwargs):
        kwargs["route_info"].update(provider="openai-codex", model="gpt-5.6-terra")
        return llm_response("Fallback response")

    service = ToolIntentService(llm_call=fake_llm_call, redactor=lambda value: value)

    assert asyncio.run(service.describe("execute_code", {"code": "print(1)"})) == ""


def test_default_call_resolves_only_the_fixed_codex_client(monkeypatch):
    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return llm_response("Runs the syntax check.")

    class FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=FakeCompletions())
            self.closed = False

        def close(self):
            self.closed = True

    client = FakeClient()

    def resolve(provider, model, *, async_mode):
        assert (provider, model, async_mode) == (PROVIDER, MODEL, False)
        return client, MODEL

    monkeypatch.setattr("agent.auxiliary_client.resolve_provider_client", resolve)
    route_info = {}
    response = asyncio.run(
        _hermes_luna_call(
            provider=PROVIDER,
            model=MODEL,
            messages=[{"role": "user", "content": "pwd"}],
            timeout=10,
            route_info=route_info,
        )
    )

    assert response.choices[0].message.content == "Runs the syntax check."
    assert route_info == {"provider": PROVIDER, "model": MODEL}
    assert calls[0]["extra_body"] == {"reasoning": {"enabled": False}}
    assert client.closed is True


def test_default_call_closes_a_client_with_an_unexpected_model(monkeypatch):
    client = SimpleNamespace(closed=False)
    client.close = lambda: setattr(client, "closed", True)
    monkeypatch.setattr(
        "agent.auxiliary_client.resolve_provider_client",
        lambda *args, **kwargs: (client, "gpt-5.6-terra"),
    )

    with pytest.raises(RuntimeError, match="fixed Codex Luna route"):
        asyncio.run(
            _hermes_luna_call(
                provider=PROVIDER,
                model=MODEL,
                messages=[],
                route_info={},
            )
        )

    assert client.closed is True


def test_default_redactor_removes_preserved_secret_fragments():
    redacted = _redact_call(
        "OPENAI_API_KEY=abcdefghijklmnopqrstuvwx sk-proj-abcdefghijklmnopqrstuvwx"
    )

    assert "abcdef" not in redacted
    assert "stuvwx" not in redacted
    assert "[REDACTED]" in redacted
    assert _redact_call("git diff main...feature") == "git diff main...feature"
    assert _redact_call("literal abcdef...wxyz") == "literal abcdef...wxyz"


def test_tool_intent_service_rejects_queueing_when_capacity_is_occupied():
    async def scenario():
        release = asyncio.Event()

        async def fake_llm_call(**kwargs):
            kwargs["route_info"].update(provider="openai-codex", model="gpt-5.6-luna")
            await release.wait()
            return llm_response("Runs the test suite.")

        service = ToolIntentService(
            llm_call=fake_llm_call,
            redactor=lambda value: value,
            max_concurrency=1,
        )
        first = asyncio.create_task(service.describe("terminal", {"command": "pytest"}))
        await asyncio.sleep(0)
        with pytest.raises(ToolIntentBusy):
            await service.describe("terminal", {"command": "git status"})
        release.set()
        assert await first == "Runs the test suite."

    asyncio.run(scenario())


def test_tool_intent_service_applies_a_process_rate_limit():
    async def fake_llm_call(**kwargs):
        kwargs["route_info"].update(provider="openai-codex", model="gpt-5.6-luna")
        return llm_response("Runs a command.")

    service = ToolIntentService(
        llm_call=fake_llm_call,
        redactor=lambda value: value,
        max_requests_per_minute=1,
    )
    assert asyncio.run(service.describe("terminal", {"command": "pwd"}))
    with pytest.raises(ToolIntentBusy):
        asyncio.run(service.describe("terminal", {"command": "ls"}))


def test_tool_intent_route_allows_only_same_origin_execution_calls(monkeypatch):
    calls = []

    class FakePlainTextResponse:
        def __init__(self, content="", status_code=200, headers=None):
            self.body = str(content).encode("utf-8")
            self.status_code = status_code
            self.headers = {key.lower(): value for key, value in (headers or {}).items()}

    monkeypatch.setattr(tool_intent_route, "PlainTextResponse", FakePlainTextResponse)

    async def describe(tool, arguments):
        calls.append((tool, arguments))
        return "Runs the dashboard syntax check."

    response = asyncio.run(
        tool_intent_endpoint(
            FakeRequest({"tool": "terminal", "arguments": {"command": "node --check app.js"}}),
            describe=describe,
        )
    )
    assert response.status_code == 200
    assert response_text(response) == "Runs the dashboard syntax check."
    assert calls == [("terminal", {"command": "node --check app.js"})]
    assert response.headers["cache-control"] == "no-store"

    non_execution = asyncio.run(
        tool_intent_endpoint(
            FakeRequest({"tool": "read_file", "arguments": {"path": "app.py"}}),
            describe=describe,
        )
    )
    cross_origin = asyncio.run(
        tool_intent_endpoint(
            FakeRequest(
                {"tool": "terminal", "arguments": {"command": "pwd"}},
                origin="https://example.com",
            ),
            describe=describe,
        )
    )
    assert non_execution.status_code == 400
    assert cross_origin.status_code == 403
    assert len(calls) == 1


def test_tool_intent_route_is_registered_for_post_only():
    matches = [
        route
        for route in dashboard_app.routes
        if getattr(route, "path", None) == "/api/tool-intent"
    ]
    assert len(matches) == 1
    methods = getattr(matches[0], "methods", None)
    if methods is None:
        methods = set(getattr(matches[0], "kwargs", {}).get("methods", []))
    assert methods == {"POST"}
