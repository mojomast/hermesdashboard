import asyncio
import json
from pathlib import Path

import app as dashboard_app
from dashboard_backend.routes.dashboard_chat import dashboard_chat_websocket_endpoint
from dashboard_backend.services import dashboard_chat as chat_service
from tests.dashboard_sources import dashboard_source, raw_dashboard_template


class FakeRequest:
    pass


class FakeWebSocket:
    def __init__(self):
        self.accepted = False
        self.closed = False
        self.close_code = None
        self.sent = []

    async def accept(self):
        self.accepted = True

    async def send_text(self, value):
        self.sent.append(json.loads(value))

    async def close(self, code=1000):
        self.closed = True
        self.close_code = code


class WaitingWebSocket(FakeWebSocket):
    async def receive_json(self):
        await asyncio.Event().wait()


class FakeReader:
    def __init__(self, lines):
        self.lines = list(lines)

    async def readline(self):
        if self.lines:
            return self.lines.pop(0)
        return b""


class FakeWriter:
    def __init__(self):
        self.writes = []
        self.closed = False

    def write(self, value):
        self.writes.append(value)

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


def response_json(response):
    return json.loads(response.body.decode("utf-8"))


def route_entries():
    entries = set()
    for route in dashboard_app.routes:
        path = getattr(route, "path", None) or (route.args[0] if getattr(route, "args", None) else None)
        methods = getattr(route, "methods", None)
        if methods is None:
            methods = getattr(route, "kwargs", {}).get("methods", ["GET"])
        entries.add((path, tuple(sorted(methods)), getattr(route, "endpoint", None)))
    return entries


def test_dashboard_chat_tab_is_available_but_hidden_by_default():
    source = dashboard_source()
    shell = raw_dashboard_template()

    assert '{% include "dashboard/partials/panels/dashboard_chat.html" %}' in shell
    assert 'data-panel="dashboard-chat"' in source
    assert 'id="dashboard-chat-panel"' in source
    assert "{ id: 'dashboard-chat', label: 'Dashboard Chat'" in source
    assert "'dashboard-chat':'Dashboard Chat'" in source
    assert "case 'dashboard-chat': loadDashboardChat(); break;" in source
    assert "'dashboard-chat'" in source
    assert "const DEFAULT_VISIBLE_DASHBOARD_TABS" in source
    default_block = source.split("const DEFAULT_VISIBLE_DASHBOARD_TABS", 1)[1].split("]);", 1)[0]
    assert "'dashboard-chat'" not in default_block
    startup_block = source.split("// Initialize hash routing", 1)[1].split("handleHashChange();", 1)[0]
    assert "applyDashboardTabSettings();" in startup_block
    assert "type=\"module\"" not in source


def test_dashboard_chat_frontend_is_jailed_and_privacy_labeled():
    source = dashboard_source()

    assert "/api/dashboard-chat/ws" in source
    assert "/api/dashboard-chat/status" in source
    assert "#hermesdashboard" in source
    assert "type: 'say'" in source
    assert "type: 'selfpm'" in source
    assert "type: 'pm'" in source
    assert "openDashboardChatPmTab(name)" in source
    assert "dashboard-chat-targets" in source
    assert ".dashboard-chat-tab.blink" in source
    assert "Blocked: arbitrary" in source
    assert "Wait for the server-confirmed #hermesdashboard join" in source
    assert "Opening Dashboard Chat websocket and requesting IRC bridge connection" in source
    assert "Connected to dashboard IRC bridge. Waiting for IRC registration" not in source
    assert "Defaults avoid local usernames, hostnames" in source
    assert "dashboard-chat-channel-key" in source
    assert 'type="password"' in source
    assert "onclick=\"selectDashboardChatTarget('#hermesdashboard')\"" in source
    assert "function selectDashboardChatTarget(target)" in source
    assert "function ensureDashboardChatPmTab(name, options = {})" in source
    assert "function noteDashboardChatPmActivity(name)" in source
    assert "if (data.from && data.from !== 'self') noteDashboardChatPmActivity(data.from);" in source
    assert "if (data.from && data.from !== 'self') openDashboardChatPmTab(data.from);" not in source


