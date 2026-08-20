import asyncio
import fcntl
import json
import os
import struct
import termios
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import dashboard_backend.services.terminal as terminal_service
from dashboard_backend.routes.terminal import (
    TERMINAL_COOKIE,
    terminal_auth_endpoint,
    terminal_status_endpoint,
    terminal_websocket_endpoint,
)
from dashboard_backend.services.terminal import (
    TerminalManager,
    TerminalSettings,
    build_terminal_env,
    login_shell_argv,
    parse_dotenv,
)


def run(coro):
    return asyncio.run(coro)


def settings(tmp_path, **overrides):
    values = {
        "enabled": True,
        "allow_remote": False,
        "running_in_docker": False,
        "auth_token": "",
        "allowed_origins": frozenset(),
        "cwd": tmp_path,
        "shell": "/bin/sh",
        "hermes_home": tmp_path / ".hermes",
        "dashboard_root": tmp_path / "dashboard",
        "detach_ttl": 60,
        "auth_ttl": 300,
        "max_sessions": 4,
    }
    values.update(overrides)
    return TerminalSettings(**values)


class FakeRequest:
    def __init__(
        self,
        body=None,
        *,
        origin="http://localhost:8081",
        host="localhost:8081",
        client="127.0.0.1",
        scheme="http",
    ):
        self._body = body
        self.headers = {"origin": origin, "host": host}
        self.client = SimpleNamespace(host=client)
        self.scope = {"scheme": scheme}
        self.url = SimpleNamespace(scheme=scheme)

    async def json(self):
        if isinstance(self._body, BaseException):
            raise self._body
        return self._body


def response_json(response):
    return json.loads(response.body.decode())


def test_disabled_and_docker_status_reasons(tmp_path):
    disabled = settings(tmp_path, enabled=False)
    response = run(
        terminal_status_endpoint(FakeRequest(), settings_factory=lambda: disabled)
    )
    payload = response_json(response)
    assert payload["enabled"] is False
    assert "DASHBOARD_TERMINAL_ENABLED" in payload["reason"]

    docker = settings(tmp_path, running_in_docker=True)
    response = run(
        terminal_status_endpoint(FakeRequest(), settings_factory=lambda: docker)
    )
    assert "Docker" in response_json(response)["reason"]


def test_environment_defaults_disabled_and_detects_docker(monkeypatch, tmp_path):
    for name in (
        "DASHBOARD_TERMINAL_ENABLED",
        "DASHBOARD_TERMINAL_ALLOW_REMOTE",
        "DASHBOARD_RUNNING_IN_DOCKER",
    ):
        monkeypatch.delenv(name, raising=False)
    marker = tmp_path / ".dockerenv"
    marker.touch()
    config = TerminalSettings.from_env(docker_marker=marker)
    assert config.enabled is False
    assert config.allow_remote is False
    assert config.running_in_docker is True
    assert config.available is False


def test_terminal_env_precedence_is_child_only(monkeypatch, tmp_path):
    hermes_home = tmp_path / "hermes"
    dashboard_root = tmp_path / "dashboard"
    hermes_home.mkdir()
    dashboard_root.mkdir()
    (hermes_home / ".env").write_text(
        "PROCESS_KEY=hermes\nHERMES_ONLY=one\nTERM=bad\n", encoding="utf-8"
    )
    (dashboard_root / ".env.local").write_text(
        "PROCESS_KEY=dashboard\nDASHBOARD_ONLY=two\nCOLORTERM=bad\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROCESS_KEY", "process")
    before = os.environ.copy()

    env = build_terminal_env(
        settings(tmp_path, hermes_home=hermes_home, dashboard_root=dashboard_root)
    )

    assert env["PROCESS_KEY"] == "dashboard"
    assert env["HERMES_ONLY"] == "one"
    assert env["DASHBOARD_ONLY"] == "two"
    assert env["TERM"] == "xterm-256color"
    assert env["COLORTERM"] == "truecolor"
    assert os.environ == before


