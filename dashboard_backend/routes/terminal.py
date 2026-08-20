"""HTTP and WebSocket routes for the optional browser terminal."""

from __future__ import annotations

import asyncio
import ipaddress
import json
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import urlsplit

from starlette.responses import JSONResponse
try:
    from starlette.websockets import WebSocketDisconnect
except Exception:  # Lightweight dashboard test stubs may omit this module.
    class WebSocketDisconnect(Exception):
        pass

from dashboard_backend.services.terminal import (
    TerminalManager,
    TerminalSettings,
    secrets_match,
)

TERMINAL_COOKIE = "hermes_terminal_session"
MAX_INPUT_BYTES = 65536


def _header(scope: Any, name: str) -> str:
    headers = getattr(scope, "headers", None)
    if headers is not None and hasattr(headers, "get"):
        return str(headers.get(name, ""))
    raw_headers = getattr(scope, "scope", {}).get("headers", [])
    wanted = name.lower().encode("ascii")
    for key, value in raw_headers:
        if key.lower() == wanted:
            return value.decode("latin-1")
    return ""


def _peer_is_loopback(scope: Any) -> bool:
    client = getattr(scope, "client", None)
    if client is None:
        client = getattr(scope, "scope", {}).get("client")
    host = getattr(client, "host", None) or (client[0] if client else "")
    try:
        return ipaddress.ip_address(str(host).split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _origin_is_local(origin: str) -> bool:
    try:
        host = urlsplit(origin).hostname or ""
        return host.lower() == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _origin_allowed(scope: Any, settings: TerminalSettings) -> bool:
    origin = _header(scope, "origin").rstrip("/")
    if not origin:
        return False
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return False

    host = _header(scope, "host").lower()
    same_authority = parsed.netloc.lower() == host
    scope_scheme = getattr(scope, "scope", {}).get("scheme", "")
    expected_scheme = {"ws": "http", "wss": "https"}.get(
        scope_scheme, scope_scheme
    )
    forwarded = _header(scope, "x-forwarded-proto").split(",", 1)[0].strip()
    if forwarded in {"http", "https"}:
        expected_scheme = forwarded
    same_origin = same_authority and parsed.scheme == expected_scheme
    return same_origin or origin in settings.allowed_origins


def _access_allowed(scope: Any, settings: TerminalSettings) -> tuple[bool, str]:
    if not settings.available:
        return False, settings.reason
    if not _origin_allowed(scope, settings):
        return False, "Terminal request origin is not allowed."
    if not settings.allow_remote and (
        not _peer_is_loopback(scope) or not _origin_is_local(_header(scope, "origin"))
    ):
        return False, "Terminal is restricted to a loopback peer and local origin."
    return True, ""


def _cookie_value(scope: Any) -> str | None:
    cookie = SimpleCookie()
    try:
        cookie.load(_header(scope, "cookie"))
    except Exception:
        return None
    morsel = cookie.get(TERMINAL_COOKIE)
    return morsel.value if morsel else None


async def terminal_status_endpoint(
    request,
    *,
    manager: TerminalManager | None = None,
    settings_factory=TerminalSettings.from_env,
):
    settings = settings_factory()
    payload = settings.status_payload()
    if settings.allow_remote and manager is not None:
        payload["requires_auth"] = not manager.has_auth_session(
            _cookie_value(request)
        )
    # Same-origin GET requests do not consistently include Origin. Report
    # request-specific access only when the browser supplied one.
    if _header(request, "origin"):
        allowed, denial = _access_allowed(request, settings)
        payload["access_allowed"] = allowed
        if settings.available and not allowed:
            payload["access_reason"] = denial
    return JSONResponse(payload)


async def terminal_auth_endpoint(
    request,
    *,
    manager: TerminalManager,
    settings_factory=TerminalSettings.from_env,
):
    settings = settings_factory()
    allowed, denial = _access_allowed(request, settings)
    if not allowed:
        return JSONResponse({"ok": False, "error": denial}, status_code=403)
    if not settings.allow_remote:
        return JSONResponse({"ok": True, "auth_required": False})
    try:
        body = await request.json()
    except Exception:
        body = None
    supplied = body.get("token") if isinstance(body, dict) else ""
    if not isinstance(supplied, str) or not secrets_match(settings.auth_token, supplied):
        return JSONResponse({"ok": False, "error": "Invalid terminal token."}, status_code=403)

    session = manager.create_auth_session(settings.auth_ttl)
    response = JSONResponse({"ok": True, "auth_required": True})
    forwarded = _header(request, "x-forwarded-proto").split(",", 1)[0].strip()
    scheme = getattr(request, "url", None)
    scheme = getattr(scheme, "scheme", "")
    cookie_options = {
        "max_age": settings.auth_ttl,
        "httponly": True,
        "secure": scheme == "https" or forwarded == "https",
        "samesite": "strict",
        "path": "/api/terminal",
    }
    if hasattr(response, "set_cookie"):
        response.set_cookie(TERMINAL_COOKIE, session, **cookie_options)
    else:  # Lightweight dashboard test response stubs omit set_cookie/headers.
        cookie = SimpleCookie()
        cookie[TERMINAL_COOKIE] = session
        morsel = cookie[TERMINAL_COOKIE]
        morsel["max-age"] = str(settings.auth_ttl)
        morsel["httponly"] = True
        morsel["samesite"] = "strict"
        morsel["path"] = "/api/terminal"
        if cookie_options["secure"]:
            morsel["secure"] = True
        response.headers = {
            "set-cookie": cookie.output(header="").strip()
        }
    return response


async def terminal_websocket_endpoint(
    websocket,
    *,
    manager: TerminalManager,
    settings_factory=TerminalSettings.from_env,
):
    settings = settings_factory()
    allowed, denial = _access_allowed(websocket, settings)
    if allowed and settings.allow_remote and not manager.has_auth_session(
        _cookie_value(websocket)
    ):
        allowed, denial = False, "Terminal authentication is required."
    if not allowed:
        await websocket.close(code=4403, reason=denial[:123])
        return

    await manager.start()
    terminal_id = websocket.query_params.get("terminal_id")
    session = None
    try:
        if terminal_id:
            resume_token = websocket.query_params.get("resume_token")
            if not resume_token:
                await websocket.close(code=4403, reason="Terminal resume token is required")
                return
            try:
                session, replay, output_queue = await manager.attach(
                    terminal_id, resume_token, detach_ttl=settings.detach_ttl
                )
            except KeyError:
                await websocket.close(code=4404, reason="Unknown or expired terminal")
                return
            except PermissionError:
                await websocket.close(code=4403, reason="Invalid terminal resume token")
                return
            except RuntimeError:
                await websocket.close(code=4409, reason="Terminal is already attached")
                return
        else:
            session = await manager.spawn(settings)
            session, replay, output_queue = await manager.attach(session.terminal_id)
    except RuntimeError:
        await websocket.close(code=4429, reason="Terminal session limit reached")
        return
    except OSError:
        await websocket.close(code=1011, reason="Terminal process could not be started")
        return
    except asyncio.CancelledError:
        if session is not None and not session.attached:
            await manager.close(session.terminal_id)
        raise

    try:
        await websocket.accept()
        ready = {
            "type": "ready",
            "terminal_id": session.terminal_id,
            "reconnected": bool(terminal_id),
        }
        initial_resume_token = getattr(session, "initial_resume_token", None)
        if initial_resume_token:
            ready["resume_token"] = initial_resume_token
            session.initial_resume_token = None
        await websocket.send_text(json.dumps(ready))
        for chunk in replay:
            await websocket.send_bytes(chunk)
    except (WebSocketDisconnect, OSError, RuntimeError):
        await manager.detach(session.terminal_id)
        return
    except asyncio.CancelledError:
        await manager.detach(session.terminal_id)
        raise

    close_requested = False

    async def send_output() -> None:
        while True:
            chunk = await output_queue.get()
            if chunk is None:
                await websocket.send_text(json.dumps({"type": "exit"}))
                return
            await websocket.send_bytes(chunk)

    async def receive_input() -> None:
        nonlocal close_requested
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                return
            text = message.get("text")
            if text is None:
                await websocket.send_text(json.dumps({"type": "error", "error": "Expected a JSON text message."}))
                continue
            try:
                data = json.loads(text)
            except (TypeError, json.JSONDecodeError):
                await websocket.send_text(json.dumps({"type": "error", "error": "Malformed JSON message."}))
                continue
            if not isinstance(data, dict):
                await websocket.send_text(json.dumps({"type": "error", "error": "Expected a JSON object."}))
                continue
            kind = data.get("type")
            try:
                if kind == "input":
                    value = data.get("data")
                    if not isinstance(value, str) or len(value.encode("utf-8")) > MAX_INPUT_BYTES:
                        raise ValueError("Input must be a string no larger than 65536 bytes.")
                    await manager.write(session.terminal_id, value.encode("utf-8"))
                elif kind == "resize":
                    rows, cols = data.get("rows"), data.get("cols")
                    if not isinstance(rows, int) or isinstance(rows, bool) or not isinstance(cols, int) or isinstance(cols, bool):
                        raise ValueError("Resize requires integer rows and cols.")
                    await manager.resize(session.terminal_id, rows, cols)
                elif kind == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif kind == "close":
                    close_requested = True
                    await manager.close(session.terminal_id)
                    return
                else:
                    raise ValueError("Unknown terminal message type.")
            except (KeyError, ValueError, OSError) as exc:
                await websocket.send_text(json.dumps({"type": "error", "error": str(exc)}))

    tasks = [asyncio.create_task(send_output()), asyncio.create_task(receive_input())]
    try:
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if not close_requested and session.terminal_id in manager.sessions:
            await manager.detach(session.terminal_id)