def test_dashboard_chat_status_route_and_payload_do_not_expose_key(monkeypatch):
    config = {
        "dashboard_chat": {
            "enabled": True,
            "hosts": ["irc.example.test"],
            "port": 6697,
            "tls": True,
            "channel_key": "supersecret",
            "default_nick_prefix": "HermesDash",
            "ident": "hermesdash",
            "realname": "Hermes Dashboard",
        }
    }
    monkeypatch.setattr(dashboard_app, "get_config", lambda: config)

    response = asyncio.run(dashboard_app.dashboard_chat_status_endpoint(FakeRequest()))
    payload = response_json(response)

    assert payload["enabled"] is True
    assert payload["bridge_available"] is True
    assert payload["connected"] is False
    assert payload["channel"] == "#hermesdashboard"
    assert payload["hosts"] == ["irc.example.test"]
    assert payload["port"] == 6697
    assert payload["tls"] is True
    assert payload["default_nick_prefix"] == "HermesDash"
    assert payload["ident"] == "hermesdash"
    assert payload["realname"] == "Hermes Dashboard"
    assert payload["channel_key_configured"] is True
    assert "supersecret" not in json.dumps(payload)
    assert "arbitrary JOIN/RAW commands are blocked" in payload["jail"]

    paths = {path for path, _methods, _endpoint in route_entries()}
    assert "/api/dashboard-chat/status" in paths
    if dashboard_app.WebSocketRoute is not None:
        assert "/api/dashboard-chat/ws" in paths


def test_dashboard_chat_settings_payload_masks_channel_key(monkeypatch):
    config = {
        "dashboard_chat": {
            "enabled": True,
            "hosts": ["irc.example.test"],
            "channel_key": "supersecret",
        }
    }
    monkeypatch.setattr(dashboard_app, "get_config", lambda: config)
    monkeypatch.setattr(dashboard_app, "get_raw_config", lambda: config)
    monkeypatch.setattr(dashboard_app, "get_env", lambda: {})

    payload = dashboard_app._settings_payload()

    assert payload["config"]["dashboard_chat"]["channel_key"] == ""
    assert payload["raw_config"]["dashboard_chat"]["channel_key"] == ""
    assert payload["config"]["dashboard_chat"]["channel_key_configured"] is True
    assert "supersecret" not in json.dumps(payload)


def test_get_config_masks_dashboard_chat_channel_key(monkeypatch):
    config = {
        "dashboard_chat": {
            "enabled": True,
            "hosts": ["irc.example.test"],
            "channel_key": "supersecret",
        }
    }
    monkeypatch.setattr(dashboard_app, "get_raw_config", lambda: config)

    payload = response_json(asyncio.run(dashboard_app.get_config_endpoint(FakeRequest())))

    assert payload["dashboard_chat"]["channel_key"] == ""
    assert payload["dashboard_chat"]["channel_key_configured"] is True
    assert "supersecret" not in json.dumps(payload)


def test_dashboard_chat_runtime_config_validates_port(monkeypatch):
    monkeypatch.delenv("DASHBOARD_CHAT_IRC_PORT", raising=False)
    assert chat_service._dashboard_chat_runtime_config({"dashboard_chat": {"port": "6698"}})["port"] == 6698
    assert chat_service._dashboard_chat_runtime_config({"dashboard_chat": {"port": "nope"}})["port"] == 6697
    assert chat_service._dashboard_chat_runtime_config({"dashboard_chat": {"port": 0}})["port"] == 6697
    assert chat_service._dashboard_chat_runtime_config({"dashboard_chat": {"port": 70000}})["port"] == 6697

    monkeypatch.setenv("DASHBOARD_CHAT_IRC_PORT", "6699")
    assert chat_service._dashboard_chat_runtime_config({"dashboard_chat": {"port": 6698}})["port"] == 6699

    monkeypatch.setenv("DASHBOARD_CHAT_IRC_PORT", "70000")
    assert chat_service._dashboard_chat_runtime_config({"dashboard_chat": {"port": 6698}})["port"] == 6697

    monkeypatch.setenv("DASHBOARD_CHAT_IRC_PORT", "bad")
    assert chat_service._dashboard_chat_runtime_config({"dashboard_chat": {"port": 6698}})["port"] == 6697


