import asyncio
import json

import app as dashboard_app
from tests.dashboard_sources import dashboard_source


class FakeJsonRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def response_json(response):
    return json.loads(response.body.decode("utf-8"))


def test_approval_passphrase_frontend_contract():
    source = dashboard_source()

    assert 'id="approval-passphrase"' in source
    assert 'id="approval-passphrase-remember"' in source
    assert "APPROVAL_PASSPHRASE_STORAGE_KEY" in source
    assert "function currentApprovalPassphrase()" in source
    assert "passphrase_required" in source
    assert "body: JSON.stringify({ session_id: sessionId, decision, all: Boolean(options.all), passphrase })" in source


def test_approval_controls_are_inline_not_top_context_panel():
    source = dashboard_source()

    assert 'id="approval-panel"' not in source
    assert 'id="approval-list"' not in source
    assert "function renderApprovalChatBubble(approvals)" in source
    assert "id = 'approval-chat-bubble'" in source
    assert "Approve</button>" in source
    assert "Deny</button>" in source
    assert "Auto-approve controls live in the gear/options menu" in source
    assert 'id="approval-auto-toggle"' in source
    assert 'id="approval-auto-minutes"' in source


def test_configured_approval_passphrase_reads_config_without_restart(monkeypatch):
    monkeypatch.delenv("DASHBOARD_APPROVAL_PASSPHRASE", raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "get_config",
        lambda: {"dashboard": {"approvals": {"passphrase": "open-sesame"}}},
    )

    assert dashboard_app._configured_approval_passphrase() == "open-sesame"


def test_approval_respond_requires_passphrase_when_configured(monkeypatch):
    monkeypatch.setattr(dashboard_app, "_configured_approval_passphrase", lambda: "open-sesame")

    response = asyncio.run(
        dashboard_app.dashboard_approvals_respond_endpoint(FakeJsonRequest({"session_id": "s1", "decision": "once"}))
    )
    payload = response_json(response)

    assert response.status_code == 403
    assert payload == {"ok": False, "error": "approval passphrase required"}


def test_approval_respond_strips_passphrase_before_proxy(monkeypatch):
    captured = {}
    monkeypatch.setattr(dashboard_app, "_configured_approval_passphrase", lambda: "open-sesame")

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": True, "resolved": 1}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(dashboard_app.httpx, "AsyncClient", FakeClient)

    response = asyncio.run(
        dashboard_app.dashboard_approvals_respond_endpoint(
            FakeJsonRequest({"session_id": "s1", "decision": "session", "passphrase": "open-sesame"})
        )
    )
    payload = response_json(response)

    assert response.status_code == 200
    assert payload == {"ok": True, "resolved": 1}
    assert captured["json"] == {"session_id": "s1", "decision": "session"}
