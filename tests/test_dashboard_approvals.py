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
    assert "request_id: options.requestId || undefined" in source
    assert "always_scope: options.alwaysScope || undefined" in source


def test_approval_controls_are_inline_not_top_context_panel():
    source = dashboard_source()

    assert 'id="approval-panel"' not in source
    assert 'id="approval-list"' not in source
    assert "function renderApprovalChatBubble(approvals)" in source
    assert "id = 'approval-chat-bubble'" in source
    assert "Approve Once</button>" in source
    assert "Approve Session</button>" in source
    assert "Always Exact</button>" in source
    assert "Always Prefix</button>" in source
    assert "Always This Type</button>" in source
    assert "Prefix: <code>" in source
    assert "Deny</button>" in source
    assert "data-approval-decision=\"once\"" in source
    assert "data-approval-decision=\"session\"" in source
    assert "Boolean(approval.allow_session)" in source
    assert "Boolean(approval.allow_permanent)" in source
    assert "data-approval-decision=\"deny\"" in source
    assert "button.addEventListener('click'" in source
    assert "dataset.approvalSignature === signature" in source
    assert '<div class="approval-inline-command">' in source
    assert "command || 'No command provided'" in source
    assert '<details class="approval-inline-details">' not in source
    assert 'onclick="respondToApproval(' not in source
    assert "Auto-approve controls live in the gear/options menu" in source
    assert 'id="approval-auto-toggle"' in source
    assert 'id="approval-auto-minutes"' in source
    assert "activeRun?.approvalSessionId" in source
    assert "parsed.approval_session_id" in source


def test_chat_stream_enables_isolated_blocking_approvals(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {
            "X-Hermes-Session-Id": "chat-session-1",
            "X-Hermes-Approval-Session-Id": "approval-run-1",
        }

        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield "data: [DONE]"

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

        def stream(self, method, url, headers=None, json=None):
            captured["headers"] = headers
            return FakeStream()

    state = {"session_id": None, "stop_requested": False, "done": False, "events": []}
    monkeypatch.setitem(dashboard_app.ACTIVE_RUNS, "dashboard-run-1", state)
    monkeypatch.setattr(dashboard_app.httpx, "Client", FakeClient)

    dashboard_app._run_chat_stream_sync("dashboard-run-1", [], None)

    assert captured["headers"]["X-Hermes-Blocking-Approvals"] == "true"
    assert state["approval_session_id"] == "approval-run-1"
    run_state = json.loads(state["events"][0]["data"])
    assert run_state["approval_session_id"] == "approval-run-1"
    dashboard_app.ACTIVE_RUNS.pop("dashboard-run-1", None)


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
            FakeJsonRequest(
                {
                    "session_id": "s1",
                    "request_id": "req-1",
                    "decision": "always",
                    "always_scope": "exact",
                    "passphrase": "open-sesame",
                }
            )
        )
    )
    payload = response_json(response)

    assert response.status_code == 200
    assert payload == {"ok": True, "resolved": 1}
    assert captured["json"] == {
        "session_id": "s1",
        "request_id": "req-1",
        "decision": "always",
        "always_scope": "exact",
    }