def test_dashboard_chat_helpers_preserve_privacy_and_sanitize(monkeypatch):
    monkeypatch.setenv("USER", "alice")
    monkeypatch.setenv("LOGNAME", "alice")
    monkeypatch.setenv("HOSTNAME", "alice-laptop")

    cfg = chat_service._dashboard_chat_runtime_config({"dashboard_chat": {}})
    assert cfg["default_nick_prefix"] == "HermesDash"
    assert cfg["ident"] == "hermesdash"
    assert cfg["realname"] == "Hermes Dashboard"
    user_command = chat_service._dashboard_chat_user_command("HermesDashabc123", cfg)
    assert user_command == "USER hermesdash 0 * :Hermes Dashboard"
    assert "alice" not in user_command
    assert "laptop" not in user_command

    assert chat_service._sanitize_dashboard_chat_nick("9 bad nick;/JOIN #other", "HermesDash").startswith("HermesDash")
    assert chat_service._sanitize_dashboard_chat_pm_target("al ice;/JOIN") == "aliceJOIN"
    assert "\n" not in chat_service._dashboard_chat_truncate_message("hello\r\nJOIN #other")
    assert len(chat_service._dashboard_chat_truncate_message("x" * 999)) == chat_service.DASHBOARD_CHAT_MAX_MESSAGE_CHARS

    prefix, command, rest = chat_service._parse_irc_prefix(":nick!u@h PRIVMSG #hermesdashboard :hi")
    assert prefix == "nick!u@h"
    assert command == "PRIVMSG"
    assert rest == "#hermesdashboard :hi"

    msg = chat_service._parse_irc_message(":nick!u@h PRIVMSG #hermesdashboard :hi", "HermesDash")
    assert msg == {
        "type": "message",
        "from": "nick",
        "target": "#hermesdashboard",
        "text": "hi",
        "private": False,
        "own": False,
    }
    names = chat_service._parse_irc_message(":server 353 HermesDash = #hermesdashboard :@alice +bob", "HermesDash")
    assert names == {"type": "names", "names": ["alice", "bob"]}


def test_dashboard_chat_disabled_websocket_does_not_open_network():
    ws = FakeWebSocket()

    async def fail_open_connection(*args, **kwargs):  # pragma: no cover - should never run
        raise AssertionError("disabled Dashboard Chat must not open IRC sockets")

    asyncio.run(
        dashboard_chat_websocket_endpoint(
            ws,
            runtime_config=lambda: {"enabled": False},
            open_connection=fail_open_connection,
        )
    )

    assert ws.accepted is True
    assert ws.closed is True
    assert ws.close_code == 1000
    assert ws.sent[0]["status"] == "disabled"


def test_dashboard_chat_all_hosts_fail_closes_without_key_leak():
    ws = FakeWebSocket()

    async def fail_open_connection(host, port, ssl):
        raise OSError(f"bad key supersecret on {host}")

    asyncio.run(
        dashboard_chat_websocket_endpoint(
            ws,
            runtime_config=lambda: {
                "enabled": True,
                "hosts": ["irc1.example.test", "irc2.example.test"],
                "port": 6697,
                "tls": True,
                "channel_key": "supersecret",
                "default_nick_prefix": "HermesDash",
                "ident": "hermesdash",
                "realname": "Hermes Dashboard",
            },
            open_connection=fail_open_connection,
        )
    )

    assert ws.closed is True
    assert ws.close_code == 1011
    assert ws.sent[-1]["type"] == "error"
    assert "[redacted]" in ws.sent[-1]["text"]
    assert "supersecret" not in json.dumps(ws.sent)


def test_dashboard_chat_irc_eof_cancels_waiting_websocket_loop():
    ws = WaitingWebSocket()
    writer = FakeWriter()

    async def open_connection(host, port, ssl):
        return FakeReader([b""]), writer

    asyncio.run(
        asyncio.wait_for(
            dashboard_chat_websocket_endpoint(
                ws,
                runtime_config=lambda: {
                    "enabled": True,
                    "hosts": ["irc.example.test"],
                    "port": 6697,
                    "tls": True,
                    "channel_key": "supersecret",
                    "default_nick_prefix": "HermesDash",
                    "ident": "hermesdash",
                    "realname": "Hermes Dashboard",
                },
                open_connection=open_connection,
            ),
            timeout=1,
        )
    )

    assert writer.closed is True
    assert "supersecret" not in json.dumps(ws.sent)


def test_dashboard_chat_modules_do_not_import_app():
    root = Path(__file__).resolve().parents[1]
    assert "import app" not in (root / "dashboard_backend" / "services" / "dashboard_chat.py").read_text()
    assert "import app" not in (root / "dashboard_backend" / "routes" / "dashboard_chat.py").read_text()