def test_dotenv_parser_is_literal_and_skips_hostile_lines(tmp_path):
    marker = tmp_path / "executed"
    dotenv = tmp_path / ".env"
    dotenv.write_bytes(
        b"# comment\nexport GOOD='quoted value'\n"
        b'EMBEDDED="left=right"\n'
        + f"HOSTILE=$(touch {marker})\n".encode()
        + b"BAD NAME=value\nMISSING\nNUL=value\0ignored\nUNFINISHED='value\n"
    )

    values = parse_dotenv(dotenv)

    assert values == {
        "GOOD": "quoted value",
        "EMBEDDED": "left=right",
        "HOSTILE": f"$(touch {marker})",
    }
    assert not marker.exists()
    oversized = tmp_path / "oversized.env"
    oversized.write_bytes(b"A=" + b"x" * 32)
    assert parse_dotenv(oversized, max_bytes=16) == {}


def test_hermes_home_file_location_is_not_redirected(monkeypatch, tmp_path):
    original = tmp_path / "original"
    redirected = tmp_path / "redirected"
    dashboard = tmp_path / "dashboard"
    for directory in (original, redirected, dashboard):
        directory.mkdir()
    (original / ".env").write_text(
        f"HERMES_HOME={redirected}\nFROM_ORIGINAL=yes\n", encoding="utf-8"
    )
    (redirected / ".env").write_text("FROM_REDIRECTED=no\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(original))

    config = TerminalSettings.from_env(
        docker_marker=tmp_path / "no-docker", dashboard_root=dashboard
    )
    env = build_terminal_env(config)

    assert config.hermes_home == original.resolve()
    assert env["FROM_ORIGINAL"] == "yes"
    assert "FROM_REDIRECTED" not in env


def test_login_shell_argv():
    assert login_shell_argv("/bin/bash") == ["-bash"]
    assert login_shell_argv("/bin/sh") == ["-sh"]


def test_docker_spawn_does_not_parse_or_fork(monkeypatch, tmp_path):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("disabled Docker terminal attempted process setup")

    monkeypatch.setattr(terminal_service, "parse_dotenv", unexpected)
    monkeypatch.setattr(terminal_service.pty, "fork", unexpected)
    config = settings(tmp_path, running_in_docker=True)

    with pytest.raises(PermissionError):
        run(TerminalManager().spawn(config))


def test_status_does_not_expose_environment(tmp_path):
    secret_name = "SYNTHETIC_PRIVATE_NAME"
    secret_value = "synthetic-private-value"
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    (hermes_home / ".env").write_text(
        f"{secret_name}={secret_value}\n", encoding="utf-8"
    )
    config = settings(tmp_path, hermes_home=hermes_home)

    payload = json.dumps(config.status_payload())

    assert secret_name not in payload
    assert secret_value not in payload


def test_local_mode_requires_loopback_peer_and_local_origin(tmp_path):
    config = settings(tmp_path)
    proxied = FakeRequest(
        origin="https://dashboard.example.ts.net",
        host="dashboard.example.ts.net",
        client="127.0.0.1",
        scheme="https",
    )
    payload = response_json(
        run(terminal_status_endpoint(proxied, settings_factory=lambda: config))
    )
    assert payload["access_allowed"] is False
    assert "loopback peer and local origin" in payload["access_reason"]

    remote_peer = FakeRequest(client="100.64.0.2")
    payload = response_json(
        run(terminal_status_endpoint(remote_peer, settings_factory=lambda: config))
    )
    assert payload["access_allowed"] is False


def test_remote_auth_uses_random_httponly_cookie_without_leaking_secret(tmp_path):
    manager = TerminalManager()
    config = settings(
        tmp_path, allow_remote=True, auth_token="configured-secret", auth_ttl=300
    )
    request = FakeRequest(
        {"token": "configured-secret"},
        origin="https://dashboard.example.ts.net",
        host="dashboard.example.ts.net",
        client="100.64.0.2",
        scheme="https",
    )
    response = run(
        terminal_auth_endpoint(
            request, manager=manager, settings_factory=lambda: config
        )
    )
    assert response.status_code == 200
    assert b"configured-secret" not in response.body
    cookie = response.headers["set-cookie"]
    assert TERMINAL_COOKIE in cookie
    assert "configured-secret" not in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Secure" in cookie


def test_remote_mode_without_token_is_unavailable(tmp_path):
    config = settings(tmp_path, allow_remote=True, auth_token="")
    payload = response_json(
        run(
            terminal_status_endpoint(
                FakeRequest(), settings_factory=lambda: config
            )
        )
    )
    assert payload["enabled"] is False
    assert "DASHBOARD_TERMINAL_AUTH_TOKEN" in payload["reason"]


def test_real_pty_spawn_input_output_resize_and_cleanup(monkeypatch, tmp_path):
    async def exercise():
        manager = TerminalManager()
        home = tmp_path / "home"
        hermes_home = tmp_path / "hermes"
        dashboard_root = tmp_path / "dashboard"
        for directory in (home, hermes_home, dashboard_root):
            directory.mkdir()
        (home / ".bash_profile").write_text(
            "export LOGIN_PROFILE_MARKER=profile-loaded\n", encoding="utf-8"
        )
        (hermes_home / ".env").write_text(
            "SYNTHETIC_DOTENV=hermes-value\n", encoding="utf-8"
        )
        (dashboard_root / ".env.local").write_text(
            "SYNTHETIC_DOTENV=dashboard-value\n", encoding="utf-8"
        )
        monkeypatch.setenv("HOME", str(home))
        shell = "/bin/bash" if Path("/bin/bash").is_file() else "/bin/sh"
        if shell == "/bin/sh":
            (home / ".profile").write_text(
                "export LOGIN_PROFILE_MARKER=profile-loaded\n", encoding="utf-8"
            )
        config = settings(
            tmp_path,
            shell=shell,
            hermes_home=hermes_home,
            dashboard_root=dashboard_root,
        )
        session = await manager.spawn(config)
        attached, replay, queue = await manager.attach(session.terminal_id)
        assert attached is session

        await manager.resize(session.terminal_id, 37, 101)
        packed = fcntl.ioctl(session.fd, termios.TIOCGWINSZ, b"\0" * 8)
        rows, cols, _, _ = struct.unpack("HHHH", packed)
        assert (rows, cols) == (37, 101)

        await manager.write(session.terminal_id, b"printf '__PTY_OK__\\n'\n")
        output = b"".join(replay)
        deadline = asyncio.get_running_loop().time() + 5
        while b"__PTY_OK__" not in output and asyncio.get_running_loop().time() < deadline:
            chunk = await asyncio.wait_for(queue.get(), timeout=2)
            assert chunk is not None
            output += chunk
        assert b"__PTY_OK__" in output

        await manager.write(session.terminal_id, b"printf '__ENV__%s:%s\\n' \"$TERM\" \"$COLORTERM\"\n")
        deadline = asyncio.get_running_loop().time() + 5
        while b"__ENV__xterm-256color:truecolor" not in output and asyncio.get_running_loop().time() < deadline:
            chunk = await asyncio.wait_for(queue.get(), timeout=2)
            assert chunk is not None
            output += chunk
        assert b"__ENV__xterm-256color:truecolor" in output

        await manager.write(
            session.terminal_id,
            b"printf '__LOADED__%s:%s\\n' \"$SYNTHETIC_DOTENV\" \"$LOGIN_PROFILE_MARKER\"\n",
        )
        deadline = asyncio.get_running_loop().time() + 5
        expected = b"__LOADED__dashboard-value:profile-loaded"
        while expected not in output and asyncio.get_running_loop().time() < deadline:
            chunk = await asyncio.wait_for(queue.get(), timeout=2)
            assert chunk is not None
            output += chunk
        assert expected in output

        pid = session.pid
        await manager.close(session.terminal_id)
        assert session.terminal_id not in manager.sessions
        assert session.fd == -1
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            # A just-reaped child can briefly remain visible on some kernels.
            await asyncio.sleep(0.05)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pass
        await manager.shutdown()

    run(exercise())


def test_session_limit_and_resume_capability(tmp_path):
    async def exercise():
        manager = TerminalManager()
        config = settings(tmp_path, max_sessions=1)
        session = await manager.spawn(config)
        token = session.initial_resume_token
        await manager.attach(session.terminal_id)
        await manager.detach(session.terminal_id)

        try:
            await manager.attach(session.terminal_id, "wrong-token")
        except PermissionError:
            pass
        else:
            raise AssertionError("invalid resume token was accepted")

        attached, _, _ = await manager.attach(session.terminal_id, token)
        assert attached is session
        try:
            await manager.spawn(config)
        except RuntimeError as exc:
            assert "limit" in str(exc).lower()
        else:
            raise AssertionError("terminal session limit was not enforced")
        await manager.shutdown()

    run(exercise())


def test_simultaneous_spawns_never_exceed_session_limit(tmp_path):
    async def exercise():
        manager = TerminalManager()
        config = settings(tmp_path, max_sessions=1)
        results = await asyncio.gather(
            manager.spawn(config), manager.spawn(config), return_exceptions=True
        )
        assert len(manager.sessions) == 1
        assert sum(isinstance(result, RuntimeError) for result in results) == 1
        await manager.shutdown()

    run(exercise())


def test_two_sessions_and_close_are_isolated(tmp_path):
    async def exercise():
        manager = TerminalManager()
        config = settings(tmp_path, max_sessions=2)
        first, second = await asyncio.gather(
            manager.spawn(config), manager.spawn(config)
        )
        _, _, second_output = await manager.attach(second.terminal_id)

        await manager.close(first.terminal_id)
        assert first.terminal_id not in manager.sessions
        assert second.terminal_id in manager.sessions

        await manager.write(second.terminal_id, b"printf '__SECOND_ALIVE__\\n'\n")
        output = b""
        deadline = asyncio.get_running_loop().time() + 5
        while b"__SECOND_ALIVE__" not in output and asyncio.get_running_loop().time() < deadline:
            chunk = await asyncio.wait_for(second_output.get(), timeout=2)
            assert chunk is not None
            output += chunk
        assert b"__SECOND_ALIVE__" in output
        await manager.shutdown()

    run(exercise())


def test_attached_output_queue_is_bounded(tmp_path):
    async def exercise():
        manager = TerminalManager()
        session = await manager.spawn(settings(tmp_path))
        _, _, output = await manager.attach(session.terminal_id)

        for index in range(manager.MAX_OUTPUT_QUEUE_CHUNKS + 10):
            manager._queue_output(output, str(index).encode())

        assert output.qsize() == manager.MAX_OUTPUT_QUEUE_CHUNKS
        assert await output.get() == b"10"
        await manager.shutdown()

    run(exercise())


def test_detach_reconnect_buffer_and_ttl_cleanup(tmp_path):
    async def exercise():
        manager = TerminalManager()
        session = await manager.spawn(settings(tmp_path))
        _, _, _ = await manager.attach(session.terminal_id)
        await manager.detach(session.terminal_id)
        await manager.write(session.terminal_id, b"printf '__DETACHED__\\n'\n")
        deadline = asyncio.get_running_loop().time() + 3
        while not session.output_buffer and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        _, replay, _ = await manager.attach(
            session.terminal_id, session.initial_resume_token
        )
        assert b"__DETACHED__" in b"".join(replay)
        await manager.detach(session.terminal_id)
        await manager.cleanup_expired(
            now=(session.detached_at or time.monotonic()) + 2, detach_ttl=1
        )
        assert session.terminal_id not in manager.sessions
        await manager.shutdown()

    run(exercise())


def test_attach_enforces_detach_ttl_without_waiting_for_cleanup(tmp_path):
    async def exercise():
        manager = TerminalManager()
        session = await manager.spawn(settings(tmp_path))
        token = session.initial_resume_token
        await manager.attach(session.terminal_id)
        await manager.detach(session.terminal_id)
        detached_at = session.detached_at

        attached, _, _ = await manager.attach(
            session.terminal_id,
            token,
            detach_ttl=10,
            now=detached_at + 9.9,
        )
        assert attached is session
        await manager.detach(session.terminal_id)

        with pytest.raises(KeyError):
            await manager.attach(
                session.terminal_id,
                token,
                detach_ttl=10,
                now=session.detached_at + 10,
            )
        assert session.terminal_id not in manager.sessions
        await manager.shutdown()

    run(exercise())


class FakeWebSocket:
    def __init__(self, messages):
        self.headers = {"origin": "http://localhost:8081", "host": "localhost:8081"}
        self.client = SimpleNamespace(host="127.0.0.1")
        self.scope = {"scheme": "ws"}
        self.query_params = {}
        self.messages = list(messages)
        self.sent = []
        self.accepted = False
        self.closed = None

    async def accept(self):
        self.accepted = True

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)

    async def send_text(self, value):
        self.sent.append(("text", json.loads(value)))

    async def send_bytes(self, value):
        self.sent.append(("bytes", value))

    async def receive(self):
        await asyncio.sleep(0)
        return self.messages.pop(0)


