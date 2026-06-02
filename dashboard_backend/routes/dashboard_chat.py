"""Route wrappers for the optional Dashboard Chat / IRC bridge."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

from starlette.responses import JSONResponse

from dashboard_backend.services.dashboard_chat import (
    _dashboard_chat_truncate_message,
    _dashboard_chat_user_command,
    _parse_irc_message,
    _sanitize_dashboard_chat_nick,
    _sanitize_dashboard_chat_pm_target,
)


async def dashboard_chat_status_endpoint(
    request,
    *,
    status_payload: Callable[[], dict[str, Any]],
):
    return JSONResponse(status_payload())


async def dashboard_chat_websocket_endpoint(
    websocket,
    *,
    runtime_config: Callable[[], dict[str, Any]],
    open_connection: Callable[..., Awaitable[tuple[Any, Any]]] = asyncio.open_connection,
):
    """Minimal jailed IRC websocket bridge.

    The route is inert unless `dashboard_chat.enabled` is true. Tests inject a
    fake `open_connection`; production only attempts network after an explicit
    websocket connection to this optional bridge.
    """

    await websocket.accept()
    cfg = runtime_config()
    if not cfg.get("enabled"):
        await websocket.send_text(
            json.dumps(
                {
                    "type": "status",
                    "status": "disabled",
                    "text": "Dashboard Chat / IRC is disabled. Enable dashboard_chat.enabled first.",
                }
            )
        )
        await websocket.close(code=1000)
        return

    hosts = list(cfg.get("hosts") or [])
    if not hosts:
        await websocket.send_text(json.dumps({"type": "error", "text": "No IRC hosts configured."}))
        await websocket.close(code=1000)
        return

    nick = _sanitize_dashboard_chat_nick(None, cfg.get("default_nick_prefix"))
    reader = writer = None
    last_error = None

    def safe_error(value: Any) -> str:
        text = str(value or "")
        key = str(cfg.get("channel_key") or "")
        return text.replace(key, "[redacted]") if key else text

    for host in hosts:
        try:
            await websocket.send_text(
                json.dumps({"type": "status", "status": "connecting", "host": host})
            )
            reader, writer = await open_connection(host, cfg["port"], ssl=cfg["tls"])
            break
        except Exception as exc:  # pragma: no cover - exercised with fakes in tests
            last_error = safe_error(exc)
            reader = writer = None
    if reader is None or writer is None:
        await websocket.send_text(
            json.dumps({"type": "error", "text": f"Unable to connect to IRC bridge: {last_error}"})
        )
        await websocket.close(code=1011)
        return

    channel = cfg.get("channel") or "#hermesdashboard"
    joined = False
    registered = False
    allowed_pm_targets: set[str] = {nick.lower()}

    def send_irc(line: str) -> None:
        writer.write((line + "\r\n").encode("utf-8"))

    async def drain() -> None:
        maybe = writer.drain()
        if hasattr(maybe, "__await__"):
            await maybe

    async def send_join_once() -> None:
        key = str(cfg.get("channel_key") or "")
        send_irc(f"JOIN {channel} {key}" if key else f"JOIN {channel}")
        await drain()
        await websocket.send_text(
            json.dumps({"type": "status", "status": "joining", "channel": channel})
        )

    send_irc(f"NICK {nick}")
    send_irc(_dashboard_chat_user_command(nick, cfg))
    await drain()
    await websocket.send_text(
        json.dumps(
            {
                "type": "status",
                "status": "connected",
                "nick": nick,
                "text": "Connected to dashboard IRC bridge. Waiting for IRC registration.",
            }
        )
    )

    async def irc_loop() -> None:
        nonlocal joined, registered, nick
        while True:
            raw = await reader.readline()
            if not raw:
                break
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith("PING "):
                send_irc("PONG " + line.split(" ", 1)[1])
                await drain()
                continue
            parts = line.split(" ")
            command = parts[1].upper() if line.startswith(":") and len(parts) > 1 else parts[0].upper()
            if command == "001" and not registered:
                registered = True
                await websocket.send_text(json.dumps({"type": "status", "status": "registered", "nick": nick}))
                await send_join_once()
                continue
            parsed = _parse_irc_message(line, nick)
            if not parsed:
                continue
            if parsed["type"] == "join" and parsed.get("nick", "").lower() == nick.lower():
                joined = True
                await websocket.send_text(json.dumps({"type": "status", "status": "joined", "channel": channel}))
            elif parsed["type"] == "names":
                for name in parsed.get("names") or []:
                    allowed_pm_targets.add(str(name).lower())
            elif parsed["type"] in {"part", "quit"}:
                allowed_pm_targets.discard(str(parsed.get("nick") or "").lower())
            elif parsed["type"] == "nick":
                old = str(parsed.get("nick") or "").lower()
                new = str(parsed.get("new_nick") or "")
                allowed_pm_targets.discard(old)
                if new:
                    allowed_pm_targets.add(new.lower())
                    if old == nick.lower():
                        nick = new
            await websocket.send_text(json.dumps(parsed))

    async def client_loop() -> None:
        nonlocal nick
        while True:
            data = await websocket.receive_json()
            kind = data.get("type")
            if kind == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue
            if kind == "nick":
                new_nick = _sanitize_dashboard_chat_nick(data.get("nick"), cfg.get("default_nick_prefix"))
                send_irc(f"NICK {new_nick}")
                await drain()
                continue
            text = _dashboard_chat_truncate_message(data.get("text"))
            if not text:
                continue
            if kind == "say":
                if not joined:
                    await websocket.send_text(
                        json.dumps({"type": "error", "text": "Wait for the server-confirmed #hermesdashboard join before sending."})
                    )
                    continue
                send_irc(f"PRIVMSG {channel} :{text}")
                await drain()
            elif kind == "selfpm":
                send_irc(f"PRIVMSG {nick} :{text}")
                await drain()
            elif kind == "pm":
                target = _sanitize_dashboard_chat_pm_target(data.get("target"))
                if not target or target.lower() not in allowed_pm_targets:
                    await websocket.send_text(
                        json.dumps({"type": "error", "text": "Blocked: arbitrary PM targets are not allowed."})
                    )
                    continue
                send_irc(f"PRIVMSG {target} :{text}")
                await drain()
            else:
                await websocket.send_text(
                    json.dumps({"type": "error", "text": "Blocked: arbitrary IRC commands are not allowed."})
                )

    tasks = [asyncio.create_task(irc_loop()), asyncio.create_task(client_loop())]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            task.result()
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            send_irc(f"PART {channel} :Hermes Dashboard disconnect")
            await drain()
        except Exception:
            pass
        close = getattr(writer, "close", None)
        if close:
            close()
        wait_closed = getattr(writer, "wait_closed", None)
        if wait_closed:
            maybe = wait_closed()
            if hasattr(maybe, "__await__"):
                await maybe
