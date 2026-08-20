"""In-memory Unix PTY runtime for the optional browser terminal."""

from __future__ import annotations

import asyncio
import errno
import fcntl
import hmac
import hashlib
import os
import pty
import pwd
import re
import secrets
import signal
import struct
import termios
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MAX_DOTENV_BYTES = 1024 * 1024
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DASHBOARD_ROOT = Path(__file__).resolve().parents[2]


def _parse_dotenv_line(line: str) -> tuple[str, str] | None:
    if "\0" in line:
        return None
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export") and len(line) > 6 and line[6].isspace():
        line = line[6:].lstrip()
    if "=" not in line:
        return None
    name, raw_value = line.split("=", 1)
    name = name.strip()
    if not _ENV_NAME.fullmatch(name):
        return None

    raw_value = raw_value.strip()
    if not raw_value:
        return name, ""
    quote = raw_value[0]
    if quote in {"'", '"'}:
        value: list[str] = []
        escaped = False
        closing = None
        for index, character in enumerate(raw_value[1:], start=1):
            if quote == '"' and escaped:
                value.append(
                    {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}.get(
                        character, f"\\{character}"
                    )
                )
                escaped = False
            elif quote == '"' and character == "\\":
                escaped = True
            elif character == quote:
                closing = index
                break
            else:
                value.append(character)
        if escaped or closing is None:
            return None
        trailing = raw_value[closing + 1 :].strip()
        if trailing and not trailing.startswith("#"):
            return None
        return name, "".join(value)

    comment = re.search(r"\s+#", raw_value)
    if comment:
        raw_value = raw_value[: comment.start()].rstrip()
    return name, raw_value


def parse_dotenv(path: Path, *, max_bytes: int = MAX_DOTENV_BYTES) -> dict[str, str]:
    """Parse a bounded dotenv file literally, without expansion or execution."""
    try:
        with path.open("rb") as dotenv_file:
            contents = dotenv_file.read(max_bytes + 1)
    except (OSError, ValueError):
        return {}
    if len(contents) > max_bytes:
        return {}

    values: dict[str, str] = {}
    for raw_line in contents.splitlines():
        try:
            line = raw_line.decode("utf-8")
        except UnicodeDecodeError:
            continue
        parsed = _parse_dotenv_line(line)
        if parsed is not None:
            values[parsed[0]] = parsed[1]
    return values


def login_shell_argv(shell: str) -> list[str]:
    return [f"-{os.path.basename(shell)}"]