class FakeManager:
    def __init__(self):
        self.sessions = {}
        self.closed = False

    async def start(self):
        pass

    async def spawn(self, _settings):
        session = SimpleNamespace(terminal_id="opaque-random-id")
        self.sessions[session.terminal_id] = session
        return session

    async def attach(self, terminal_id):
        return self.sessions[terminal_id], [], asyncio.Queue()

    async def write(self, terminal_id, data):
        pass

    async def resize(self, terminal_id, rows, cols):
        pass

    async def close(self, terminal_id):
        self.closed = True
        self.sessions.pop(terminal_id, None)

    async def detach(self, terminal_id):
        pass

    def has_auth_session(self, token):
        return False


def test_websocket_malformed_messages_are_safe(tmp_path):
    websocket = FakeWebSocket(
        [
            {"type": "websocket.receive", "text": "{"},
            {"type": "websocket.receive", "text": json.dumps({"type": "resize", "rows": "bad", "cols": 10})},
            {"type": "websocket.receive", "text": json.dumps({"type": "ping"})},
            {"type": "websocket.receive", "text": json.dumps({"type": "close"})},
        ]
    )
    manager = FakeManager()
    run(
        terminal_websocket_endpoint(
            websocket,
            manager=manager,
            settings_factory=lambda: settings(tmp_path),
        )
    )
    payloads = [value for kind, value in websocket.sent if kind == "text"]
    assert websocket.accepted
    assert payloads[0]["type"] == "ready"
    assert sum(payload.get("type") == "error" for payload in payloads) == 2
    assert any(payload.get("type") == "pong" for payload in payloads)
    assert manager.closed


