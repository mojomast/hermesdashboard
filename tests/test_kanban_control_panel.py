import asyncio
import json

import app as dashboard_app
from dashboard_backend.routes.kanban import kanban_control_endpoint
from dashboard_backend.services import kanban as kanban_service
from tests.dashboard_sources import dashboard_source


class Request:
    def __init__(self, body):
        self._body = json.dumps(body).encode("utf-8")

    async def body(self):
        return self._body


def decode(response):
    return json.loads(response.body.decode("utf-8"))


def test_kanban_status_uses_live_config_and_service_state(tmp_path, monkeypatch):
    manifest = tmp_path / "plugins" / "kanban" / "dashboard" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        kanban_service,
        "_service_state",
        lambda action, service=kanban_service.KANBAN_SERVICE: action in {"is-active", "is-enabled"},
    )

    status = kanban_service.get_kanban_status(
        get_config=lambda: {
            "kanban": {
                "enabled": True,
                "orchestrator_profile": "kanban-orchestrator",
                "default_assignee": "worker-bot",
                "max_in_progress": 2,
                "max_in_progress_per_profile": 1,
                "auto_decompose": False,
                "review_dispatch": False,
            }
        },
        agent_path=tmp_path,
    )

    assert status["installed"] is True
    assert status["enabled"] is True
    assert status["orchestrator_profile"] == "kanban-orchestrator"
    assert status["default_assignee"] == "worker-bot"
    assert status["auto_decompose"] is False
    assert status["review_dispatch"] is False


def test_kanban_control_orders_service_and_live_switch_safely(tmp_path, monkeypatch):
    calls = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(kanban_service, "_systemctl", lambda *args: calls.append(("systemctl", *args)) or Result())
    monkeypatch.setattr(kanban_service, "get_kanban_status", lambda **kwargs: {"enabled": True})
    setter = lambda key, value: calls.append(("config", key, value))

    kanban_service.set_kanban_enabled(
        True,
        get_config=lambda: {},
        agent_path=tmp_path,
        set_config_value=setter,
    )
    assert calls == [
        ("systemctl", "enable", "--now", kanban_service.KANBAN_SERVICE),
        ("config", "kanban.enabled", "true"),
    ]

    calls.clear()
    kanban_service.set_kanban_enabled(
        False,
        get_config=lambda: {},
        agent_path=tmp_path,
        set_config_value=setter,
    )
    assert calls == [
        ("config", "kanban.enabled", "false"),
        ("systemctl", "disable", "--now", kanban_service.KANBAN_SERVICE),
    ]


def test_kanban_control_requires_intent_and_authorization():
    denied = asyncio.run(
        kanban_control_endpoint(
            Request({"action": "disable", "intent": "kanban_deployment_control"}),
            set_enabled=lambda enabled: {"enabled": enabled},
            authorize=lambda passphrase: False,
        )
    )
    assert denied.status_code == 403

    invalid = asyncio.run(
        kanban_control_endpoint(
            Request({"action": "disable"}),
            set_enabled=lambda enabled: {"enabled": enabled},
            authorize=lambda passphrase: True,
        )
    )
    assert invalid.status_code == 400


def test_kanban_panel_and_routes_are_wired():
    html = dashboard_source()
    paths = {getattr(route, "path", None) for route in dashboard_app.routes}

    assert "/api/kanban" in paths
    assert "/api/kanban/control" in paths
    assert html.count('data-panel="kanban"') == 2
    assert 'id="kanban-panel"' in html
    assert 'id="kanban-open-board"' in html
    assert 'rel="noopener noreferrer"' in html
    assert "function loadKanban()" in html
    assert "function controlKanban(action)" in html
    assert "kanban_deployment_control" in html
    assert "currentApprovalPassphrase()" in html
    assert "'kanban'," in html