def build_terminal_env(settings: "TerminalSettings") -> dict[str, str]:
    """Build the shell environment without changing the dashboard process."""
    env = dict(os.environ)
    env.update(parse_dotenv(settings.hermes_home / ".env"))
    env.update(parse_dotenv(settings.dashboard_root / ".env.local"))
    env.update({"TERM": "xterm-256color", "COLORTERM": "truecolor"})
    return env


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"", "0", "false", "no", "off"}


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class TerminalSettings:
    enabled: bool
    allow_remote: bool
    running_in_docker: bool
    auth_token: str
    allowed_origins: frozenset[str]
    cwd: Path
    shell: str
    hermes_home: Path
    dashboard_root: Path
    detach_ttl: int
    auth_ttl: int
    max_sessions: int

    @property
    def available(self) -> bool:
        return self.enabled and not self.running_in_docker and (
            not self.allow_remote or bool(self.auth_token)
        )

    @property
    def reason(self) -> str:
        if self.running_in_docker:
            return (
                "Browser Terminal is unavailable in Docker dashboard mode because "
                "the dashboard process is not running on the host."
            )
        if not self.enabled:
            return "Browser terminal is disabled by DASHBOARD_TERMINAL_ENABLED."
        if self.allow_remote and not self.auth_token:
            return (
                "Remote browser terminal requires DASHBOARD_TERMINAL_AUTH_TOKEN."
            )
        if self.allow_remote:
            return "Browser terminal is enabled for authenticated remote access."
        return "Browser terminal is enabled for loopback access only."

    @classmethod
    def from_env(
        cls,
        *,
        docker_marker: Path = Path("/.dockerenv"),
        dashboard_root: Path = _DASHBOARD_ROOT,
    ) -> "TerminalSettings":
        home = Path.home().resolve()
        configured_cwd = os.getenv("DASHBOARD_TERMINAL_CWD", "").strip()
        configured_hermes_home = os.getenv("HERMES_HOME", "").strip()
        hermes_home = Path(configured_hermes_home or home / ".hermes").expanduser().resolve()
        candidates = [configured_cwd, str(hermes_home), str(home)]
        cwd = home
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate).expanduser().resolve()
            if path.is_dir():
                cwd = path
                break

        shell = ""
        try:
            candidate_shell = pwd.getpwuid(os.getuid()).pw_shell
        except (KeyError, OSError):
            candidate_shell = ""
        for candidate in (candidate_shell, "/bin/bash", "/bin/sh"):
            if (
                candidate
                and os.path.isabs(candidate)
                and os.path.isfile(candidate)
                and os.access(candidate, os.X_OK)
            ):
                shell = candidate
                break
        if not shell:
            raise RuntimeError("No executable Unix shell is available")

        origins = frozenset(
            origin.strip().rstrip("/")
            for origin in os.getenv("DASHBOARD_TERMINAL_ALLOWED_ORIGINS", "").split(",")
            if origin.strip()
        )
        return cls(
            enabled=_env_bool("DASHBOARD_TERMINAL_ENABLED"),
            allow_remote=_env_bool("DASHBOARD_TERMINAL_ALLOW_REMOTE"),
            running_in_docker=(
                _env_bool("DASHBOARD_RUNNING_IN_DOCKER") or docker_marker.exists()
            ),
            auth_token=os.getenv("DASHBOARD_TERMINAL_AUTH_TOKEN", ""),
            allowed_origins=origins,
            cwd=cwd,
            shell=shell,
            hermes_home=hermes_home,
            dashboard_root=dashboard_root.resolve(),
            detach_ttl=_bounded_int(
                "DASHBOARD_TERMINAL_DETACH_TTL_SECONDS", 60, 1, 86400
            ),
            auth_ttl=_bounded_int(
                "DASHBOARD_TERMINAL_AUTH_TTL_SECONDS", 28800, 60, 86400
            ),
            max_sessions=_bounded_int(
                "DASHBOARD_TERMINAL_MAX_SESSIONS", 4, 1, 32
            ),
        )

    def status_payload(self) -> dict[str, Any]:
        return {
            "enabled": self.available,
            "configured": self.enabled,
            "allow_remote": self.allow_remote,
            "requires_auth": self.allow_remote,
            "running_in_docker": self.running_in_docker,
            "reason": self.reason,
            "detach_ttl_seconds": self.detach_ttl,
            "max_sessions": self.max_sessions,
        }


@dataclass
class TerminalSession:
    terminal_id: str
    pid: int
    fd: int
    resume_token_hash: bytes
    initial_resume_token: str | None
    output_buffer: deque[bytes] = field(default_factory=deque)
    output_buffer_bytes: int = 0
    output_queue: asyncio.Queue[bytes | None] | None = None
    attached: bool = False
    detached_at: float | None = None
    exited: bool = False
    reader_task: asyncio.Task | None = None


