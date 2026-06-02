"""Dashboard Chat / IRC bridge helpers.

This module owns pure configuration, sanitizer, parser, and status logic for the
optional dashboard IRC bridge. It intentionally performs no network I/O; route
wrappers inject any websocket/network dependencies at call time.
"""

from __future__ import annotations

import os
import re
import uuid
from typing import Any

DASHBOARD_CHAT_DEFAULT_HOSTS = ["irc.ussyco.de", "irc.ussy.host"]
DASHBOARD_CHAT_DEFAULT_PORT = 6697
DASHBOARD_CHAT_DEFAULT_TLS = True
DASHBOARD_CHAT_CHANNEL = "#hermesdashboard"
DASHBOARD_CHAT_DEFAULT_NICK_PREFIX = "HermesDash"
DASHBOARD_CHAT_DEFAULT_IDENT = "hermesdash"
DASHBOARD_CHAT_DEFAULT_REALNAME = "Hermes Dashboard"
DASHBOARD_CHAT_MAX_MESSAGE_CHARS = 500
DASHBOARD_CHAT_JAIL_DESCRIPTION = (
    "channel-only plus PMs to users present in #hermesdashboard; arbitrary "
    "JOIN/RAW commands are blocked by the dashboard proxy"
)

_IDENTITY_CHARS_RE = re.compile(r"[^A-Za-z0-9_`^{}\[\]|.-]+")
_NICK_FIRST_RE = re.compile(r"[A-Za-z_`^{}\[\]|]")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off", ""}


def _env_hosts(default: list[str]) -> list[str]:
    raw = os.getenv("DASHBOARD_CHAT_IRC_HOSTS")
    if raw is None:
        return list(default)
    return [host.strip() for host in raw.split(",") if host.strip()]


def _sanitize_dashboard_chat_identity_token(
    value: Any, fallback: str, max_len: int = 32
) -> str:
    token = _IDENTITY_CHARS_RE.sub("", str(value or "").strip())[:max_len]
    if not token or not _NICK_FIRST_RE.match(token[0]):
        return fallback[:max_len]
    return token


def _sanitize_dashboard_chat_realname(value: Any, fallback: str = DASHBOARD_CHAT_DEFAULT_REALNAME) -> str:
    text = _CONTROL_RE.sub(" ", str(value or "")).strip()
    text = " ".join(text.split())[:64]
    return text or fallback


def _config_section(config: dict[str, Any] | None) -> dict[str, Any]:
    section = (config or {}).get("dashboard_chat", {})
    return section if isinstance(section, dict) else {}


def _dashboard_chat_runtime_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    section = _config_section(config)
    default_hosts = section.get("hosts", DASHBOARD_CHAT_DEFAULT_HOSTS)
    if isinstance(default_hosts, str):
        default_hosts = [h.strip() for h in default_hosts.split(",") if h.strip()]
    if not isinstance(default_hosts, list):
        default_hosts = DASHBOARD_CHAT_DEFAULT_HOSTS

    try:
        port = int(os.getenv("DASHBOARD_CHAT_IRC_PORT", section.get("port", DASHBOARD_CHAT_DEFAULT_PORT)))
    except (TypeError, ValueError):
        port = DASHBOARD_CHAT_DEFAULT_PORT
    if port < 1 or port > 65535:
        port = DASHBOARD_CHAT_DEFAULT_PORT

    return {
        "enabled": bool(section.get("enabled", False)),
        "hosts": _env_hosts([str(host).strip() for host in default_hosts if str(host).strip()]),
        "port": port,
        "tls": _env_bool("DASHBOARD_CHAT_IRC_TLS", bool(section.get("tls", DASHBOARD_CHAT_DEFAULT_TLS))),
        "channel": DASHBOARD_CHAT_CHANNEL,
        "channel_key": os.getenv("DASHBOARD_CHAT_CHANNEL_KEY", str(section.get("channel_key", ""))),
        "default_nick_prefix": _sanitize_dashboard_chat_identity_token(
            section.get("default_nick_prefix", DASHBOARD_CHAT_DEFAULT_NICK_PREFIX),
            DASHBOARD_CHAT_DEFAULT_NICK_PREFIX,
            24,
        ),
        "ident": _sanitize_dashboard_chat_identity_token(
            section.get("ident", DASHBOARD_CHAT_DEFAULT_IDENT),
            DASHBOARD_CHAT_DEFAULT_IDENT,
            16,
        ),
        "realname": _sanitize_dashboard_chat_realname(
            section.get("realname", DASHBOARD_CHAT_DEFAULT_REALNAME)
        ),
    }


