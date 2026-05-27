from pathlib import Path

import app as dashboard_app


TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "index.html"


def _html() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_dashboard_chat_tab_is_registered_with_navigation_and_router():
    html = _html()

    assert 'data-panel="dashboard-chat"' in html
    assert 'id="dashboard-chat-panel"' in html
    assert "{ id: 'dashboard-chat', label: 'Dashboard Chat' }" in html
    assert "'dashboard-chat'" in html.split("const validPanels =", 1)[1].split(";", 1)[0]
    assert "'dashboard-chat':'Dashboard Chat'" in html
    assert "case 'dashboard-chat': loadDashboardChat(); break;" in html


def test_dashboard_chat_frontend_is_jailed_to_channel_and_pm_tabs():
    html = _html()

    assert "/api/dashboard-chat/ws" in html
    assert "/api/dashboard-chat/status" in html
    assert "#hermesdashboard" in html
    assert "PM yourself" in html
    assert "type: 'say'" in html
    assert "type: 'selfpm'" in html
    assert "type: 'pm'" in html
    assert "openDashboardChatPmTab(name)" in html
    assert "dashboard-chat-targets" in html
    assert ".dashboard-chat-tab.blink" in html
    assert "Blocked: arbitrary" in html
    assert "dashboardChatJoined" in html
    assert "Wait for the server-confirmed #hermesdashboard join" in html
    assert "Connected to dashboard IRC bridge. Waiting for IRC registration" in html


def test_dashboard_chat_settings_are_visible_and_privacy_labeled():
    html = _html()

    assert "Dashboard Chat / IRC" in html
    assert 'id="dashboard-chat-hosts"' in html
    assert 'id="dashboard-chat-port"' in html
    assert 'id="dashboard-chat-tls"' in html
    assert 'id="dashboard-chat-nick-prefix"' in html
    assert 'id="dashboard-chat-ident"' in html
    assert 'id="dashboard-chat-realname"' in html
    assert 'id="dashboard-chat-channel-key"' in html
    assert "Defaults avoid local usernames, hostnames" in html
    assert "function saveDashboardChatSettings()" in html
    assert "dashboard_chat.ident" in html


def test_dashboard_chat_backend_routes_and_policy_are_registered():
    status_route = next((route for route in dashboard_app.routes if getattr(route, "path", "") == "/api/dashboard-chat/status"), None)
    assert status_route is not None
    assert getattr(status_route, "endpoint", None) is dashboard_app.dashboard_chat_status_endpoint

    ws_route = next((route for route in dashboard_app.routes if getattr(route, "path", "") == "/api/dashboard-chat/ws"), None)
    assert ws_route is not None
    assert getattr(ws_route, "endpoint", None) is dashboard_app.dashboard_chat_websocket_endpoint

    payload = dashboard_app._dashboard_chat_status_payload()
    assert payload["channel"] == "#hermesdashboard"
    assert payload["channel_key_configured"] is True
    assert payload["default_nick_prefix"] == "HermesDash"
    assert payload["ident"] == "hermesdash"
    assert payload["realname"] == "Hermes Dashboard"
    assert "PMs to users present" in payload["jail"]


def test_dashboard_chat_helpers_sanitize_and_parse_allowed_messages():
    assert dashboard_app._sanitize_dashboard_chat_nick("bad nick;/JOIN #other") == "badnickJOINother"
    assert dashboard_app._dashboard_chat_truncate_message("hello\r\nthere") == "hello  there"

    user_command = dashboard_app._dashboard_chat_user_command(
        "ChosenNick",
        {"ident": "hermesdash", "realname": "Hermes Dashboard"},
    )
    assert user_command == "USER hermesdash 0 * :Hermes Dashboard"
    assert "ChosenNick" not in user_command
    assert "mojo" not in user_command.lower()

    default_nick = dashboard_app._sanitize_dashboard_chat_nick("", "HermesDash")
    assert default_nick.startswith("HermesDash")
    assert "mojo" not in default_nick.lower()

    channel = dashboard_app._parse_irc_message(":alice!u@h PRIVMSG #hermesdashboard :hi")
    assert channel == {"type": "message", "scope": "channel", "nick": "alice", "text": "hi"}

    self_pm = dashboard_app._parse_irc_message(":alice!u@h PRIVMSG HermesDash123 :secret", current_nick="HermesDash123")
    assert self_pm == {"type": "message", "scope": "pm", "nick": "alice", "target": "HermesDash123", "text": "secret"}

    own_pm_echo = dashboard_app._parse_irc_message(":HermesDash123!u@h PRIVMSG alice :secret", current_nick="HermesDash123")
    assert own_pm_echo == {"type": "message", "scope": "pm", "nick": "HermesDash123", "target": "alice", "text": "secret", "self": True}

    names = dashboard_app._parse_irc_message(":irc.example 353 HermesDash123 = #hermesdashboard :@alice +bob HermesDash123")
    assert names == {"type": "names", "names": ["alice", "bob", "HermesDash123"]}
    assert dashboard_app._sanitize_dashboard_chat_pm_target("al ice;/JOIN") == "aliceJOIN"

    assert dashboard_app._parse_irc_prefix(":irc.example 001 HermesDash123 :Welcome") == (
        "irc.example",
        "001",
        "HermesDash123 :Welcome",
    )


def test_dashboard_chat_backend_waits_for_irc_registration_before_joining():
    source = Path(dashboard_app.__file__).read_text(encoding="utf-8")
    registration_block = source.split('if command == "001":', 1)[1].split('if command in {"376", "422"}', 1)[0]
    assert "registered = True" in registration_block
    assert "await send_join_once()" in registration_block
    assert "state\": \"joined" not in registration_block
    assert "MODE {chat_cfg['channel']} +k" not in source
    assert "self\": True" in source
    assert "allowed_pm_targets" in source
    assert "PRIVMSG {target} :{message}" in source
    assert "not in allowed_pm_targets" in source