def test_websocket_rejects_disabled_before_accept(tmp_path):
    websocket = FakeWebSocket([])
    run(
        terminal_websocket_endpoint(
            websocket,
            manager=FakeManager(),
            settings_factory=lambda: settings(tmp_path, enabled=False),
        )
    )
    assert not websocket.accepted
    assert websocket.closed[0] == 4403


def test_websocket_rejects_remote_connection_in_local_only_mode(tmp_path):
    websocket = FakeWebSocket([])
    websocket.headers = {
        "origin": "https://dashboard.example.ts.net",
        "host": "dashboard.example.ts.net",
    }
    websocket.client = SimpleNamespace(host="100.64.0.2")
    websocket.scope = {"scheme": "wss"}
    run(
        terminal_websocket_endpoint(
            websocket,
            manager=FakeManager(),
            settings_factory=lambda: settings(tmp_path),
        )
    )
    assert not websocket.accepted
    assert websocket.closed[0] == 4403


def test_app_registers_terminal_routes_and_websocket():
    import app as dashboard_app

    paths = [getattr(route, "path", None) for route in dashboard_app.routes]
    assert "/api/terminal/status" in paths
    assert "/api/terminal/auth" in paths
    if dashboard_app.WebSocketRoute is not None:
        assert "/api/terminal/ws" in paths
    else:
        source = Path(dashboard_app.__file__).read_text(encoding="utf-8")
        assert 'WebSocketRoute("/api/terminal/ws"' in source