def _sanitize_dashboard_chat_nick(value: Any, prefix: str | None = None) -> str:
    fallback_prefix = _sanitize_dashboard_chat_identity_token(
        prefix or DASHBOARD_CHAT_DEFAULT_NICK_PREFIX,
        DASHBOARD_CHAT_DEFAULT_NICK_PREFIX,
        18,
    )
    nick = _sanitize_dashboard_chat_identity_token(value, "", 24)
    if not nick:
        nick = f"{fallback_prefix}{uuid.uuid4().hex[:6]}"
    return nick[:24]


def _dashboard_chat_user_command(nick: str, config: dict[str, Any] | None = None) -> str:
    cfg = config or _dashboard_chat_runtime_config()
    ident = _sanitize_dashboard_chat_identity_token(cfg.get("ident"), DASHBOARD_CHAT_DEFAULT_IDENT, 16)
    realname = _sanitize_dashboard_chat_realname(cfg.get("realname"), DASHBOARD_CHAT_DEFAULT_REALNAME)
    return f"USER {ident} 0 * :{realname}"


def _dashboard_chat_truncate_message(value: Any) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = " ".join(text.split())
    return text[:DASHBOARD_CHAT_MAX_MESSAGE_CHARS]


def _sanitize_dashboard_chat_pm_target(value: Any) -> str:
    target = _sanitize_dashboard_chat_identity_token(value, "", 24)
    return target


def _parse_irc_prefix(line: str) -> tuple[str, str, str]:
    raw = str(line or "").rstrip("\r\n")
    prefix = ""
    if raw.startswith(":"):
        prefix, _, raw = raw[1:].partition(" ")
    command, _, rest = raw.partition(" ")
    return prefix, command.upper(), rest


def _nick_from_prefix(prefix: str) -> str:
    return str(prefix or "").split("!", 1)[0]


def _parse_irc_message(line: str, current_nick: str | None = None) -> dict[str, Any] | None:
    prefix, command, rest = _parse_irc_prefix(line)
    nick = _nick_from_prefix(prefix)
    current = str(current_nick or "")

    if command in {"PRIVMSG", "NOTICE"}:
        target, _, text = rest.partition(" :")
        message_type = "notice" if command == "NOTICE" else "message"
        private = bool(current and target.lower() == current.lower())
        own_echo = bool(current and nick.lower() == current.lower())
        return {
            "type": message_type,
            "from": nick,
            "target": target,
            "text": text,
            "private": private,
            "own": own_echo,
        }
    if command == "JOIN":
        return {"type": "join", "nick": nick, "channel": rest.lstrip(":")}
    if command == "PART":
        channel, _, reason = rest.partition(" :")
        return {"type": "part", "nick": nick, "channel": channel, "text": reason}
    if command == "QUIT":
        return {"type": "quit", "nick": nick, "text": rest.lstrip(":")}
    if command == "NICK":
        return {"type": "nick", "nick": nick, "new_nick": rest.lstrip(":")}
    if command == "353":
        _, _, names = rest.partition(" :")
        return {"type": "names", "names": [name.lstrip("@+") for name in names.split() if name]}
    if command == "433":
        return {"type": "nick_error", "text": rest}
    if command in {"471", "473", "474", "475"}:
        return {"type": "join_error", "code": command, "text": rest}
    return None


def _dashboard_chat_status_payload(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = _dashboard_chat_runtime_config(config)
    return {
        "enabled": cfg["enabled"],
        "connected": False,
        "bridge_available": bool(cfg["enabled"] and cfg["hosts"]),
        "channel": cfg["channel"],
        "hosts": cfg["hosts"],
        "port": cfg["port"],
        "tls": cfg["tls"],
        "default_nick_prefix": cfg["default_nick_prefix"],
        "ident": cfg["ident"],
        "realname": cfg["realname"],
        "channel_key_configured": bool(cfg["channel_key"]),
        "jail": DASHBOARD_CHAT_JAIL_DESCRIPTION,
    }