class TerminalManager:
    """Owns PTYs, detached output, auth sessions, and bounded cleanup."""

    MAX_BUFFER_BYTES = 1024 * 1024
    MAX_OUTPUT_QUEUE_CHUNKS = 64

    def __init__(self) -> None:
        self.sessions: dict[str, TerminalSession] = {}
        self.auth_sessions: dict[str, float] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(1)
                await self.cleanup_expired()
        except asyncio.CancelledError:
            pass

    def create_auth_session(self, ttl: int) -> str:
        token = secrets.token_urlsafe(32)
        self.auth_sessions[token] = time.monotonic() + ttl
        return token

    def has_auth_session(self, token: str | None) -> bool:
        if not token:
            return False
        expires = self.auth_sessions.get(token)
        if expires is None:
            return False
        if expires <= time.monotonic():
            self.auth_sessions.pop(token, None)
            return False
        return True

    async def spawn(self, settings: TerminalSettings) -> TerminalSession:
        if not settings.available:
            raise PermissionError(settings.reason)
        env = build_terminal_env(settings)
        async with self._lock:
            if len(self.sessions) >= settings.max_sessions:
                raise RuntimeError("Terminal session limit reached")
            pid, fd = pty.fork()
            if pid == 0:  # pragma: no cover - this branch is replaced by exec
                try:
                    os.chdir(settings.cwd)
                    os.execve(settings.shell, login_shell_argv(settings.shell), env)
                except BaseException:
                    os._exit(127)
            try:
                os.set_blocking(fd, False)
                fcntl.ioctl(
                    fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0)
                )
                resume_token = secrets.token_urlsafe(32)
                session = TerminalSession(
                    terminal_id=secrets.token_urlsafe(24),
                    pid=pid,
                    fd=fd,
                    resume_token_hash=hashlib.sha256(
                        resume_token.encode("utf-8")
                    ).digest(),
                    initial_resume_token=resume_token,
                )
            except BaseException:
                try:
                    os.close(fd)
                except OSError:
                    pass
                await self._terminate_and_reap(pid)
                raise
            self.sessions[session.terminal_id] = session
        session.reader_task = asyncio.create_task(self._read_output(session))
        return session

    async def attach(
        self,
        terminal_id: str,
        resume_token: str | None = None,
        *,
        detach_ttl: int | None = None,
        now: float | None = None,
    ) -> tuple[TerminalSession, list[bytes], asyncio.Queue[bytes | None]]:
        expired_session = None
        async with self._lock:
            session = self.sessions.get(terminal_id)
            if session is None:
                raise KeyError("Unknown or expired terminal")
            if resume_token is not None:
                supplied_hash = hashlib.sha256(resume_token.encode("utf-8")).digest()
                if not hmac.compare_digest(session.resume_token_hash, supplied_hash):
                    raise PermissionError("Invalid terminal resume token")
            if session.attached:
                raise RuntimeError("Terminal is already attached")
            if (
                detach_ttl is not None
                and session.detached_at is not None
                and (time.monotonic() if now is None else now) - session.detached_at
                >= detach_ttl
            ):
                expired_session = self.sessions.pop(terminal_id)
            if expired_session is not None:
                session = None
            else:
                queue: asyncio.Queue[bytes | None] = asyncio.Queue(
                    maxsize=self.MAX_OUTPUT_QUEUE_CHUNKS
                )
                replay = list(session.output_buffer)
                session.output_buffer.clear()
                session.output_buffer_bytes = 0
                session.output_queue = queue
                session.attached = True
                session.detached_at = None
                if session.exited:
                    queue.put_nowait(None)
                return session, replay, queue
        await self._close_session(expired_session)
        raise KeyError("Unknown or expired terminal")

    async def detach(self, terminal_id: str) -> None:
        async with self._lock:
            session = self.sessions.get(terminal_id)
            if session is None:
                return
            session.attached = False
            session.output_queue = None
            session.detached_at = time.monotonic()

    async def write(self, terminal_id: str, data: bytes) -> None:
        session = self.sessions.get(terminal_id)
        if session is None or session.exited:
            raise KeyError("Terminal is not running")
        view = memoryview(data)
        while view:
            try:
                written = os.write(session.fd, view)
                view = view[written:]
            except BlockingIOError:
                await asyncio.sleep(0.01)
            except OSError as exc:
                if exc.errno in {errno.EIO, errno.EBADF}:
                    raise KeyError("Terminal is not running") from exc
                raise

    async def resize(self, terminal_id: str, rows: int, cols: int) -> None:
        session = self.sessions.get(terminal_id)
        if session is None or session.exited:
            raise KeyError("Terminal is not running")
        rows = max(1, min(1000, int(rows)))
        cols = max(1, min(1000, int(cols)))
        fcntl.ioctl(session.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    async def _wait_readable(self, fd: int) -> None:
        loop = asyncio.get_running_loop()
        ready = loop.create_future()

        def mark_ready() -> None:
            if not ready.done():
                ready.set_result(None)

        loop.add_reader(fd, mark_ready)
        try:
            await ready
        finally:
            loop.remove_reader(fd)

    async def _read_output(self, session: TerminalSession) -> None:
        try:
            while True:
                await self._wait_readable(session.fd)
                try:
                    chunk = os.read(session.fd, 65536)
                except BlockingIOError:
                    continue
                except OSError as exc:
                    if exc.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                if session.attached and session.output_queue is not None:
                    self._queue_output(session.output_queue, chunk)
                else:
                    self._buffer_output(session, chunk)
        except (asyncio.CancelledError, OSError):
            pass
        finally:
            session.exited = True
            self._close_fd(session)
            if session.output_queue is not None:
                self._queue_output(session.output_queue, None)

    @staticmethod
    def _queue_output(
        queue: asyncio.Queue[bytes | None], chunk: bytes | None
    ) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait(chunk)

    def _buffer_output(self, session: TerminalSession, chunk: bytes) -> None:
        session.output_buffer.append(chunk)
        session.output_buffer_bytes += len(chunk)
        while (
            session.output_buffer
            and session.output_buffer_bytes > self.MAX_BUFFER_BYTES
        ):
            session.output_buffer_bytes -= len(session.output_buffer.popleft())

    def _close_fd(self, session: TerminalSession) -> None:
        if session.fd < 0:
            return
        try:
            os.close(session.fd)
        except OSError:
            pass
        session.fd = -1

    async def close(self, terminal_id: str) -> None:
        async with self._lock:
            session = self.sessions.get(terminal_id)
            if session is None:
                return
            await self._close_session(session)
            if self.sessions.get(terminal_id) is session:
                self.sessions.pop(terminal_id, None)

    async def _close_session(self, session: TerminalSession) -> None:
        if not session.exited:
            try:
                os.killpg(session.pid, signal.SIGHUP)
            except (ProcessLookupError, PermissionError):
                pass
        self._close_fd(session)
        if session.reader_task and session.reader_task is not asyncio.current_task():
            session.reader_task.cancel()
            await asyncio.gather(session.reader_task, return_exceptions=True)
        await self._terminate_and_reap(session.pid)

    async def _terminate_and_reap(self, pid: int) -> None:
        leader_reaped = False
        for group_signal in (None, signal.SIGTERM, signal.SIGKILL):
            if group_signal is not None:
                try:
                    os.killpg(pid, group_signal)
                except (ProcessLookupError, PermissionError):
                    pass
            for _ in range(10):
                if not leader_reaped:
                    try:
                        waited, _ = os.waitpid(pid, os.WNOHANG)
                    except (ChildProcessError, OSError):
                        leader_reaped = True
                    else:
                        leader_reaped = waited == pid
                try:
                    os.killpg(pid, 0)
                except ProcessLookupError:
                    group_exists = False
                except PermissionError:
                    group_exists = True
                else:
                    group_exists = True
                if leader_reaped and not group_exists:
                    return
                await asyncio.sleep(0.01)

    async def cleanup_expired(
        self, *, now: float | None = None, detach_ttl: int | None = None
    ) -> None:
        current = time.monotonic() if now is None else now
        ttl = detach_ttl
        if ttl is None:
            ttl = TerminalSettings.from_env().detach_ttl
        async with self._lock:
            expired = [
                session
                for session in self.sessions.values()
                if not session.attached
                and session.detached_at is not None
                and current - session.detached_at >= ttl
            ]
            for session in expired:
                await self._close_session(session)
                if self.sessions.get(session.terminal_id) is session:
                    self.sessions.pop(session.terminal_id, None)
        self.auth_sessions = {
            token: expires
            for token, expires in self.auth_sessions.items()
            if expires > current
        }

    async def shutdown(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            await asyncio.gather(self._cleanup_task, return_exceptions=True)
            self._cleanup_task = None
        for terminal_id in list(self.sessions):
            await self.close(terminal_id)
        self.auth_sessions.clear()


def secrets_match(configured: str, supplied: str) -> bool:
    return bool(configured and supplied) and hmac.compare_digest(configured, supplied)


terminal_manager = TerminalManager()
