import asyncio
import datetime
import importlib.util
import inspect
import json
import os
import re
import signal
import sys
import sqlite3
import subprocess
import threading
import time
import uuid
from collections import Counter, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import httpx
import aiohttp
import yaml
from starlette.applications import Starlette
from starlette.routing import Route
try:
    from starlette.routing import WebSocketRoute
except Exception:
    # Lightweight tests may stub only Route; use it as a structural fallback
    # so websocket route wiring remains inspectable without a live ASGI stack.
    WebSocketRoute = Route
from starlette.templating import Jinja2Templates
from starlette.responses import JSONResponse, PlainTextResponse
try:
    from starlette.websockets import WebSocket, WebSocketDisconnect
except Exception:
    WebSocket = object
    class WebSocketDisconnect(Exception):
        pass
try:
    from starlette.responses import StreamingResponse
except Exception:  # Lightweight test stubs may omit StreamingResponse.
    StreamingResponse = PlainTextResponse
from sse_starlette.sse import EventSourceResponse

sys.path.insert(0, str(Path(__file__).parent.parent / "hermes-agent"))

try:
    from hermes_constants import display_hermes_home, get_hermes_home
except Exception:

    def get_hermes_home() -> Path:
        return Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser().resolve()

    def display_hermes_home() -> str:
        return str(get_hermes_home())


try:
    from hermes_cli.config import (
        DEFAULT_CONFIG,
        OPTIONAL_ENV_VARS,
        load_config as load_hermes_config,
        load_env as load_hermes_env,
        save_config as save_hermes_config,
        save_env_value,
    )
except Exception:
    DEFAULT_CONFIG = {
        "_config_version": 0,
        "model": "anthropic/claude-opus-4.6",
        "agent": {"max_turns": 90, "tool_use_enforcement": "auto"},
        "memory": {
            "memory_enabled": True,
            "user_profile_enabled": True,
            "memory_char_limit": 22000,
            "user_char_limit": 13750,
            "nudge_interval": 10,
            "flush_min_turns": 6,
        },
        "display": {"personality": "helpful", "skin": "default"},
        "dashboard_chat": {
            "hosts": ["irc.ussyco.de", "irc.ussy.host"],
            "port": 6697,
            "tls": True,
            "channel_key": "hermesdashboard",
            "default_nick_prefix": "HermesDash",
            "ident": "hermesdash",
            "realname": "Hermes Dashboard",
        },
        "browser": {
            "inactivity_timeout": 120,
            "command_timeout": 30,
            "record_sessions": False,
            "allow_private_urls": False,
            "camofox": {"managed_persistence": False},
        },
        "web": {"backend": "firecrawl"},
        "voice": {
            "record_key": "ctrl+b",
            "max_recording_seconds": 120,
            "auto_tts": False,
            "silence_threshold": 200,
            "silence_duration": 3,
        },
        "session_reset": {"mode": "both", "idle_minutes": 1440, "at_hour": 4},
        "skills": {"external_dirs": [], "disabled": [], "creation_nudge_interval": 15},
        "platform_toolsets": {},
    }
    OPTIONAL_ENV_VARS = {
        "OPENROUTER_API_KEY": {
            "description": "OpenRouter API key",
            "prompt": "OpenRouter API key",
            "url": "https://openrouter.ai/keys",
            "password": True,
            "category": "provider",
        },
        "ZAI_API_KEY": {
            "description": "Z.AI / GLM API key",
            "prompt": "Z.AI API key",
            "url": "https://z.ai",
            "password": True,
            "category": "provider",
        },
        "GLM_API_KEY": {
            "description": "Z.AI / GLM API key",
            "prompt": "GLM API key",
            "url": "https://z.ai",
            "password": True,
            "category": "provider",
        },
        "FIRECRAWL_API_KEY": {
            "description": "Firecrawl API key",
            "prompt": "Firecrawl API key",
            "url": "https://www.firecrawl.dev/app/api-keys",
            "password": True,
            "category": "tool",
        },
        "TAVILY_API_KEY": {
            "description": "Tavily API key",
            "prompt": "Tavily API key",
            "url": "https://app.tavily.com/home",
            "password": True,
            "category": "tool",
        },
        "BROWSERBASE_API_KEY": {
            "description": "Browserbase API key",
            "prompt": "Browserbase API key",
            "url": "https://www.browserbase.com/settings",
            "password": True,
            "category": "tool",
        },
    }

    def load_hermes_config():
        config_path = get_hermes_home() / "config.yaml"
        if not config_path.exists():
            return json.loads(json.dumps(DEFAULT_CONFIG))
        try:
            with open(config_path) as f:
                raw = yaml.safe_load(f) or {}
        except Exception:
            raw = {}
        merged = json.loads(json.dumps(DEFAULT_CONFIG))

        def merge(dst, src):
            for key, value in (src or {}).items():
                if isinstance(value, dict) and isinstance(dst.get(key), dict):
                    merge(dst[key], value)
                else:
                    dst[key] = value

        merge(merged, raw)
        return merged

    def load_hermes_env():
        env = {}
        env_path = get_hermes_home() / ".env"
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        env[key] = value
        return env

    def save_hermes_config(config):
        config_path = get_hermes_home() / "config.yaml"
        with open(config_path, "w") as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)

    def save_env_value(key, value):
        env = load_hermes_env()
        env[key] = value
        env_path = get_hermes_home() / ".env"
        with open(env_path, "w") as f:
            for env_key, env_value in env.items():
                f.write(f"{env_key}={env_value}\n")


try:
    from hermes_cli.skin_engine import list_skins
except Exception:

    def list_skins():
        return [{"name": "default", "source": "builtin"}]


try:
    from hermes_cli.tools_config import (
        CONFIGURABLE_TOOLSETS,
        PLATFORMS,
        _get_platform_tools,
    )
except Exception:
    CONFIGURABLE_TOOLSETS = [
        ("browser", "Browser", "Browser automation"),
        ("code_execution", "Code Execution", "Sandboxed code execution"),
        ("delegation", "Delegation", "Subagent delegation"),
        ("file", "File", "File read and write tools"),
        ("memory", "Memory", "Persistent memory tools"),
        ("session_search", "Session Search", "Session recall and search"),
        ("skills", "Skills", "Skill browsing and use"),
        ("terminal", "Terminal", "Shell command execution"),
        ("todo", "Todo", "Structured task tracking"),
        ("web", "Web", "Web search and extraction"),
    ]
    PLATFORMS = {
        "cli": {"label": "CLI", "default_toolset": "hermes-cli"},
        "api_server": {"label": "API Server", "default_toolset": "hermes-api"},
        "telegram": {"label": "Telegram", "default_toolset": "hermes-telegram"},
        "discord": {"label": "Discord", "default_toolset": "hermes-discord"},
        "slack": {"label": "Slack", "default_toolset": "hermes-slack"},
        "whatsapp": {"label": "WhatsApp", "default_toolset": "hermes-whatsapp"},
        "signal": {"label": "Signal", "default_toolset": "hermes-signal"},
        "homeassistant": {
            "label": "Home Assistant",
            "default_toolset": "hermes-homeassistant",
        },
    }

    def _get_platform_tools(config, platform):
        toolsets = config.get("platform_toolsets", {}) or {}
        values = toolsets.get(platform)
        if isinstance(values, list) and values:
            return values
        default_toolset = PLATFORMS.get(platform, {}).get("default_toolset")
        return [default_toolset] if default_toolset else []


HERMES_API = os.getenv("HERMES_API", "http://127.0.0.1:8642")
HERMES_HOME = get_hermes_home()
DASHBOARD_REPO_ROOT = Path(
    os.getenv("DASHBOARD_UPDATE_ROOT", str(Path(__file__).resolve().parent))
).expanduser().resolve()
SELF_IMPROVEMENT_HOME = Path(
    os.getenv("SELF_IMPROVEMENT_HOME", str(Path.home() / "self-improvement"))
).expanduser().resolve()
API_KEY = os.getenv(
    "API_SERVER_KEY", "hermes-dashboard-secret-9e4349ef052042545dd435d3330a2287"
)
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8081"))
HERMES_READ_TIMEOUT_RAW = os.getenv("DASHBOARD_HERMES_READ_TIMEOUT", "0").strip()
HERMES_READ_TIMEOUT = (
    None
    if HERMES_READ_TIMEOUT_RAW.lower() in {"", "0", "none", "null", "off"}
    else float(HERMES_READ_TIMEOUT_RAW)
)
HERMES_USEFUL_EVENT_TIMEOUT = float(
    os.getenv("DASHBOARD_HERMES_USEFUL_EVENT_TIMEOUT", "120")
)

templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates")
)


ACTIVE_RUN_TTL_SECONDS = 1800
ACTIVE_RUNS: dict[str, dict] = {}
_STARTUP_METADATA_BACKFILL_STARTED = False
DASHBOARD_STATE_DB_PATH = HERMES_HOME / "dashboard_state.db"
DASHBOARD_STATE_KEYS = {"conversation", "active_run"}
DASHBOARD_STATE_LOCK = threading.Lock()

DASHBOARD_CHAT_IRC_HOSTS = [
    host.strip()
    for host in os.getenv("DASHBOARD_CHAT_IRC_HOSTS", "irc.ussyco.de,irc.ussy.host").split(",")
    if host.strip()
]
DASHBOARD_CHAT_IRC_PORT = int(os.getenv("DASHBOARD_CHAT_IRC_PORT", "6697"))
DASHBOARD_CHAT_IRC_TLS = os.getenv("DASHBOARD_CHAT_IRC_TLS", "1").lower() not in {"0", "false", "no", "off"}
DASHBOARD_CHAT_CHANNEL = "#hermesdashboard"
DASHBOARD_CHAT_CHANNEL_KEY = os.getenv("DASHBOARD_CHAT_CHANNEL_KEY", "hermesdashboard")
DASHBOARD_CHAT_DEFAULT_NICK_PREFIX = "HermesDash"
DASHBOARD_CHAT_DEFAULT_IDENT = "hermesdash"
DASHBOARD_CHAT_DEFAULT_REALNAME = "Hermes Dashboard"
DASHBOARD_CHAT_MAX_MESSAGE_CHARS = 500

# Track D: Interrupt control for live runs.
# NOTE: The actual agent (run_agent.py) must check check_interrupt_flag()
# before each tool call. This endpoint only sets the flag.
INTERRUPT_FLAGS: dict[str, bool] = {}


def set_interrupt_flag(session_id: str, value: bool) -> None:
    INTERRUPT_FLAGS[session_id] = value


def check_interrupt_flag(session_id: str) -> bool:
    return INTERRUPT_FLAGS.get(session_id, False)

BUILT_IN_PERSONALITIES = [
    "helpful",
    "concise",
    "technical",
    "creative",
    "teacher",
    "kawaii",
    "catgirl",
    "pirate",
    "shakespeare",
    "surfer",
    "noir",
    "uwu",
    "philosopher",
    "hype",
]

EXTRA_SECRET_METADATA = {
    "OPENAI_API_KEY": {
        "description": "OpenAI API key for custom endpoints and OpenAI-backed tools",
        "prompt": "OpenAI API key",
        "url": "https://platform.openai.com/api-keys",
        "password": True,
        "category": "provider",
    },
    "OPENAI_BASE_URL": {
        "description": "OpenAI-compatible base URL override",
        "prompt": "OpenAI base URL",
        "url": None,
        "password": False,
        "category": "provider",
    },
    "ANTHROPIC_API_KEY": {
        "description": "Anthropic Console API key",
        "prompt": "Anthropic API key",
        "url": "https://console.anthropic.com/settings/keys",
        "password": True,
        "category": "provider",
    },
    "ANTHROPIC_TOKEN": {
        "description": "Legacy Anthropic auth token",
        "prompt": "Anthropic token",
        "url": None,
        "password": True,
        "category": "provider",
    },
    "NOUS_API_KEY": {
        "description": "Nous Portal API key",
        "prompt": "Nous API key",
        "url": "https://portal.nousresearch.com/",
        "password": True,
        "category": "provider",
    },
    "GROQ_API_KEY": {
        "description": "Groq Whisper STT API key",
        "prompt": "Groq API key",
        "url": "https://console.groq.com/keys",
        "password": True,
        "category": "tool",
    },
}

WEB_BACKENDS = ["firecrawl", "exa", "parallel", "tavily"]
TTS_PROVIDERS = ["edge", "elevenlabs", "openai", "neutts"]
STT_PROVIDERS = ["local", "groq", "openai"]
BUSY_INPUT_MODES = ["interrupt", "queue"]
TOOL_PROGRESS_MODES = ["off", "new", "all", "verbose"]
BACKGROUND_NOTIFICATION_MODES = ["off", "result", "error", "all"]
RESUME_DISPLAY_MODES = ["full", "minimal"]
APPROVAL_MODES = ["manual", "smart", "off"]
REASONING_EFFORTS = ["", "none", "minimal", "low", "medium", "high", "xhigh"]

# Configurable model cost rates ($ per 1M tokens).
MODEL_COST_TABLE = {
    "default": {"input": 3.00, "output": 15.00},
}


def _cleanup_active_runs() -> None:
    now = time.time()
    expired = []
    for run_id, state in ACTIVE_RUNS.items():
        task = state.get("task")
        updated_at = state.get("updated_at", 0)
        if task and not task.done():
            continue
        if now - updated_at > ACTIVE_RUN_TTL_SECONDS:
            expired.append(run_id)
    for run_id in expired:
        ACTIVE_RUNS.pop(run_id, None)


def _normalize_sse_payload(parsed: dict) -> list[dict]:
    payloads: list[dict] = []
    if parsed.get("tool") and not parsed.get("choices"):
        payloads.append(
            {
                "type": "tool_progress",
                "name": parsed.get("tool"),
                "progress": parsed.get("label") or parsed.get("message") or "running",
                "arguments": parsed,
            }
        )
        return payloads
    hermes = parsed.get("hermes")
    usage = parsed.get("usage")
    if isinstance(hermes, dict):
        payload = dict(hermes)
        call_id = str(
            payload.get("call_id") or payload.get("tool_call_id") or ""
        ).strip()
        if call_id and not payload.get("call_id"):
            payload["call_id"] = call_id
        if payload.get("type") == "meta" and usage:
            payload["usage"] = usage
        payloads.append(payload)
    if "choices" in parsed and parsed["choices"]:
        delta = parsed["choices"][0].get("delta", {})
        content = delta.get("content", "")
        if content:
            payloads.append({"type": "content", "content": content})
    if usage and not (isinstance(hermes, dict) and hermes.get("type") == "meta"):
        payload = {"type": "meta", "usage": usage}
        if isinstance(hermes, dict):
            payload.update(hermes)
        payloads.append(payload)
    return payloads


def _sanitize_chat_messages(messages: list) -> list:
    sanitized = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        # Preserve multimodal content arrays with valid text/image_url parts
        if isinstance(content, list):
            valid_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") in {"text", "image_url"}:
                    valid_parts.append(part)
            if valid_parts:
                sanitized.append({"role": role, "content": valid_parts})
            continue
        # Fall back to string for everything else
        content = str(content or "")
        if role not in {"system", "user", "assistant", "tool"}:
            continue
        if role == "assistant" and content.startswith("Error: Hermes gateway"):
            continue
        if not content and role != "assistant":
            continue
        sanitized.append({"role": role, "content": content})
    return sanitized


def _log_stream(run_id: str, message: str) -> None:
    print(f"[dashboard:/chat:{run_id}] {message}", file=sys.stderr, flush=True)


def _dashboard_state_connect() -> sqlite3.Connection:
    DASHBOARD_STATE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DASHBOARD_STATE_DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_state (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    return conn


def _validate_dashboard_state_key(key: str) -> str:
    normalized = str(key or "").strip()
    if normalized not in DASHBOARD_STATE_KEYS:
        raise ValueError(f"Unsupported dashboard state key: {normalized}")
    return normalized


def _load_dashboard_state(key: str):
    key = _validate_dashboard_state_key(key)
    with DASHBOARD_STATE_LOCK:
        conn = _dashboard_state_connect()
        try:
            row = conn.execute(
                "SELECT value_json FROM dashboard_state WHERE key = ?", (key,)
            ).fetchone()
        finally:
            conn.close()
    if not row:
        return False, None
    try:
        return True, json.loads(row[0])
    except json.JSONDecodeError:
        return False, None


def _save_dashboard_state(key: str, value) -> None:
    key = _validate_dashboard_state_key(key)
    value_json = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with DASHBOARD_STATE_LOCK:
        conn = _dashboard_state_connect()
        try:
            conn.execute(
                """
                INSERT INTO dashboard_state(key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, value_json, updated_at),
            )
            conn.commit()
        finally:
            conn.close()


def _delete_dashboard_state(key: str) -> None:
    key = _validate_dashboard_state_key(key)
    with DASHBOARD_STATE_LOCK:
        conn = _dashboard_state_connect()
        try:
            conn.execute("DELETE FROM dashboard_state WHERE key = ?", (key,))
            conn.commit()
        finally:
            conn.close()


async def get_dashboard_state(request):
    key = request.path_params["key"]
    try:
        found, value = _load_dashboard_state(key)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"found": found, "value": value})


async def set_dashboard_state(request):
    key = request.path_params["key"]
    try:
        data = json.loads(await request.body())
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    if not isinstance(data, dict) or "value" not in data:
        return JSONResponse({"error": "Expected JSON object with a value field"}, status_code=400)
    try:
        _save_dashboard_state(key, data.get("value"))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"success": True})


async def delete_dashboard_state(request):
    key = request.path_params["key"]
    try:
        _delete_dashboard_state(key)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"success": True})


def _run_chat_stream_sync(run_id: str, messages: list, session_id: Optional[str]) -> None:
    state = ACTIVE_RUNS[run_id]
    event_count = 0
    content_events = 0
    tool_events = 0
    raw_line_count = 0
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    if session_id:
        headers["X-Hermes-Session-Id"] = session_id
    _log_stream(run_id, f"sync start messages={len(messages)} session_id={session_id or '-'}")
    try:
        with httpx.Client(
            timeout=httpx.Timeout(
                connect=30.0,
                read=HERMES_READ_TIMEOUT,
                write=300.0,
                pool=30.0,
            )
        ) as client:
            with client.stream(
                "POST",
                f"{HERMES_API}/v1/chat/completions",
                headers=headers,
                json={
                    "model": "hermes-agent",
                    "messages": messages,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                _log_stream(run_id, f"sync upstream status={response.status_code}")
                if not state.get("session_id"):
                    sid = response.headers.get("X-Hermes-Session-Id", "").strip()
                    if sid:
                        state["session_id"] = sid
                        state["events"].append(
                            {
                                "data": json.dumps(
                                    {
                                        "type": "run_state",
                                        "run_id": run_id,
                                        "session_id": sid,
                                    }
                                )
                            }
                        )
                first_useful_event_at = time.time()
                saw_useful_event = False
                for line in response.iter_lines():
                    if (
                        not saw_useful_event
                        and time.time() - first_useful_event_at > HERMES_USEFUL_EVENT_TIMEOUT
                    ):
                        raise TimeoutError(
                            "Hermes gateway stream produced no usable event "
                            f"within {int(HERMES_USEFUL_EVENT_TIMEOUT)}s"
                        )
                    raw_line_count += 1
                    if raw_line_count <= 20:
                        _log_stream(run_id, f"sync raw[{raw_line_count}] {line[:240]!r}")
                    if not line.startswith("data: "):
                        continue
                    chunk = line[6:]
                    state["updated_at"] = time.time()
                    if chunk == "[DONE]":
                        state["done"] = True
                        state["events"].append({"data": "[DONE]"})
                        break
                    try:
                        parsed = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    payloads = _normalize_sse_payload(parsed)
                    if not payloads:
                        continue
                    saw_useful_event = True
                    for payload in payloads:
                        event_count += 1
                        if payload.get("type") == "content":
                            content_events += 1
                        elif payload.get("type") in {"tool_call", "tool_output", "tool_progress"}:
                            tool_events += 1
                        state["events"].append({"data": json.dumps(payload)})
                if not state.get("done"):
                    state["done"] = True
                    state["events"].append({"data": "[DONE]"})
                    _log_stream(run_id, "sync upstream closed without explicit DONE")
    except Exception as exc:
        _log_stream(run_id, f"sync error {type(exc).__name__}: {exc}")
        state["events"].append(
            {
                "data": json.dumps(
                    {
                        "type": "content",
                        "content": f"Error: Hermes gateway is unavailable ({exc}).",
                    }
                )
            }
        )
        state["events"].append({"data": "[DONE]"})
        state["error"] = str(exc)
        state["done"] = True
    finally:
        state["updated_at"] = time.time()
        _log_stream(
            run_id,
            "sync finish "
            f"done={state.get('done')} events={event_count} "
            f"content={content_events} tool={tool_events} raw={raw_line_count} "
            f"error={state.get('error') or '-'}",
        )


async def _run_chat_stream(
    run_id: str, messages: list, session_id: Optional[str]
) -> None:
    await asyncio.to_thread(_run_chat_stream_sync, run_id, messages, session_id)
    return
    state = ACTIVE_RUNS[run_id]
    event_count = 0
    content_events = 0
    tool_events = 0
    raw_line_count = 0
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    if session_id:
        headers["X-Hermes-Session-Id"] = session_id
    _log_stream(run_id, f"start messages={len(messages)} session_id={session_id or '-'}")
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=30.0,
                read=HERMES_READ_TIMEOUT,
                write=300.0,
                pool=30.0,
            )
        ) as client:
            async with client.stream(
                "POST",
                f"{HERMES_API}/v1/chat/completions",
                headers=headers,
                json={
                    "model": "hermes-agent",
                    "messages": messages,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                _log_stream(run_id, f"upstream status={response.status_code}")
                if not state.get("session_id"):
                    sid = response.headers.get("X-Hermes-Session-Id", "").strip()
                    if sid:
                        state["session_id"] = sid
                        state["events"].append(
                            {
                                "data": json.dumps(
                                    {
                                        "type": "run_state",
                                        "run_id": run_id,
                                        "session_id": sid,
                                    }
                                )
                            }
                        )
                first_useful_event_at = time.time()
                saw_useful_event = False
                line_iter = response.aiter_lines().__aiter__()
                while True:
                    if (
                        not saw_useful_event
                        and time.time() - first_useful_event_at > HERMES_USEFUL_EVENT_TIMEOUT
                    ):
                        raise TimeoutError(
                            "Hermes gateway stream produced no usable event "
                            f"within {int(HERMES_USEFUL_EVENT_TIMEOUT)}s"
                        )
                    try:
                        line = await asyncio.wait_for(
                            line_iter.__anext__(),
                            timeout=min(5.0, HERMES_USEFUL_EVENT_TIMEOUT),
                        )
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        continue
                    raw_line_count += 1
                    if raw_line_count <= 20:
                        _log_stream(run_id, f"raw[{raw_line_count}] {line[:240]!r}")
                    if not line.startswith("data: "):
                        continue
                    chunk = line[6:]
                    state["updated_at"] = time.time()
                    if chunk == "[DONE]":
                        state["done"] = True
                        state["events"].append({"data": "[DONE]"})
                        break
                    try:
                        parsed = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    payloads = _normalize_sse_payload(parsed)
                    if not payloads:
                        continue
                    saw_useful_event = True
                    for payload in payloads:
                        event_count += 1
                        if payload.get("type") == "content":
                            content_events += 1
                        elif payload.get("type") in {"tool_call", "tool_output", "tool_progress"}:
                            tool_events += 1
                        event = {"data": json.dumps(payload)}
                        state["events"].append(event)
                if not state.get("done"):
                    state["done"] = True
                    state["events"].append({"data": "[DONE]"})
                    _log_stream(run_id, "upstream closed without explicit DONE")
    except Exception as exc:
        _log_stream(run_id, f"error {type(exc).__name__}: {exc}")
        state["events"].append(
            {
                "data": json.dumps(
                    {
                        "type": "content",
                        "content": f"Error: Hermes gateway is unavailable ({exc}).",
                    }
                )
            }
        )
        state["events"].append({"data": "[DONE]"})
        state["error"] = str(exc)
        state["done"] = True
    finally:
        state["updated_at"] = time.time()
        _log_stream(
            run_id,
            "finish "
            f"done={state.get('done')} events={event_count} "
            f"content={content_events} tool={tool_events} raw={raw_line_count} "
            f"error={state.get('error') or '-'}",
        )


def _child_session_ids(conn: sqlite3.Connection, session_id: str) -> list[str]:
    cursor = conn.execute(
        "SELECT id FROM sessions WHERE parent_session_id = ? ORDER BY started_at, id",
        (session_id,),
    )
    return [row[0] for row in cursor.fetchall()]


def _related_session_artifacts(session_ids: list[str]) -> list[dict]:
    sessions_dir = HERMES_HOME / "sessions"
    if not sessions_dir.is_dir():
        return []

    artifacts: list[dict] = []
    seen_paths: set[str] = set()
    for session_id in session_ids:
        for path in sorted(sessions_dir.glob(f"request_dump_{session_id}_*.json")):
            resolved = str(path.resolve())
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)

            item = {
                "kind": "request_dump",
                "session_id": session_id,
                "slug": path.stem,
                "file_name": path.name,
                "path": resolved,
            }
            try:
                payload = json.loads(path.read_text())
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                item["timestamp"] = payload.get("timestamp")
                item["reason"] = payload.get("reason")
                error = payload.get("error")
                if isinstance(error, dict):
                    item["error_type"] = error.get("type")
                    item["error_message"] = error.get("message")
                    item["error_response_status"] = error.get("response_status")
                request = payload.get("request")
                if isinstance(request, dict):
                    item["url"] = request.get("url")
                    body = request.get("body")
                    if isinstance(body, dict):
                        item["model"] = body.get("model")
            artifacts.append(item)

    return sorted(
        artifacts,
        key=lambda artifact: (
            str(artifact.get("timestamp") or ""),
            str(artifact.get("file_name") or ""),
        ),
    )


def _session_activity_payload(conn: sqlite3.Connection, session_id: str) -> dict:
    session_ids = [session_id] + _child_session_ids(conn, session_id)
    placeholders = ",".join("?" for _ in session_ids)
    rows = conn.execute(
        f"""
        SELECT session_id, role, content, timestamp, tool_call_id, tool_calls, tool_name
        FROM messages
        WHERE session_id IN ({placeholders})
        ORDER BY timestamp, id
        """,
        session_ids,
    ).fetchall()

    skill_events = []
    session_search_events = []
    background_reviews = []
    assistant_tool_calls: dict[str, dict] = {}

    for row in rows:
        item = dict(row)
        session_label = item.get("session_id")
        if item.get("role") == "assistant" and item.get("tool_calls"):
            try:
                calls = json.loads(item["tool_calls"])
            except Exception:
                calls = []
            for tc in calls if isinstance(calls, list) else []:
                call_id = tc.get("id") or tc.get("call_id") or ""
                func = tc.get("function", {}) if isinstance(tc, dict) else {}
                assistant_tool_calls[call_id] = {
                    "call_id": call_id,
                    "name": func.get("name", ""),
                    "arguments": func.get("arguments", ""),
                    "session_id": session_label,
                    "timestamp": item.get("timestamp"),
                }
        elif item.get("role") == "tool":
            call = assistant_tool_calls.get(item.get("tool_call_id", ""), {})
            call_id = call.get("call_id") or item.get("tool_call_id") or ""
            tool_name = call.get("name") or item.get("tool_name") or "tool"
            output = _safe_json_loads(item.get("content"))
            target = None
            if session_label != session_id:
                target = {"kind": "child", "id": session_label}
            elif call_id:
                target = {"kind": "tool", "id": call_id}
            if tool_name == "skill_manage":
                event = {
                    "session_id": session_label,
                    "timestamp": item.get("timestamp"),
                    "request": _safe_json_loads(call.get("arguments", ""))
                    or call.get("arguments")
                    or "",
                    "result": output or item.get("content") or "",
                    "tool_call_id": call_id,
                    "tool_name": tool_name,
                }
                if target:
                    event["target"] = target
                skill_events.append(event)
            elif tool_name == "session_search":
                event = {
                    "session_id": session_label,
                    "timestamp": item.get("timestamp"),
                    "request": _safe_json_loads(call.get("arguments", ""))
                    or call.get("arguments")
                    or "",
                    "result": output or item.get("content") or "",
                    "tool_call_id": call_id,
                    "tool_name": tool_name,
                }
                if target:
                    event["target"] = target
                session_search_events.append(event)

    for child_id in session_ids[1:]:
        child_messages = conn.execute(
            """
            SELECT role, content, timestamp, tool_calls, tool_call_id, tool_name
            FROM messages WHERE session_id = ? ORDER BY timestamp, id
            """,
            (child_id,),
        ).fetchall()
        if not child_messages:
            continue
        tool_events = []
        summary = []
        assistant_calls: dict[str, dict] = {}
        for row in child_messages:
            item = dict(row)
            if item.get("role") == "assistant" and item.get("tool_calls"):
                try:
                    calls = json.loads(item["tool_calls"])
                except Exception:
                    calls = []
                for tc in calls if isinstance(calls, list) else []:
                    call_id = tc.get("id") or tc.get("call_id") or ""
                    func = tc.get("function", {}) if isinstance(tc, dict) else {}
                    assistant_calls[call_id] = {
                        "call_id": call_id,
                        "name": func.get("name", ""),
                        "arguments": _safe_json_loads(func.get("arguments", ""))
                        or func.get("arguments")
                        or "",
                    }
            elif item.get("role") == "tool":
                call = assistant_calls.get(item.get("tool_call_id", ""), {})
                payload = (
                    _safe_json_loads(item.get("content", ""))
                    or item.get("content")
                    or ""
                )
                tool_events.append(
                    {
                        "call_id": call.get("call_id")
                        or item.get("tool_call_id")
                        or "",
                        "name": call.get("name") or item.get("tool_name") or "tool",
                        "arguments": call.get("arguments") or "",
                        "output": payload,
                        "timestamp": item.get("timestamp"),
                    }
                )
                if isinstance(payload, dict) and payload.get("message"):
                    summary.append(payload["message"])
                elif isinstance(payload, str) and payload.strip():
                    summary.append(payload.strip())
        background_reviews.append(
            {
                "session_id": child_id,
                "timestamp": child_messages[0]["timestamp"] if child_messages else None,
                "summary": " | ".join(summary[:5]),
                "events": tool_events,
                "target": {"kind": "child", "id": child_id},
            }
        )

    return {
        "background_reviews": background_reviews,
        "skill_events": skill_events,
        "session_search_events": session_search_events,
    }


def _session_overview_payload(conn: sqlite3.Connection, session_id: str) -> dict:
    child_rows = conn.execute(
        """
        SELECT id, title, summary, started_at
        FROM sessions
        WHERE parent_session_id = ?
        ORDER BY started_at, id
        """,
        (session_id,),
    ).fetchall()
    return {
        "children": [dict(row) for row in child_rows],
        "child_count": len(child_rows),
    }


def _sessions_table_exists(conn: sqlite3.Connection) -> bool:
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
    )
    return cursor.fetchone() is not None


def _sessions_table_has_column(conn: sqlite3.Connection, column_name: str) -> bool:
    try:
        rows = conn.execute("PRAGMA table_info(sessions)").fetchall()
    except Exception:
        return False
    for row in rows:
        name = row[1] if not isinstance(row, sqlite3.Row) else row["name"]
        if name == column_name:
            return True
    return False


def _ensure_sessions_summary_column(conn: sqlite3.Connection) -> None:
    if not _sessions_table_exists(conn):
        return
    if _sessions_table_has_column(conn, "summary"):
        return
    conn.execute("ALTER TABLE sessions ADD COLUMN summary TEXT")
    conn.commit()


def _sqlite_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _sqlite_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    except Exception:
        return set()
    columns: set[str] = set()
    for row in rows:
        columns.add(row[1] if not isinstance(row, sqlite3.Row) else row["name"])
    return columns


def _parse_dashboard_timestamp(value: object) -> Optional[datetime.datetime]:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(float(value), tz=datetime.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        numeric_value = float(text)
    except ValueError:
        numeric_value = None
    if numeric_value is not None:
        try:
            return datetime.datetime.fromtimestamp(numeric_value, tz=datetime.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _tool_output_failed(content: object) -> bool:
    payload = _safe_json_loads(content) if isinstance(content, str) else content
    if isinstance(payload, dict):
        if payload.get("success") is False or payload.get("ok") is False:
            return True
        if payload.get("error") or payload.get("errors"):
            return True
        exit_code = payload.get("exit_code")
        if isinstance(exit_code, int) and exit_code != 0:
            return True
        status = str(payload.get("status") or "").lower()
        if status in {"error", "failed", "failure"}:
            return True
    lowered = str(content or "").lower()
    return any(marker in lowered for marker in ("traceback", "exception", "error:", "failed"))


def _empty_agent_observability_report(window_hours: int, reason: str) -> dict:
    return {
        "window_hours": window_hours,
        "summary": {
            "sessions": 0,
            "completed_sessions": 0,
            "running_sessions": 0,
            "error_sessions": 0,
            "messages": 0,
            "tool_calls": 0,
            "tool_outputs": 0,
            "tool_failures": 0,
            "tool_failure_rate": 0.0,
            "missing_summaries": 0,
            "stale_running_sessions": 0,
        },
        "top_tools": [],
        "source_mix": [],
        "model_mix": [],
        "recent_traces": [],
        "alerts": [{"severity": "info", "title": "No telemetry yet", "detail": reason}],
        "recommendations": [
            "Run a few agent sessions, then refresh this panel to see aggregate behavior plus trace exemplars.",
        ],
        "research_basis": [
            "Agent observability guidance emphasizes aggregate dashboards plus detailed traces.",
            "Recommended metrics include error rate, tool failure rate, latency, token/cost, model mix, and tool sequences.",
        ],
    }


def get_agent_observability_report(window_hours: int = 24, trace_limit: int = 8) -> dict:
    """Aggregate recent Hermes session telemetry into an agent-ops dashboard payload."""
    window_hours = max(1, min(int(window_hours or 24), 24 * 30))
    trace_limit = max(1, min(int(trace_limit or 8), 25))
    db_path = HERMES_HOME / "state.db"
    if not db_path.exists():
        return _empty_agent_observability_report(window_hours, "state.db does not exist yet.")

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=window_hours)
    cutoff_text = cutoff.isoformat().replace("+00:00", "Z")
    cutoff_epoch = cutoff.timestamp()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _sqlite_table_exists(conn, "sessions"):
            return _empty_agent_observability_report(window_hours, "sessions table is missing.")
        session_columns = _sqlite_table_columns(conn, "sessions")
        _ensure_sessions_summary_column(conn)
        session_columns.add("summary")
        select_columns = ["id", "title", "started_at", "ended_at", "source"]
        optional_columns = ["model", "summary", "end_reason", "parent_session_id"]
        select_columns.extend(col for col in optional_columns if col in session_columns)
        sessions = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT {', '.join(select_columns)}
                FROM sessions
                WHERE started_at IS NULL
                   OR (typeof(started_at) IN ('integer', 'real') AND started_at >= ?)
                   OR (typeof(started_at) = 'text' AND started_at >= ?)
                ORDER BY started_at DESC
                LIMIT 250
                """,
                (cutoff_epoch, cutoff_text),
            ).fetchall()
        ]
        if not sessions:
            return _empty_agent_observability_report(window_hours, "No sessions fell inside the selected window.")

        session_ids = [str(row.get("id") or "") for row in sessions if row.get("id")]
        placeholders = ",".join("?" for _ in session_ids)
        messages: list[dict] = []
        if session_ids and _sqlite_table_exists(conn, "messages"):
            message_columns = _sqlite_table_columns(conn, "messages")
            msg_select = ["session_id", "role", "content"]
            for col in ("timestamp", "tool_calls", "tool_call_id", "tool_name"):
                if col in message_columns:
                    msg_select.append(col)
            messages = [
                dict(row)
                for row in conn.execute(
                    f"""
                    SELECT {', '.join(msg_select)}
                    FROM messages
                    WHERE session_id IN ({placeholders})
                    ORDER BY timestamp, id
                    """,
                    session_ids,
                ).fetchall()
            ]

        messages_by_session = Counter(str(msg.get("session_id") or "") for msg in messages)
        tool_calls_by_session: Counter[str] = Counter()
        tool_counter: Counter[str] = Counter()
        tool_outputs = 0
        tool_failures = 0
        for msg in messages:
            sid = str(msg.get("session_id") or "")
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                calls = _safe_json_loads(msg.get("tool_calls"))
                if isinstance(calls, list):
                    for call in calls:
                        if not isinstance(call, dict):
                            continue
                        func = call.get("function") if isinstance(call.get("function"), dict) else {}
                        name = str(func.get("name") or call.get("name") or "tool").strip() or "tool"
                        tool_counter[name] += 1
                        tool_calls_by_session[sid] += 1
            if msg.get("role") == "tool":
                tool_outputs += 1
                name = str(msg.get("tool_name") or "tool").strip() or "tool"
                tool_counter[name] += 1
                tool_calls_by_session[sid] += 1
                if _tool_output_failed(msg.get("content")):
                    tool_failures += 1

        now = datetime.datetime.now(datetime.timezone.utc)
        running = 0
        errors = 0
        missing_summaries = 0
        stale_running = 0
        source_counter: Counter[str] = Counter()
        model_counter: Counter[str] = Counter()
        traces = []
        for session in sessions:
            sid = str(session.get("id") or "")
            ended = bool(session.get("ended_at"))
            if not ended:
                running += 1
            end_reason = str(session.get("end_reason") or "").lower()
            if end_reason == "error":
                errors += 1
            if not str(session.get("summary") or "").strip():
                missing_summaries += 1
            started = _parse_dashboard_timestamp(session.get("started_at"))
            if not ended and started and (now - started).total_seconds() > 6 * 3600:
                stale_running += 1
            source_counter[str(session.get("source") or "unknown")] += 1
            model_counter[str(session.get("model") or "unknown")] += 1
            traces.append({
                "id": sid,
                "title": _session_label(session.get("title"), session.get("summary"), sid),
                "started_at": session.get("started_at"),
                "source": session.get("source") or "unknown",
                "model": session.get("model") or "unknown",
                "status": "error" if end_reason == "error" else "running" if not ended else "complete",
                "messages": messages_by_session.get(sid, 0),
                "tool_events": tool_calls_by_session.get(sid, 0),
            })

        tool_calls = sum(tool_counter.values())
        failure_rate = (tool_failures / tool_outputs) if tool_outputs else 0.0
        alerts = []
        if errors:
            alerts.append({"severity": "danger", "title": "Error-ending sessions", "detail": f"{errors} session(s) ended with error in the last {window_hours}h."})
        if failure_rate >= 0.1:
            alerts.append({"severity": "warning", "title": "Tool failure rate elevated", "detail": f"{failure_rate:.0%} of tool outputs look failed."})
        if stale_running:
            alerts.append({"severity": "warning", "title": "Stale running sessions", "detail": f"{stale_running} session(s) have been running longer than 6 hours."})
        if missing_summaries:
            alerts.append({"severity": "info", "title": "Summary coverage gap", "detail": f"{missing_summaries} session(s) lack summaries; backfill improves trace triage."})
        if not alerts:
            alerts.append({"severity": "ok", "title": "Telemetry looks healthy", "detail": "No elevated tool-failure, stale-run, or error-session signals in this window."})

        return {
            "window_hours": window_hours,
            "summary": {
                "sessions": len(sessions),
                "completed_sessions": len(sessions) - running,
                "running_sessions": running,
                "error_sessions": errors,
                "messages": len(messages),
                "tool_calls": tool_calls,
                "tool_outputs": tool_outputs,
                "tool_failures": tool_failures,
                "tool_failure_rate": round(failure_rate, 4),
                "missing_summaries": missing_summaries,
                "stale_running_sessions": stale_running,
            },
            "top_tools": [{"name": name, "count": count} for name, count in tool_counter.most_common(10)],
            "source_mix": [{"name": name, "count": count} for name, count in source_counter.most_common()],
            "model_mix": [{"name": name, "count": count} for name, count in model_counter.most_common(8)],
            "recent_traces": traces[:trace_limit],
            "alerts": alerts,
            "recommendations": [
                "Use the top-tool list to spot brittle dependencies before they dominate failures.",
                "Open recent traces with high tool-event counts when debugging loops or wrong tool selection.",
                "Track summary coverage because searchable traces are faster to triage than raw transcripts.",
            ],
            "research_basis": [
                "Sentry's 2026 agent observability guide argues effective monitoring needs both aggregate dashboards and detailed traces.",
                "Langfuse describes agent observability as real-time monitoring of LLM calls, control flow, latency, cost, and error rates for multi-step agents.",
            ],
        }
    finally:
        conn.close()


def _clean_transcript_seed_text(text: str) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if cleaned.startswith("[SYSTEM:"):
        # Extract skill name from system prompts like "[SYSTEM: The user has invoked the \"tournament-build\" skill...]"
        import re
        skill_match = re.search(r'"([^"]+)"\s+skill', lowered)
        if skill_match:
            return f"Skill: {skill_match.group(1)}"
        return ""
    if cleaned.startswith("--- name:"):
        return ""
    if "skill content is loaded below" in lowered:
        return ""
    if lowered.startswith("the user has invoked the"):
        # Extract skill name from plain text
        import re
        skill_match = re.search(r'"([^"]+)"', lowered)
        if skill_match:
            return f"Skill: {skill_match.group(1)}"
        return ""
    return cleaned


def _extract_tool_output_preview(raw_content: str) -> str:
    payload = _safe_json_loads(raw_content)
    if isinstance(payload, dict):
        for key in ("summary", "message", "output", "content", "result"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return " ".join(value.split()).strip()
    if isinstance(payload, str) and payload.strip():
        return " ".join(payload.split()).strip()
    return " ".join(str(raw_content or "").split()).strip()


def _extract_summary_from_messages(
    messages: list[dict], session_meta: Optional[dict] = None
) -> Optional[str]:
    session_meta = session_meta or {}
    title = str(session_meta.get("title") or "").strip()
    user_messages = []
    assistant_messages = []
    tool_names = []
    tool_output_previews = []
    for msg in messages:
        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "").strip()
        cleaned_content = _clean_transcript_seed_text(content)
        if role == "user" and cleaned_content:
            user_messages.append(cleaned_content)
        elif role == "assistant" and cleaned_content:
            assistant_messages.append(cleaned_content)
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            for tool_call in tool_calls:
                func = (
                    tool_call.get("function", {}) if isinstance(tool_call, dict) else {}
                )
                name = str(func.get("name") or tool_call.get("name") or "").strip()
                if name:
                    tool_names.append(name)
        tool_name = str(msg.get("tool_name") or "").strip()
        if role == "tool" and tool_name:
            tool_names.append(tool_name)
        if role == "tool" and content:
            preview = _extract_tool_output_preview(content)
            if preview:
                tool_output_previews.append(preview)

    if (
        not user_messages
        and not assistant_messages
        and not title
        and not tool_names
        and not tool_output_previews
    ):
        return None

    seed = (
        user_messages[0]
        if user_messages
        else assistant_messages[0]
        if assistant_messages
        else tool_output_previews[0]
        if tool_output_previews
        else title
    )
    summary = seed.replace("\n", " ").strip() if seed else ""
    if len(summary) > 220:
        summary = summary[:219].rstrip() + "..."
    unique_tools = []
    for name in tool_names:
        if name not in unique_tools:
            unique_tools.append(name)
    if unique_tools:
        tool_text = ", ".join(unique_tools[:4])
        summary = (
            f"{summary} Tools: {tool_text}." if summary else f"Tools: {tool_text}."
        )
    return summary.strip() or None


def _extract_title_from_messages(
    messages: list[dict], session_meta: Optional[dict] = None
) -> Optional[str]:
    session_meta = session_meta or {}
    tool_names = []
    tool_output_previews = []

    def _condense_title(text: str) -> Optional[str]:
        cleaned = _clean_transcript_seed_text(text).strip(" .:-=")
        if not cleaned:
            return None
        cleaned = cleaned.replace("Tools:", "").strip(" .:-")
        if ". " in cleaned:
            cleaned = cleaned.split(". ", 1)[0].strip()
        if " Tools: " in cleaned:
            cleaned = cleaned.split(" Tools: ", 1)[0].strip()
        if cleaned.startswith("==="):
            cleaned = cleaned.strip("=").strip()
        if cleaned.lower().startswith("now i have a complete picture"):
            return None
        if cleaned.lower().startswith("let me compile"):
            return None
        words = cleaned.split()
        if len(words) > 8:
            cleaned = " ".join(words[:8]).rstrip(" ,;:-") + "..."
        return cleaned[:77].rstrip() + "..." if len(cleaned) > 80 else cleaned

    for msg in messages:
        content = str(msg.get("content") or "").strip()
        role = str(msg.get("role") or "")
        cleaned_content = _clean_transcript_seed_text(content)

        if role == "user" and cleaned_content:
            title = _condense_title(cleaned_content.replace("\n", " "))
            if title:
                return title
        if role == "assistant" and cleaned_content:
            title = _condense_title(cleaned_content.replace("\n", " "))
            if title:
                return title
        # If assistant has tool_calls but empty content, extract tool names
        if role == "assistant" and not cleaned_content:
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                tc_names = []
                for tool_call in tool_calls:
                    func = (
                        tool_call.get("function", {}) if isinstance(tool_call, dict) else {}
                    )
                    name = str(func.get("name") or tool_call.get("name") or "").strip()
                    if name:
                        tc_names.append(name)
                if tc_names:
                    tool_text = ", ".join(tc_names[:3])
                    title = _condense_title(f"Running {tool_text}")
                    if title:
                        return title

        tool_name = str(msg.get("tool_name") or "").strip()
        if tool_name:
            tool_names.append(tool_name)
        if role == "tool" and content:
            preview = _extract_tool_output_preview(content)
            if preview:
                tool_output_previews.append(preview)
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            for tool_call in tool_calls:
                func = (
                    tool_call.get("function", {}) if isinstance(tool_call, dict) else {}
                )
                name = str(func.get("name") or tool_call.get("name") or "").strip()
                if name:
                    tool_names.append(name)
    if tool_output_previews:
        title = _condense_title(tool_output_previews[0])
        if title:
            return title
    if tool_names:
        title = f"Session using {tool_names[0]}"
        return title[:77].rstrip() + "..." if len(title) > 80 else title
    fallback = str(session_meta.get("title") or "").strip()
    if fallback:
        return fallback
    summary = str(session_meta.get("summary") or "").strip()
    if summary:
        title = _condense_title(summary)
        if title:
            return title
    session_id = str(session_meta.get("id") or "").strip()
    if session_id:
        return f"Session {session_id[:8]}"
    return None


def _refresh_local_session_metadata(
    conn: sqlite3.Connection, session_id: str, force: bool = False
) -> dict[str, Optional[str]]:
    conn.row_factory = sqlite3.Row
    _ensure_sessions_summary_column(conn)
    session_meta = conn.execute(
        "SELECT id, title, source, model, summary FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if not session_meta:
        return {"title": None, "summary": None}
    message_rows = conn.execute(
        "SELECT role, content, tool_calls, tool_name FROM messages WHERE session_id = ? ORDER BY timestamp, id",
        (session_id,),
    ).fetchall()
    messages = []
    for row in message_rows:
        item = dict(row)
        if item.get("tool_calls"):
            try:
                item["tool_calls"] = json.loads(item["tool_calls"])
            except Exception:
                pass
        messages.append(item)
    meta = dict(session_meta)
    existing_title = str(meta.get("title") or "").strip() or None
    existing_summary = str(meta.get("summary") or "").strip() or None
    generated_title = None
    generated_summary = None
    if force or not existing_title:
        generated_title = _extract_title_from_messages(messages, meta)
    if generated_title:
        meta["title"] = generated_title
    if force or not existing_summary:
        generated_summary = _extract_summary_from_messages(messages, meta)
    title_to_store = generated_title or existing_title
    summary_to_store = generated_summary or existing_summary
    if not title_to_store and summary_to_store:
        title_to_store = (
            summary_to_store[:77].rstrip() + "..."
            if len(summary_to_store) > 80
            else summary_to_store
        )
    changed = (generated_title is not None and generated_title != existing_title) or (
        generated_summary is not None and generated_summary != existing_summary
    )
    if changed:
        try:
            conn.execute(
                "UPDATE sessions SET title = COALESCE(?, title), summary = COALESCE(?, summary) WHERE id = ?"
                if not force
                else "UPDATE sessions SET title = ?, summary = ? WHERE id = ?",
                (generated_title, generated_summary, session_id)
                if not force
                else (title_to_store, summary_to_store, session_id),
            )
            conn.commit()
        except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
            # Some installs enforce unique session titles. Retry with a unique suffix.
            conn.rollback()
            if "unique" in str(e).lower() and generated_title:
                # Retry with session ID suffix to make title unique
                suffix = f" ({session_id[-6:]})"
                truncated = generated_title[:77-len(suffix)].rstrip()
                unique_title = truncated + suffix
                try:
                    conn.execute(
                        "UPDATE sessions SET title = ?, summary = COALESCE(?, summary) WHERE id = ?",
                        (unique_title, generated_summary, session_id),
                    )
                    conn.commit()
                    title_to_store = unique_title
                except sqlite3.Error:
                    conn.rollback()
                    if generated_summary is not None and generated_summary != existing_summary:
                        try:
                            conn.execute(
                                "UPDATE sessions SET summary = ? WHERE id = ?",
                                (generated_summary, session_id),
                            )
                            conn.commit()
                        except sqlite3.Error:
                            conn.rollback()
                    title_to_store = existing_title
            else:
                if generated_summary is not None and generated_summary != existing_summary:
                    try:
                        conn.execute(
                            "UPDATE sessions SET summary = ? WHERE id = ?",
                            (generated_summary, session_id),
                        )
                        conn.commit()
                    except sqlite3.Error:
                        conn.rollback()
                title_to_store = existing_title
    return {"title": title_to_store, "summary": summary_to_store, "changed": changed}


def get_raw_config():
    config_path = HERMES_HOME / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def get_config():
    return load_hermes_config()


def save_config(config):
    save_hermes_config(config)


def get_env():
    return load_hermes_env()


def save_env(env):
    env_path = HERMES_HOME / ".env"
    with open(env_path, "w") as f:
        for key, value in env.items():
            f.write(f"{key}={value}\n")


def _save_env_value_local(key: str, value: str) -> None:
    env = get_env()
    env[key] = value
    save_env(env)


def _mask_secret(value: str) -> str:
    if not value or len(value) < 8:
        return "****" if value else ""
    return value[:4] + "****" + value[-4:]


def _normalize_model_config(config: dict) -> dict:
    model = config.get("model")
    if isinstance(model, str):
        return {"default": model}
    if isinstance(model, dict):
        return model
    return {}


def _known_secret_catalog() -> dict[str, dict]:
    catalog = {**OPTIONAL_ENV_VARS, **EXTRA_SECRET_METADATA}
    catalog.setdefault(
        "API_SERVER_KEY",
        {
            "description": "Bearer token for API server authentication",
            "prompt": "API server auth key",
            "url": None,
            "password": True,
            "category": "messaging",
            "advanced": True,
        },
    )
    return catalog


def _friendly_secret_name(key: str, meta: dict) -> str:
    prompt = str(meta.get("prompt") or "").strip()
    if prompt:
        for suffix in (" API key", " API Key", " token", " Token"):
            if prompt.endswith(suffix):
                return prompt[: -len(suffix)]
        return prompt
    return key.replace("_", " ").title()


def _build_secrets_payload(env: dict) -> list[dict]:
    catalog = _known_secret_catalog()
    secrets = []
    seen: set[str] = set()
    for key, meta in sorted(catalog.items()):
        value = env.get(key, "")
        secrets.append(
            {
                "key": key,
                "name": _friendly_secret_name(key, meta),
                "description": meta.get("description", ""),
                "category": meta.get("category", "other"),
                "url": meta.get("url"),
                "configured": bool(value),
                "masked_value": _mask_secret(value),
                "advanced": bool(meta.get("advanced", False)),
                "password": bool(meta.get("password", True)),
            }
        )
        seen.add(key)

    for key, value in sorted(env.items()):
        if key in seen:
            continue
        if (
            "API_KEY" in key
            or "TOKEN" in key
            or "SECRET" in key
            or key.endswith("_URL")
        ):
            secrets.append(
                {
                    "key": key,
                    "name": key.replace("_", " ").title(),
                    "description": "",
                    "category": "other",
                    "url": None,
                    "configured": bool(value),
                    "masked_value": _mask_secret(value),
                    "advanced": True,
                    "password": not key.endswith("_URL"),
                }
            )

    return secrets


def _count_changed_values(current, default) -> int:
    if isinstance(default, dict):
        if not isinstance(current, dict):
            return 1
        changed = 0
        for key, value in default.items():
            if str(key).startswith("_"):
                continue
            if key in current:
                changed += _count_changed_values(current[key], value)
        for key in current:
            if key not in default and not str(key).startswith("_"):
                changed += 1
        return changed
    return 0 if current == default else 1


def _platform_toolset_extras(raw_config: dict) -> dict[str, list[str]]:
    configurable = {key for key, _, _ in CONFIGURABLE_TOOLSETS}
    default_toolsets = {info["default_toolset"] for info in PLATFORMS.values()}
    platform_toolsets = raw_config.get("platform_toolsets", {}) or {}
    extras: dict[str, list[str]] = {}
    for platform, entries in platform_toolsets.items():
        if not isinstance(entries, list):
            continue
        extras[platform] = sorted(
            entry
            for entry in entries
            if entry not in configurable and entry not in default_toolsets
        )
    return extras


def _resolved_platform_toolsets(config: dict) -> dict[str, list[str]]:
    configurable = {key for key, _, _ in CONFIGURABLE_TOOLSETS}
    resolved: dict[str, list[str]] = {}
    for platform in PLATFORMS:
        enabled = _get_platform_tools(config, platform)
        resolved[platform] = sorted(ts for ts in enabled if ts in configurable)
    return resolved


def _settings_payload() -> dict:
    effective = get_config()
    raw = get_raw_config()
    env = get_env()
    model = _normalize_model_config(effective)
    secrets = _build_secrets_payload(env)
    by_category: dict[str, dict] = {}
    for secret in secrets:
        category = secret["category"]
        bucket = by_category.setdefault(category, {"total": 0, "configured": 0})
        bucket["total"] += 1
        if secret["configured"]:
            bucket["configured"] += 1

    custom_personalities = (
        effective.get("agent", {}).get("personalities")
        or raw.get("agent", {}).get("personalities")
        or raw.get("personalities")
        or {}
    )

    return {
        "overview": {
            "profile_home": display_hermes_home(),
            "config_version": effective.get(
                "_config_version", DEFAULT_CONFIG.get("_config_version", 0)
            ),
            "changed_count": _count_changed_values(raw, DEFAULT_CONFIG),
            "missing_secrets_count": sum(
                1 for secret in secrets if not secret["configured"]
            ),
            "configured_secrets_count": sum(
                1 for secret in secrets if secret["configured"]
            ),
            "secrets_by_category": by_category,
        },
        "config": effective,
        "raw_config": raw,
        "model": {
            "default": model.get("default", ""),
            "provider": model.get("provider", "auto"),
            "base_url": model.get("base_url", ""),
        },
        "personality": {
            "current": effective.get("display", {}).get("personality", "helpful"),
            "built_in": BUILT_IN_PERSONALITIES,
            "custom": sorted(custom_personalities.keys()),
            "custom_definitions": custom_personalities,
        },
        "skins": list_skins(),
        "toolsets": [
            {"key": key, "label": label, "description": description}
            for key, label, description in CONFIGURABLE_TOOLSETS
        ],
        "platforms": [
            {
                "key": key,
                "label": value["label"],
                "default_toolset": value["default_toolset"],
            }
            for key, value in PLATFORMS.items()
        ],
        "resolved_platform_toolsets": _resolved_platform_toolsets(effective),
        "platform_toolset_extras": _platform_toolset_extras(raw),
        "web_backends": WEB_BACKENDS,
        "tts_providers": TTS_PROVIDERS,
        "stt_providers": STT_PROVIDERS,
        "busy_input_modes": BUSY_INPUT_MODES,
        "tool_progress_modes": TOOL_PROGRESS_MODES,
        "background_notification_modes": BACKGROUND_NOTIFICATION_MODES,
        "resume_display_modes": RESUME_DISPLAY_MODES,
        "approval_modes": APPROVAL_MODES,
        "reasoning_efforts": REASONING_EFFORTS,
        "secrets": secrets,
    }


async def homepage(request):
    response = templates.TemplateResponse(request, "index.html")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


async def chat_stream(request):
    body = await request.body()
    data = json.loads(body)
    run_id = str(data.get("run_id") or "").strip()
    resume = bool(data.get("resume"))
    session_id = str(data.get("session_id") or "").strip() or None

    if run_id and resume and run_id in ACTIVE_RUNS:
        state = ACTIVE_RUNS[run_id]
    else:
        messages = _sanitize_chat_messages(data.get("messages", []))
        preview = []
        for msg in messages[-6:]:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role", "?"))
            content = msg.get("content", "")
            if isinstance(content, list):
                content_preview = "[multimodal]"
                content_len = len(json.dumps(content))
            else:
                content_preview = str(content or "")[:120]
                content_len = len(str(content or ""))
            preview.append(
                {
                    "role": role,
                    "content": content_preview,
                    "len": content_len,
                }
            )
        print(
            f"[dashboard:/chat] messages={len(messages)} preview={preview}",
            file=sys.stderr,
            flush=True,
        )
        _cleanup_active_runs()
        run_id = run_id or f"run_{uuid.uuid4().hex}"
        state = {
            "events": deque(),
            "done": False,
            "created_at": time.time(),
            "updated_at": time.time(),
            "task": None,
            "session_id": session_id,
        }
        ACTIVE_RUNS[run_id] = state
        _log_stream(run_id, f"accepted sanitized_messages={len(messages)}")
        state["task"] = asyncio.create_task(
            _run_chat_stream(run_id, messages, session_id)
        )

    async def generate():
        sent = int(data.get("event_offset") or 0)
        last_heartbeat = time.time()
        try:
            if sent == 0:
                initial_session_id = state.get("session_id")
                yield {
                    "data": json.dumps(
                        {
                            "type": "run_state",
                            "run_id": run_id,
                            "session_id": initial_session_id,
                        }
                    )
                }
            while True:
                while sent < len(state["events"]):
                    event = state["events"][sent]
                    sent += 1
                    yield event
                    if event.get("data") == "[DONE]":
                        return
                if state.get("done"):
                    if sent >= len(state["events"]):
                        yield {"data": "[DONE]"}
                    return
                if time.time() - last_heartbeat >= 15:
                    last_heartbeat = time.time()
                    yield {
                        "data": json.dumps(
                            {
                                "type": "heartbeat",
                                "run_id": run_id,
                                "session_id": state.get("session_id"),
                            }
                        )
                    }
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            _log_stream(run_id, f"client disconnected after sent={sent}")
            task = state.get("task")
            if task is not None and not task.done():
                task.cancel()
            state["done"] = True
            raise

    return EventSourceResponse(
        generate(),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",
        },
    )


async def health(request):
    return JSONResponse({"status": "ok"})


async def get_status(request):
    config = get_config()
    env = get_env()
    model = _normalize_model_config(config)
    display = config.get("display", {})

    return JSONResponse(
        {
            "model": model.get("default", "unknown"),
            "provider": model.get("provider", "unknown"),
            "personality": display.get("personality", "helpful"),
            "max_turns": config.get("agent", {}).get("max_turns", 60),
            "memory_enabled": config.get("memory", {}).get("memory_enabled", True),
            "api_keys": {
                "openrouter": "OPENROUTER_API_KEY" in env
                or bool(env.get("OPENROUTER_API_KEY")),
                "zai": bool(
                    env.get("GLM_API_KEY")
                    or env.get("ZAI_API_KEY")
                    or env.get("Z_AI_API_KEY")
                ),
                "anthropic": "ANTHROPIC_API_KEY" in env
                or bool(env.get("ANTHROPIC_API_KEY")),
                "openai": bool(env.get("OPENAI_API_KEY")),
                "groq": bool(env.get("GROQ_API_KEY")),
                "kimi": bool(env.get("KIMI_API_KEY")),
                "minimax": bool(
                    env.get("MINIMAX_API_KEY") or env.get("MINIMAX_CN_API_KEY")
                ),
                "browserbase": bool(env.get("BROWSERBASE_API_KEY")),
                "firecrawl": bool(env.get("FIRECRAWL_API_KEY")),
                "api_server": bool(env.get("API_SERVER_KEY")),
            },
        }
    )


async def get_config_endpoint(request):
    return JSONResponse(get_raw_config())


async def get_settings(request):
    return JSONResponse(_settings_payload())


async def update_config(request):
    body = await request.body()
    updates = json.loads(body)
    config = get_raw_config()

    for key, value in updates.items():
        if "." in key:
            parts = key.split(".")
            current = config
            for part in parts[:-1]:
                if part not in current or not isinstance(current.get(part), dict):
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        else:
            config[key] = value

    save_config(config)
    return JSONResponse({"success": True})


async def get_models(request):
    env = get_env()
    config = get_config()
    model_config = _normalize_model_config(config)

    zai_api_key = (
        env.get("GLM_API_KEY") or env.get("ZAI_API_KEY") or env.get("Z_AI_API_KEY")
    )
    zai_base_url = (
        env.get("GLM_BASE_URL")
        or model_config.get("base_url")
        or "https://api.z.ai/api/paas/v4"
    )

    zai_models = None
    if zai_api_key:
        url = zai_base_url.rstrip("/") + "/models"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {zai_api_key}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                payload = resp.json()
                data = payload.get("data") if isinstance(payload, dict) else None
                if isinstance(data, list):
                    zai_models = sorted(
                        [
                            str(item.get("id", "")).strip()
                            for item in data
                            if isinstance(item, dict)
                            and str(item.get("id", "")).strip()
                        ]
                    )
        except Exception:
            zai_models = None

    if not zai_models:
        zai_models = ["glm-5", "glm-4.7", "glm-4.5", "glm-4.5-flash"]

    return JSONResponse(
        {
            "providers": [
                {
                    "id": "zai",
                    "name": "Z.AI / GLM",
                    "models": zai_models,
                },
                {
                    "id": "openrouter",
                    "name": "OpenRouter",
                    "models": [
                        "anthropic/claude-opus-4.6",
                        "anthropic/claude-sonnet-4.6",
                        "openai/gpt-4o",
                        "openai/o1",
                        "google/gemini-2.5-pro",
                    ],
                },
                {
                    "id": "anthropic",
                    "name": "Anthropic",
                    "models": ["claude-opus-4-20250514", "claude-sonnet-4-20250514"],
                },
                {"id": "nous", "name": "Nous Portal", "models": ["auto"]},
                {"id": "kimi-coding", "name": "Kimi", "models": ["kimi-latest"]},
            ]
        }
    )


async def get_personalities(request):
    config = get_config()
    custom = (
        list((config.get("agent", {}).get("personalities") or {}).keys())
        if config.get("agent", {}).get("personalities")
        else []
    )
    return JSONResponse(
        {
            "built_in": BUILT_IN_PERSONALITIES,
            "custom": custom,
            "current": config.get("display", {}).get("personality", "helpful"),
        }
    )


async def set_personality(request):
    body = await request.body()
    data = json.loads(body)
    personality = data.get("personality", "helpful")

    config = get_config()
    if "display" not in config:
        config["display"] = {}
    config["display"]["personality"] = personality
    save_config(config)

    return JSONResponse({"success": True, "personality": personality})


async def set_model(request):
    body = await request.body()
    data = json.loads(body)
    model = data.get("model")
    provider = data.get("provider")

    if not model:
        return JSONResponse(
            {"success": False, "error": "Model required"}, status_code=400
        )

    config = get_raw_config()
    if "model" not in config:
        config["model"] = {}
    elif isinstance(config["model"], str):
        config["model"] = {"default": config["model"]}
    config["model"]["default"] = model
    if provider:
        config["model"]["provider"] = provider
    save_config(config)

    return JSONResponse({"success": True, "model": model, "provider": provider})


async def get_agent_observability_endpoint(request):
    try:
        window_hours = int(request.query_params.get("window_hours", 24))
    except Exception:
        window_hours = 24
    try:
        trace_limit = int(request.query_params.get("trace_limit", 8))
    except Exception:
        trace_limit = 8
    return JSONResponse(get_agent_observability_report(window_hours, trace_limit))


async def get_sessions(request):
    db_path = HERMES_HOME / "state.db"
    if not db_path.exists():
        return JSONResponse({"sessions": [], "total": 0})

    limit = int(request.query_params.get("limit", 50))
    offset = int(request.query_params.get("offset", 0))
    search = request.query_params.get("search", "")
    sort = request.query_params.get("sort", "date_desc")
    source = request.query_params.get("source", "")

    order = "ASC" if sort == "date_asc" else "DESC"

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        _ensure_sessions_summary_column(conn)

        if not _sessions_table_exists(conn):
            conn.close()
            return JSONResponse({"sessions": [], "total": 0})

        conditions = []
        params = []

        if search:
            conditions.append(
                "s.id IN (SELECT session_id FROM messages WHERE content LIKE ?)"
            )
            params.append(f"%{search}%")

        if source:
            conditions.append("s.source = ?")
            params.append(source)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        # Get total count
        count_sql = f"SELECT COUNT(DISTINCT s.id) FROM sessions s {where_clause}"
        total = conn.execute(count_sql, params).fetchone()[0]

        # Get paginated results
        if search:
            query = f"""
                SELECT DISTINCT s.id, s.title, s.started_at, s.ended_at, s.source,
                       s.summary,
                       substr(m.content, 1, 100) as preview
                FROM sessions s
                LEFT JOIN messages m ON s.id = m.session_id
                {where_clause}
                ORDER BY s.started_at {order}
                LIMIT ? OFFSET ?
            """
        else:
            query = f"""
                SELECT s.id, s.title, s.started_at, s.ended_at, s.source,
                       s.summary,
                       (SELECT substr(content, 1, 100) FROM messages WHERE session_id = s.id ORDER BY timestamp LIMIT 1) as preview
                FROM sessions s
                {where_clause}
                ORDER BY s.started_at {order}
                LIMIT ? OFFSET ?
            """

        cursor = conn.execute(query, params + [limit, offset])
        sessions = []
        for row in cursor.fetchall():
            item = dict(row)
            if (
                not str(item.get("title") or "").strip()
                or not str(item.get("summary") or "").strip()
            ):
                refreshed = _refresh_local_session_metadata(conn, item.get("id", ""))
                item["title"] = refreshed.get("title") or item.get("title")
                item["summary"] = refreshed.get("summary") or item.get("summary")
            item["title"] = _session_label(
                item.get("title"),
                item.get("summary") or item.get("preview"),
                item.get("id", ""),
            )
            sessions.append(item)
        conn.close()

        return JSONResponse({"sessions": sessions, "total": total})
    except Exception as e:
        return JSONResponse({"sessions": [], "total": 0, "error": str(e)})


async def search_sessions(request):
    db_path = HERMES_HOME / "state.db"
    if not db_path.exists():
        return JSONResponse({"results": [], "total": 0, "offset": 0, "limit": 20})

    q = request.query_params.get("q", "").strip()
    status = request.query_params.get("status", "all").strip().lower()
    date_from = request.query_params.get("date_from", "").strip()
    date_to = request.query_params.get("date_to", "").strip()
    # tag is accepted but ignored since tags are not yet stored
    _ = request.query_params.get("tag", "").strip()
    limit = max(1, min(int(request.query_params.get("limit", 20)), 100))
    offset = max(0, int(request.query_params.get("offset", 0)))

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        _ensure_sessions_summary_column(conn)

        if not _sessions_table_exists(conn):
            conn.close()
            return JSONResponse(
                {"results": [], "total": 0, "offset": offset, "limit": limit}
            )

        conditions = []
        params = []

        if q:
            q_lower = q.lower()
            conditions.append(
                "(LOWER(s.title) LIKE ? OR LOWER(s.summary) LIKE ? OR s.id IN (SELECT session_id FROM messages WHERE LOWER(content) LIKE ?))"
            )
            params.extend([f"%{q_lower}%", f"%{q_lower}%", f"%{q_lower}%"])

        if status == "complete":
            conditions.append("s.ended_at IS NOT NULL")
        elif status == "running":
            conditions.append("s.ended_at IS NULL")
        elif status == "error":
            if _sessions_table_has_column(conn, "end_reason"):
                conditions.append("s.end_reason = 'error'")
            else:
                conditions.append("1=0")

        if date_from:
            conditions.append("s.started_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("s.started_at <= ?")
            params.append(date_to)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        count_sql = f"SELECT COUNT(DISTINCT s.id) FROM sessions s {where_clause}"
        total = conn.execute(count_sql, params).fetchone()[0]

        query = f"""
            SELECT DISTINCT s.id, s.title, s.summary, s.started_at, s.ended_at, s.source, s.end_reason
            FROM sessions s
            {where_clause}
            ORDER BY s.started_at DESC
            LIMIT ? OFFSET ?
        """

        cursor = conn.execute(query, params + [limit, offset])
        results = []

        for row in cursor.fetchall():
            item = dict(row)
            session_id = item["id"]

            if (
                not str(item.get("title") or "").strip()
                or not str(item.get("summary") or "").strip()
            ):
                refreshed = _refresh_local_session_metadata(conn, session_id)
                item["title"] = refreshed.get("title") or item.get("title")
                item["summary"] = refreshed.get("summary") or item.get("summary")

            title = _session_label(
                item.get("title"),
                item.get("summary"),
                session_id,
            )

            if item.get("ended_at"):
                if item.get("end_reason") == "error":
                    session_status = "error"
                else:
                    session_status = "complete"
            else:
                session_status = "running"

            match_context = ""
            if q:
                msg_row = conn.execute(
                    "SELECT content FROM messages WHERE session_id = ? AND LOWER(content) LIKE ? ORDER BY timestamp, id LIMIT 1",
                    (session_id, f"%{q.lower()}%"),
                ).fetchone()
                if msg_row:
                    content = msg_row["content"] or ""
                    idx = content.lower().find(q.lower())
                    if idx >= 0:
                        start = max(0, idx - 40)
                        end = min(len(content), idx + len(q) + 80)
                        snippet = content[start:end]
                        if start > 0:
                            snippet = "..." + snippet
                        if end < len(content):
                            snippet = snippet + "..."
                        match_context = snippet[:120]

            results.append(
                {
                    "session_id": session_id,
                    "title": title,
                    "status": session_status,
                    "created_at": item.get("started_at"),
                    "summary": item.get("summary") or "",
                    "tags": [],
                    "match_context": match_context,
                }
            )

        conn.close()
        return JSONResponse(
            {
                "results": results,
                "total": total,
                "offset": offset,
                "limit": limit,
            }
        )
    except Exception as e:
        return JSONResponse(
            {
                "results": [],
                "total": 0,
                "offset": offset,
                "limit": limit,
                "error": str(e),
            }
        )


async def get_session_sources(request):
    db_path = HERMES_HOME / "state.db"
    if not db_path.exists():
        return JSONResponse({"sources": []})
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT DISTINCT source FROM sessions WHERE source IS NOT NULL AND source != '' ORDER BY source"
        )
        sources = [row[0] for row in cursor.fetchall()]
        conn.close()
        return JSONResponse({"sources": sources})
    except Exception:
        return JSONResponse({"sources": []})


async def get_session(request):
    session_id = request.path_params["session_id"]
    db_path = HERMES_HOME / "state.db"

    if not db_path.exists():
        return JSONResponse({"error": "No sessions database"}, status_code=404)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _ensure_sessions_summary_column(conn)

    session_row = conn.execute(
        """
        SELECT id, title, summary, source, model, started_at, ended_at,
               parent_session_id, message_count, tool_call_count,
               input_tokens, output_tokens, estimated_cost_usd,
               cache_read_tokens, cache_write_tokens, reasoning_tokens,
               actual_cost_usd, cost_status, cost_source,
               end_reason, model_config, system_prompt,
               billing_provider, billing_base_url, billing_mode
        FROM sessions
        WHERE id = ?
    """,
        (session_id,),
    ).fetchone()
    if not session_row:
        conn.close()
        return JSONResponse({"error": "Session not found"}, status_code=404)

    session_payload = dict(session_row)
    if (
        not str(session_payload.get("title") or "").strip()
        or not str(session_payload.get("summary") or "").strip()
    ):
        refreshed = _refresh_local_session_metadata(conn, session_id)
        session_payload["title"] = refreshed.get("title") or session_payload.get(
            "title"
        )
        session_payload["summary"] = refreshed.get("summary") or session_payload.get(
            "summary"
        )

    cursor = conn.execute(
        """
        SELECT id, role, content, timestamp, tool_call_id, tool_calls, tool_name,
               token_count, finish_reason, reasoning, reasoning_details,
               codex_reasoning_items
        FROM messages
        WHERE session_id = ?
        ORDER BY timestamp, id
    """,
        (session_id,),
    )

    messages = []
    for row in cursor.fetchall():
        item = dict(row)
        if item.get("tool_calls"):
            try:
                item["tool_calls"] = json.loads(item["tool_calls"])
            except Exception:
                pass
        if item.get("reasoning_details"):
            try:
                item["reasoning_details"] = json.loads(item["reasoning_details"])
            except Exception:
                pass
        if item.get("codex_reasoning_items"):
            try:
                item["codex_reasoning_items"] = json.loads(
                    item["codex_reasoning_items"]
                )
            except Exception:
                pass
        messages.append(item)
    activity = _session_activity_payload(conn, session_id)
    overview = _session_overview_payload(conn, session_id)
    related_artifacts = _related_session_artifacts(
        [session_id] + [child.get("id", "") for child in overview.get("children", [])]
    )
    conn.close()

    return JSONResponse(
        {
            **session_payload,
            "messages": messages,
            **activity,
            **overview,
            "related_artifacts": related_artifacts,
        }
    )


async def backfill_session_summaries_endpoint(request):
    try:
        body = await request.body()
        data = json.loads(body) if body else {}
    except Exception:
        data = {}

    limit = max(1, min(int(data.get("limit", 50) or 50), 500))
    force = bool(data.get("force", False))
    db_path = HERMES_HOME / "state.db"
    if not db_path.exists():
        return JSONResponse(
            {"success": True, "processed": 0, "updated": 0, "failed": 0}
        )
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _ensure_sessions_summary_column(conn)
    try:
        query = (
            "SELECT id FROM sessions ORDER BY started_at DESC LIMIT ?"
            if force
            else "SELECT id FROM sessions WHERE summary IS NULL OR trim(summary) = '' OR title IS NULL OR trim(title) = '' ORDER BY started_at DESC LIMIT ?"
        )
        rows = conn.execute(query, (limit,)).fetchall()
        processed = 0
        updated = 0
        failed = 0
        for row in rows:
            processed += 1
            try:
                refreshed = _refresh_local_session_metadata(conn, row["id"])
                if refreshed.get("title") or refreshed.get("summary"):
                    updated += 1
            except Exception:
                failed += 1
        return JSONResponse(
            {
                "success": True,
                "processed": processed,
                "updated": updated,
                "failed": failed,
            }
        )
    finally:
        conn.close()


async def regenerate_session_summary_endpoint(request):
    session_id = request.path_params["session_id"]
    db_path = HERMES_HOME / "state.db"
    if not db_path.exists():
        return JSONResponse(
            {"success": False, "error": "No sessions database"}, status_code=404
        )
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _ensure_sessions_summary_column(conn)
    try:
        exists = conn.execute(
            "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not exists:
            return JSONResponse(
                {"success": False, "error": "Session not found"}, status_code=404
            )
        refreshed = _refresh_local_session_metadata(conn, session_id, force=True)
        if not refreshed.get("summary"):
            return JSONResponse(
                {"success": False, "error": "Failed to regenerate title and summary"},
                status_code=500,
            )
        return JSONResponse({"success": True, **refreshed})
    finally:
        conn.close()


def _run_startup_session_metadata_backfill() -> None:
    global _STARTUP_METADATA_BACKFILL_STARTED
    if _STARTUP_METADATA_BACKFILL_STARTED:
        return
    _STARTUP_METADATA_BACKFILL_STARTED = True

    def _worker() -> None:
        db_path = HERMES_HOME / "state.db"
        if not db_path.exists():
            return
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        _ensure_sessions_summary_column(conn)
        try:
            rows = conn.execute(
                "SELECT id FROM sessions WHERE summary IS NULL OR trim(summary) = '' OR title IS NULL OR trim(title) = '' ORDER BY started_at DESC LIMIT 1000"
            ).fetchall()
            print(f"[dashboard] Starting session metadata backfill for {len(rows)} sessions...")
            processed = 0
            for row in rows:
                try:
                    _refresh_local_session_metadata(conn, row["id"])
                    processed += 1
                except Exception as e:
                    print(f"[dashboard] Backfill error for {row['id']}: {e}")
                    continue
            print(f"[dashboard] Session metadata backfill complete: {processed}/{len(rows)} sessions processed")
        finally:
            conn.close()

    threading.Thread(
        target=_worker,
        daemon=True,
        name="dashboard-session-metadata-backfill",
    ).start()


@asynccontextmanager
async def _lifespan(_app):
    _run_startup_session_metadata_backfill()
    yield


def _dashboard_allowed_roots() -> list[Path]:
    roots: list[Path] = []
    env_root = os.getenv("HERMES_WRITE_SAFE_ROOT", "").strip()
    if env_root:
        roots.append(Path(env_root).expanduser().resolve())
    roots.append(Path.home().resolve())
    roots.append(Path.cwd().resolve())
    roots.append(HERMES_HOME.resolve())
    repos_dir = Path.home() / "repos"
    if repos_dir.is_dir():
        roots.append(repos_dir.resolve())
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def _resolve_allowed_path(raw_path: str) -> Optional[Path]:
    if not raw_path:
        return None
    try:
        candidate = Path(raw_path).expanduser().resolve()
    except Exception:
        return None
    for root in _dashboard_allowed_roots():
        try:
            candidate.relative_to(root)
            return candidate
        except ValueError:
            continue
    return None


def _safe_json_loads(value: str):
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def _collect_paths_from_payload(payload) -> list[str]:
    paths: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {"path", "file_path"} and isinstance(value, str):
                paths.append(value)
            elif key in {
                "paths",
                "files_created",
                "files_modified",
                "files",
            } and isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        paths.append(item)
            elif isinstance(value, (dict, list)):
                paths.extend(_collect_paths_from_payload(value))
    elif isinstance(payload, list):
        for item in payload:
            paths.extend(_collect_paths_from_payload(item))
    return paths


async def get_session_files(request):
    session_id = request.path_params["session_id"]
    db_path = HERMES_HOME / "state.db"

    if not db_path.exists():
        return JSONResponse({"files": []})

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        """
        SELECT role, content, timestamp, tool_call_id, tool_calls, tool_name
        FROM messages
        WHERE session_id = ?
        ORDER BY timestamp
        """,
        (session_id,),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    tool_calls_by_id = {}
    for row in rows:
        if row.get("role") != "assistant":
            continue
        payload = _safe_json_loads(row.get("tool_calls"))
        if not isinstance(payload, list):
            continue
        for tool_call in payload:
            func = tool_call.get("function", {}) if isinstance(tool_call, dict) else {}
            tool_calls_by_id[tool_call.get("id", "")] = {
                "tool": func.get("name", ""),
                "arguments": _safe_json_loads(func.get("arguments", "")) or {},
                "timestamp": row.get("timestamp"),
            }

    entries = {}
    for row in rows:
        if row.get("role") != "tool":
            continue
        call_id = row.get("tool_call_id", "")
        call = tool_calls_by_id.get(call_id, {})
        tool_name = call.get("tool") or row.get("tool_name") or "tool"
        if tool_name not in {"read_file", "write_file", "patch"}:
            continue
        args = call.get("arguments") or {}
        result = _safe_json_loads(row.get("content", "")) or {}
        raw_paths = _collect_paths_from_payload(args) + _collect_paths_from_payload(
            result
        )
        action = {"read_file": "read", "write_file": "wrote", "patch": "modified"}.get(
            tool_name, tool_name
        )
        for raw_path in raw_paths:
            allowed = _resolve_allowed_path(raw_path)
            key = str(allowed or raw_path)
            entries[key] = {
                "path": str(allowed or raw_path),
                "raw_path": raw_path,
                "tool": tool_name,
                "action": action,
                "timestamp": row.get("timestamp") or call.get("timestamp"),
                "previewable": bool(allowed and allowed.exists() and allowed.is_file()),
            }

    files = sorted(
        entries.values(), key=lambda item: item.get("timestamp") or 0, reverse=True
    )
    return JSONResponse(
        {"files": files, "roots": [str(root) for root in _dashboard_allowed_roots()]}
    )


async def get_file_content(request):
    raw_path = request.query_params.get("path", "")
    resolved = _resolve_allowed_path(raw_path)
    if resolved is None:
        return JSONResponse({"error": "Path is outside allowed roots"}, status_code=403)
    if not resolved.exists() or not resolved.is_file():
        return JSONResponse({"error": "File not found"}, status_code=404)
    try:
        content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return JSONResponse(
            {"error": "Binary file preview is not supported"}, status_code=415
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse({"path": str(resolved), "content": content})


async def delete_session(request):
    session_id = request.path_params["session_id"]
    db_path = HERMES_HOME / "state.db"

    if not db_path.exists():
        return JSONResponse({"error": "No sessions database"}, status_code=404)

    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()

    return JSONResponse({"success": True})


async def get_memory(request):
    memory_path = HERMES_HOME / "memories" / "MEMORY.md"
    user_path = HERMES_HOME / "memories" / "USER.md"

    memory_content = ""
    user_content = ""

    if memory_path.exists():
        with open(memory_path) as f:
            memory_content = f.read()

    if user_path.exists():
        with open(user_path) as f:
            user_content = f.read()

    return JSONResponse({"memory": memory_content, "user_profile": user_content})


async def update_memory(request):
    body = await request.body()
    data = json.loads(body)

    memory_dir = HERMES_HOME / "memories"
    memory_dir.mkdir(exist_ok=True)

    if "memory" in data:
        with open(memory_dir / "MEMORY.md", "w") as f:
            f.write(data["memory"])

    if "user_profile" in data:
        with open(memory_dir / "USER.md", "w") as f:
            f.write(data["user_profile"])

    return JSONResponse({"success": True})


SKILL_DESCRIPTIONS = {
    "apple": "Apple ecosystem integrations - Shortcuts, Music, Reminders, and device automation",
    "autonomous-ai-agents": "Multi-agent orchestration patterns for autonomous task execution",
    "creative": "Creative tools for image generation, art, and design workflows",
    "data-science": "Data analysis, visualization, ML model training, and Jupyter workflows",
    "devops": "Infrastructure automation, deployment pipelines, monitoring, and container management",
    "diagramming": "Create diagrams, flowcharts, architecture visualizations, and technical drawings",
    "dogfood": "Internal Hermes development and testing utilities",
    "domain": "Domain management, DNS configuration, and SSL certificate handling",
    "email": "Email composition, management, and automation workflows",
    "feeds": "RSS/Atom feed monitoring, aggregation, and content parsing",
    "gaming": "Game development, server management, and gaming platform integrations",
    "gifs": "GIF creation, processing, and animation workflows",
    "github": "GitHub workflow automation - repos, PRs, issues, code reviews, CI/CD pipelines",
    "inference-sh": "Inference.sh model deployment and serverless AI inference",
    "leisure": "Entertainment, games, trivia, and recreational activities",
    "mcp": "Model Context Protocol server management and tool integrations",
    "media": "Audio/video processing, transcoding, and media management",
    "mlops": "ML operations - model versioning, experiment tracking, deployment pipelines",
    "note-taking": "Note management, knowledge base integration, and organization tools",
    "productivity": "Productivity enhancements - calendars, tasks, reminders, workflows",
    "red-teaming": "Security testing, penetration testing, and vulnerability assessment",
    "research": "Academic research, paper analysis, citation management, and literature review",
    "smart-home": "Home automation - lights, climate, security, and IoT device control",
    "social-media": "Social platform integrations - posting, scheduling, analytics",
    "software-development": "Software engineering tools - debugging, testing, documentation",
    "web-automation": "Browser automation, web scraping, and form handling",
    "web-browsing": "Web navigation, content extraction, and online research",
}


def parse_description_md(filepath):
    """Parse DESCRIPTION.md with YAML frontmatter."""
    try:
        with open(filepath) as f:
            content = f.read()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                import yaml

                meta = yaml.safe_load(parts[1])
                return meta.get("description", "")
    except:
        pass
    return ""


SKILL_DESCRIPTIONS = {
    "apple": "Apple ecosystem integration - shortcuts, reminders, and macOS automation",
    "autonomous-ai-agents": "Autonomous agent patterns for self-directed task execution",
    "creative": "Creative tools for image generation, art, and design tasks",
    "data-science": "Data analysis, visualization, ML model training, and statistics",
    "devops": "DevOps tools for CI/CD, deployment, monitoring, and infrastructure",
    "diagramming": "Create diagrams, flowcharts, and visual documentation",
    "dogfood": "Internal Hermes development and testing utilities",
    "domain": "Domain management, DNS, and website configuration",
    "email": "Email automation, parsing, and management tools",
    "feeds": "RSS/Atom feed monitoring and content aggregation",
    "gaming": "Game development tools, stats tracking, and gaming APIs",
    "gifs": "GIF creation, editing, and management",
    "github": "GitHub workflow skills - repos, PRs, issues, code reviews, CI/CD",
    "inference-sh": "Inference.sh integration for AI model hosting",
    "leisure": "Fun tools - jokes, trivia, entertainment, and games",
    "mcp": "Model Context Protocol servers and tool integrations",
    "media": "Media handling - audio, video, image processing and conversion",
    "mlops": "ML Ops - model deployment, training pipelines, experiment tracking",
    "note-taking": "Note management - Obsidian, Notion, and markdown notes",
    "productivity": "Productivity tools - calendars, tasks, reminders, workflows",
    "red-teaming": "Security testing, penetration testing, and vulnerability assessment",
    "research": "Academic research - paper search, citation management, literature review",
    "smart-home": "Smart home automation - Home Assistant, IoT devices, sensors",
    "social-media": "Social media management - posting, scheduling, analytics",
    "software-development": "Software dev tools - debugging, testing, documentation",
    "trading": "Financial trading - market data, analysis, portfolio management",
    "travel": "Travel planning - flights, hotels, itineraries, weather",
    "web": "Web development - scraping, APIs, frontend, backend tools",
    "writing": "Writing assistance - editing, formatting, content creation",
}


async def get_skills(request):
    skills_dir = HERMES_HOME / "skills"
    skills = []

    if skills_dir.exists():
        for item in skills_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                skill_info = {"id": item.name, "path": str(item)}

                skill_md = item / "SKILL.md"
                if skill_md.exists():
                    with open(skill_md) as f:
                        content = f.read()
                        for line in content.split("\n")[:15]:
                            if line.startswith("name:"):
                                skill_info["name"] = line.split(":", 1)[1].strip()
                            elif line.startswith("description:"):
                                skill_info["description"] = line.split(":", 1)[
                                    1
                                ].strip()

                desc_md = item / "DESCRIPTION.md"
                if desc_md.exists() and "description" not in skill_info:
                    with open(desc_md) as f:
                        content = f.read()
                        for line in content.split("\n"):
                            if line.startswith("description:"):
                                skill_info["description"] = line.split(":", 1)[
                                    1
                                ].strip()
                                break

                if "name" not in skill_info:
                    skill_info["name"] = (
                        item.name.replace("-", " ").replace("_", " ").title()
                    )

                if "description" not in skill_info:
                    skill_info["description"] = SKILL_DESCRIPTIONS.get(item.name, "")

                skills.append(skill_info)

    config = get_config()
    disabled = set(config.get("skills", {}).get("disabled", []))

    return JSONResponse({"skills": skills, "disabled": list(disabled)})


async def toggle_skill(request):
    body = await request.body()
    data = json.loads(body)
    skill_id = data.get("skill_id")
    enabled = data.get("enabled", True)

    config = get_config()
    if "skills" not in config:
        config["skills"] = {}
    if "disabled" not in config["skills"]:
        config["skills"]["disabled"] = []

    disabled = set(config["skills"]["disabled"])

    if enabled:
        disabled.discard(skill_id)
    else:
        disabled.add(skill_id)

    config["skills"]["disabled"] = list(disabled)
    save_config(config)

    return JSONResponse({"success": True, "enabled": enabled})


async def get_skill_content(request):
    skill_id = request.path_params["skill_id"]
    skills_dir = HERMES_HOME / "skills" / skill_id

    if not skills_dir.exists():
        return JSONResponse({"error": "Skill not found"}, status_code=404)

    content = ""
    # Try SKILL.md first, then DESCRIPTION.md
    for filename in ["SKILL.md", "DESCRIPTION.md"]:
        filepath = skills_dir / filename
        if filepath.exists():
            with open(filepath) as f:
                content = f.read()
            break

    # Also list files in the skill directory
    files = []
    for item in skills_dir.iterdir():
        if item.is_file():
            files.append(item.name)

    return JSONResponse({"id": skill_id, "content": content, "files": files})


def _parse_game_skill_frontmatter(skill_md: Path) -> dict:
    """Return YAML frontmatter from a game SKILL.md file, tolerating plain markdown."""
    try:
        content = skill_md.read_text(encoding="utf-8")
    except Exception:
        return {}
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}
    return meta if isinstance(meta, dict) else {}


def _categorize_game_skill(tags: list[str], description: str) -> str:
    haystack = " ".join(tags + [description]).lower()

    def has_any(words: tuple[str, ...]) -> bool:
        return any(re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", haystack) for word in words)

    if has_any(("watch", "doom", "vizdoom", "fps", "stream")):
        return "Watch"
    if has_any(("emulator", "pokemon", "gameboy", "rom")):
        return "Emulator"
    if has_any(("server", "minecraft", "modpack")):
        return "Server"
    if has_any(("stats", "analytics", "coach", "strategy")):
        return "Analysis"
    return "Tool"


def get_games_catalog() -> dict:
    """Discover gaming-related Hermes skills for the dashboard Games tab."""
    gaming_dir = HERMES_HOME / "skills" / "gaming"
    games = []
    if gaming_dir.exists():
        for item in sorted(gaming_dir.iterdir(), key=lambda p: p.name.lower()):
            if not item.is_dir() or item.name.startswith("."):
                continue
            skill_md = item / "SKILL.md"
            meta = _parse_game_skill_frontmatter(skill_md) if skill_md.exists() else {}
            name = str(meta.get("name") or item.name)
            description = str(meta.get("description") or "")
            tags = meta.get("tags") or []
            if isinstance(tags, str):
                tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
            tags = [str(tag) for tag in tags]
            dashboard_meta = meta.get("dashboard") if isinstance(meta.get("dashboard"), dict) else {}
            game = {
                "id": item.name,
                "name": name.replace("-", " ").replace("_", " ").title(),
                "description": description,
                "tags": tags,
                "category": _categorize_game_skill(tags, description),
                "skill_path": str(skill_md if skill_md.exists() else item),
            }
            if dashboard_meta:
                upload_url = dashboard_meta.get("upload_url")
                upload_label = dashboard_meta.get("upload_label")
                watch_url = dashboard_meta.get("watch_url")
                launch_label = dashboard_meta.get("launch_label")
                control_url = dashboard_meta.get("control_url")
                control_label = dashboard_meta.get("control_label")
                status_hint = dashboard_meta.get("status_hint")
                if upload_url:
                    game["upload_url"] = str(upload_url)
                if upload_label:
                    game["upload_label"] = str(upload_label)
                if watch_url:
                    game["watch_url"] = str(watch_url)
                if launch_label:
                    game["launch_label"] = str(launch_label)
                if control_url:
                    game["control_url"] = str(control_url)
                if control_label:
                    game["control_label"] = str(control_label)
                if status_hint:
                    game["status_hint"] = str(status_hint)
            games.append(game)
    return {"games": games, "count": len(games)}


async def get_games_endpoint(request):
    return JSONResponse(get_games_catalog())


DOOM_WATCH_SERVER_URL = os.getenv("HERMES_DOOM_WATCH_URL", "http://127.0.0.1:9988")
MINIHACK_WATCH_SERVER_URL = os.getenv("HERMES_MINIHACK_WATCH_URL", "http://127.0.0.1:9989")
POKEMON_SERVER_URL = os.getenv("HERMES_POKEMON_SERVER_URL", "http://127.0.0.1:9879")
POKEMON_AGENT_ROOT = Path(os.getenv("HERMES_POKEMON_AGENT_ROOT", "/home/mojo/pokemon-agent")).expanduser()
POKEMON_ROM_PATH = Path(os.getenv("HERMES_POKEMON_ROM", "/home/mojo/roms/pokemon_gold.gbc")).expanduser()
POKEMON_DATA_DIR = Path(os.getenv("HERMES_POKEMON_DATA_DIR", "/home/mojo/.pokemon-agent-gold")).expanduser()
POKEMON_LOG_DIR = POKEMON_DATA_DIR / "logs"


async def _diagnostics_fetch_json(client, url, timeout=5.0):
    try:
        response = await client.get(url, timeout=timeout)
        text = response.text
        try:
            payload = response.json()
        except Exception:
            payload = {"text": text[:2000]}
        return {"ok": response.is_success, "status": response.status_code, "data": payload}
    except Exception as exc:
        return {"ok": False, "status": None, "error": str(exc)}


def _diagnostics_redact(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(token in key_text for token in ("key", "token", "secret", "password", "authorization")):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _diagnostics_redact(item)
        return redacted
    if isinstance(value, list):
        return [_diagnostics_redact(item) for item in value[:80]]
    if isinstance(value, str) and len(value) > 4000:
        return value[:4000] + "...[truncated]"
    return value


async def diagnostics_context_endpoint(request):
    target = request.query_params.get("target", "pokemon")
    base = POKEMON_SERVER_URL.rstrip("/")
    context = {
        "target": target,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "dashboard": {
            "hermes_home": display_hermes_home(),
            "hermes_api": HERMES_API,
            "pokemon_server_url": POKEMON_SERVER_URL,
            "active_runs": len(ACTIVE_RUNS),
        },
        "safety": {
            "mode": "observe_or_propose_by_default",
            "fix_policy": "Do not edit files, run commands, or restart services unless the user explicitly approves a specific plan.",
            "allowed_project_roots": ["/home/mojo/.hermes/dashboard", "/home/mojo/pokemon-agent"],
            "denied_paths": [".env", ".git", "ROM files", "save-state files unless explicitly approved"],
        },
        "pokemon": {},
    }
    async with httpx.AsyncClient() as client:
        for name, path in (
            ("health", "/health"),
            ("state", "/state"),
            ("autoplayer_status", "/autoplayer/status"),
            ("watch_status", "/watch/status"),
        ):
            context["pokemon"][name] = await _diagnostics_fetch_json(client, base + path)
    return JSONResponse(_diagnostics_redact(context))


def _pokemon_port() -> str:
    match = re.search(r":(\d+)(?:/|$)", POKEMON_SERVER_URL)
    return match.group(1) if match else "9879"


def _proc_cmdline(pid: int) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except Exception:
        return []
    return [part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part]


def _pokemon_process_kind(cmdline: list[str]) -> str | None:
    if not cmdline:
        return None
    joined = " ".join(cmdline)
    root = str(POKEMON_AGENT_ROOT)
    port = _pokemon_port()
    if root not in joined:
        return None
    if "gold_autoplayer_service.py" in joined:
        return "autoplayer_supervisor"
    if any(name in joined for name in ("gold_autoplayer_v2.py", "gold_autoplayer.py", "pokemon_autoplayer.py")):
        return "autoplayer_child"
    if "pokemon-agent" in joined and "serve" in cmdline and "--port" in cmdline and port in cmdline:
        return "server"
    return None


def _pokemon_related_processes() -> list[dict]:
    processes = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == os.getpid():
            continue
        cmdline = _proc_cmdline(pid)
        kind = _pokemon_process_kind(cmdline)
        if kind:
            processes.append({"pid": pid, "kind": kind, "cmdline": cmdline})
    order = {"autoplayer_child": 0, "autoplayer_supervisor": 1, "server": 2}
    return sorted(processes, key=lambda item: (order.get(item["kind"], 99), item["pid"]))


def _terminate_pokemon_processes(timeout: float = 5.0) -> list[dict]:
    targets = _pokemon_related_processes()
    for proc in targets:
        try:
            os.kill(proc["pid"], signal.SIGTERM)
        except ProcessLookupError:
            proc["terminated"] = True
        except Exception as exc:
            proc["terminate_error"] = str(exc)
    deadline = time.time() + timeout
    while time.time() < deadline:
        alive = {proc["pid"] for proc in _pokemon_related_processes()}
        if not any(proc["pid"] in alive for proc in targets):
            break
        time.sleep(0.1)
    alive = {proc["pid"] for proc in _pokemon_related_processes()}
    for proc in targets:
        if proc["pid"] in alive:
            try:
                os.kill(proc["pid"], signal.SIGKILL)
                proc["killed"] = True
            except ProcessLookupError:
                proc["terminated"] = True
            except Exception as exc:
                proc["kill_error"] = str(exc)
        else:
            proc["terminated"] = True
    return targets


def _start_pokemon_processes() -> dict:
    python = POKEMON_AGENT_ROOT / ".venv" / "bin" / "python"
    pokemon_agent = POKEMON_AGENT_ROOT / ".venv" / "bin" / "pokemon-agent"
    POKEMON_LOG_DIR.mkdir(parents=True, exist_ok=True)
    server_log_path = POKEMON_LOG_DIR / "dashboard-restart-server.log"
    supervisor_log_path = POKEMON_LOG_DIR / "dashboard-restart-autoplayer.log"
    server_log = server_log_path.open("ab", buffering=0)
    supervisor_log = supervisor_log_path.open("ab", buffering=0)
    common_kwargs = {
        "cwd": str(POKEMON_AGENT_ROOT),
        "stdin": subprocess.DEVNULL,
        "start_new_session": True,
    }
    server = subprocess.Popen(
        [
            str(python),
            str(pokemon_agent),
            "serve",
            "--rom",
            str(POKEMON_ROM_PATH),
            "--port",
            _pokemon_port(),
            "--data-dir",
            str(POKEMON_DATA_DIR),
        ],
        stdout=server_log,
        stderr=subprocess.STDOUT,
        **common_kwargs,
    )
    supervisor = subprocess.Popen(
        [
            str(python),
            str(POKEMON_AGENT_ROOT / "gold_autoplayer_service.py"),
            "--base-url",
            POKEMON_SERVER_URL,
            "--data-dir",
            str(POKEMON_DATA_DIR),
            "--delay",
            "1.25",
        ],
        stdout=supervisor_log,
        stderr=subprocess.STDOUT,
        **common_kwargs,
    )
    server_log.close()
    supervisor_log.close()
    return {
        "server_pid": server.pid,
        "autoplayer_supervisor_pid": supervisor.pid,
        "server_log": str(server_log_path),
        "autoplayer_log": str(supervisor_log_path),
    }


def _restart_pokemon_agent() -> dict:
    stopped = _terminate_pokemon_processes()
    started = _start_pokemon_processes()
    return {
        "ok": True,
        "message": "Pokemon agent restart requested",
        "stopped": [
            {"pid": proc["pid"], "kind": proc["kind"], "terminated": proc.get("terminated", False), "killed": proc.get("killed", False)}
            for proc in stopped
        ],
        "started": started,
        "pokemon_server_url": POKEMON_SERVER_URL,
    }


async def restart_pokemon_endpoint(request):
    try:
        result = await asyncio.to_thread(_restart_pokemon_agent)
        return JSONResponse(result)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


def _rewrite_doom_watch_html(html: str) -> str:
    """Make upstream Doom watch HTML safe under the dashboard /doom/ proxy.

    The standalone watch server uses root-absolute URLs like /status.json and
    /stream.mjpg. Those work when opened directly on port 9988, but inside the
    dashboard proxy they point at the dashboard root and 404. Rewriting them to
    /doom/... keeps the iframe same-origin and proxy-scoped.
    """
    replacements = {
        'src="/stream.mjpg"': 'src="/doom/stream.mjpg"',
        "src='/stream.mjpg'": "src='/doom/stream.mjpg'",
        "fetch('/status.json'": "fetch('/doom/status.json'",
        'fetch("/status.json"': 'fetch("/doom/status.json"',
        "<code>/status.json</code> · <code>/stream.mjpg</code>": "<code>/doom/status.json</code> · <code>/doom/stream.mjpg</code>",
    }
    for old, new in replacements.items():
        html = html.replace(old, new)
    return html


async def doom_watch_proxy_endpoint(request):
    """Proxy the local ViZDoom watch server through the dashboard origin.

    The watch server intentionally binds to 127.0.0.1 for safety. Browsing the
    dashboard from another machine would make an iframe pointed at 127.0.0.1 try
    to connect to the viewer's laptop instead of this host, causing connection
    refused. Keeping the skill URL as /doom/ and proxying here makes the iframe
    same-origin while preserving the local-only watch server.
    """
    path = request.path_params.get("path", "")
    upstream_path = "/" + path.lstrip("/") if path else "/"
    query = request.url.query
    upstream_url = DOOM_WATCH_SERVER_URL.rstrip("/") + upstream_path
    if query:
        upstream_url += "?" + query

    client = httpx.AsyncClient(timeout=None)
    try:
        body = await request.body() if request.method not in ("GET", "HEAD") else None
        headers = {}
        for header_name in ("content-type", "x-rom-filename"):
            header_value = request.headers.get(header_name)
            if header_value:
                headers[header_name] = header_value
        upstream_request = client.build_request(request.method, upstream_url, content=body, headers=headers)
        upstream = await client.send(upstream_request, stream=True)
    except httpx.RequestError as exc:
        await client.aclose()
        return PlainTextResponse(
            "Doom watch server is not responding. Start it with: "
            "cd ~/.hermes/skills/gaming/doom-player && "
            ".venv/bin/python scripts/doom_watch_server.py --host 127.0.0.1 --port 9988\n"
            f"Upstream error: {exc}",
            status_code=502,
        )

    content_type = upstream.headers.get("content-type", "application/octet-stream")
    if "text/html" in content_type.lower():
        try:
            body = await upstream.aread()
            text = body.decode(upstream.encoding or "utf-8", errors="replace")
            rewritten = _rewrite_doom_watch_html(text).encode("utf-8")
        finally:
            await upstream.aclose()
            await client.aclose()

        async def html_iter():
            yield rewritten

        return StreamingResponse(
            html_iter(),
            status_code=upstream.status_code,
            media_type="text/html; charset=utf-8",
            headers={"cache-control": "no-cache"},
        )

    async def body_iter():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    headers = {}
    for name in ("cache-control", "pragma", "age"):
        if name in upstream.headers:
            headers[name] = upstream.headers[name]
    return StreamingResponse(
        body_iter(),
        status_code=upstream.status_code,
        media_type=content_type,
        headers=headers,
    )


async def minihack_watch_proxy_endpoint(request):
    """Proxy the local MiniHack watch server through the dashboard origin."""
    path = request.path_params.get("path", "")
    upstream_path = "/" + path.lstrip("/") if path else "/"
    query = request.url.query
    upstream_url = MINIHACK_WATCH_SERVER_URL.rstrip("/") + upstream_path
    if query:
        upstream_url += "?" + query

    client = httpx.AsyncClient(timeout=None)
    try:
        body = await request.body() if request.method not in ("GET", "HEAD") else None
        headers = {}
        header_value = request.headers.get("content-type")
        if header_value:
            headers["content-type"] = header_value
        upstream_request = client.build_request(request.method, upstream_url, content=body, headers=headers)
        upstream = await client.send(upstream_request, stream=True)
    except httpx.RequestError as exc:
        await client.aclose()
        return PlainTextResponse(
            "MiniHack watch server is not responding. Start it with: "
            "cd ~/.hermes/skills/gaming/minihack-player && "
            ".venv/bin/python scripts/minihack_watch_server.py --host 127.0.0.1 --port 9989\n"
            f"Upstream error: {exc}",
            status_code=502,
        )

    async def body_iter():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    content_type = upstream.headers.get("content-type", "application/octet-stream")
    headers = {}
    for name in ("cache-control", "pragma", "age"):
        if name in upstream.headers:
            headers[name] = upstream.headers[name]
    return StreamingResponse(
        body_iter(),
        status_code=upstream.status_code,
        media_type=content_type,
        headers=headers,
    )


def _rewrite_pokemon_dashboard_js(js: str) -> str:
    """Scope the standalone pokemon-agent dashboard JS under /pokemon.

    The upstream dashboard assumes its API is mounted at the browser origin root
    (/state, /action, /screenshot/base64, /ws). In Hermes Dashboard it is opened
    inside an iframe at /pokemon/dashboard/, so HTTP calls must go through the
    dashboard proxy. WebSocket reconnects are optional because the upstream UI
    already polls screenshots/state; /pokemon/ws is still the correct same-origin
    location if a WS proxy is added later.
    """
    replacements = {
        "return window.location.protocol + '//' + window.location.host;":
            "return window.location.protocol + '//' + window.location.host + '/pokemon';",
        "return proto + '//' + window.location.host + '/ws';":
            "return proto + '//' + window.location.host + '/pokemon/ws';",
        "return proto + '//' + window.location.host + '/watch/ws?role=stats';":
            "return proto + '//' + window.location.host + '/pokemon/watch/ws?role=stats';",
    }
    for old, new in replacements.items():
        js = js.replace(old, new)
    return js


def _pokemon_upstream_path(path: str) -> str:
    path = (path or "").lstrip("/")
    if not path:
        return "/dashboard/"
    if path == "dashboard":
        return "/dashboard/"
    return "/" + path


async def pokemon_websocket_proxy_endpoint(websocket: WebSocket):
    path = websocket.path_params.get("path", "")
    if not path:
        path = websocket.url.path.removeprefix("/pokemon/")
    upstream_path = _pokemon_upstream_path(path)
    query = websocket.url.query
    upstream_url = POKEMON_SERVER_URL.rstrip("/").replace("http://", "ws://").replace("https://", "wss://") + upstream_path
    if query:
        upstream_url += "?" + query
    await websocket.accept()
    async with aiohttp.ClientSession() as session:
        try:
            async with session.ws_connect(upstream_url) as upstream:
                async def browser_to_upstream():
                    try:
                        while True:
                            message = await websocket.receive()
                            if message.get("type") == "websocket.disconnect":
                                await upstream.close()
                                break
                            if "text" in message:
                                await upstream.send_str(message["text"])
                            elif "bytes" in message:
                                await upstream.send_bytes(message["bytes"])
                    except WebSocketDisconnect:
                        await upstream.close()

                async def upstream_to_browser():
                    async for message in upstream:
                        if message.type == aiohttp.WSMsgType.TEXT:
                            await websocket.send_text(message.data)
                        elif message.type == aiohttp.WSMsgType.BINARY:
                            await websocket.send_bytes(message.data)
                        elif message.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED}:
                            break

                first_done, pending = await asyncio.wait(
                    {asyncio.create_task(browser_to_upstream()), asyncio.create_task(upstream_to_browser())},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                for task in first_done:
                    task.result()
        except Exception:
            try:
                await websocket.close()
            except Exception:
                pass


async def pokemon_proxy_endpoint(request):
    """Proxy the local pokemon-agent dashboard/API through Hermes Dashboard.

    This mirrors the Doom watch proxy: the game server stays local to this host,
    while remote dashboard users can open /pokemon/dashboard/ in the Games tab
    and still view frames plus send A/B/D-pad controls.
    """
    path = request.path_params.get("path", "")
    upstream_path = _pokemon_upstream_path(path)
    query = request.url.query
    upstream_url = POKEMON_SERVER_URL.rstrip("/") + upstream_path
    if query:
        upstream_url += "?" + query

    client = httpx.AsyncClient(timeout=None)
    try:
        body = await request.body() if request.method not in ("GET", "HEAD") else None
        headers = {}
        content_type_header = request.headers.get("content-type")
        if content_type_header:
            headers["content-type"] = content_type_header
        upstream_request = client.build_request(request.method, upstream_url, content=body, headers=headers)
        upstream = await client.send(upstream_request, stream=True)
    except httpx.RequestError as exc:
        await client.aclose()
        return PlainTextResponse(
            "Pokemon server is not responding. Start it with: "
            "cd /home/mojo/pokemon-agent && . .venv/bin/activate && "
            "pokemon-agent serve --rom /home/mojo/roms/pokemon_gold.gbc --port 9879 "
            "--data-dir /home/mojo/.pokemon-agent-gold\n"
            f"Upstream error: {exc}",
            status_code=502,
        )

    content_type = upstream.headers.get("content-type", "application/octet-stream")
    lower_content_type = content_type.lower()
    should_rewrite_js = upstream_path.endswith(".js") or "javascript" in lower_content_type
    if should_rewrite_js:
        try:
            body = await upstream.aread()
            text = body.decode(upstream.encoding or "utf-8", errors="replace")
            rewritten = _rewrite_pokemon_dashboard_js(text).encode("utf-8")
        finally:
            await upstream.aclose()
            await client.aclose()

        async def js_iter():
            yield rewritten

        return StreamingResponse(
            js_iter(),
            status_code=upstream.status_code,
            media_type="application/javascript; charset=utf-8",
            headers={"cache-control": "no-cache"},
        )

    async def body_iter():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    headers = {}
    for name in ("cache-control", "pragma", "age"):
        if name in upstream.headers:
            headers[name] = upstream.headers[name]
    return StreamingResponse(
        body_iter(),
        status_code=upstream.status_code,
        media_type=content_type,
        headers=headers,
    )


async def get_game_content_endpoint(request):
    game_id = request.path_params["game_id"]
    safe_id = Path(game_id).name
    game_dir = HERMES_HOME / "skills" / "gaming" / safe_id
    skill_md = game_dir / "SKILL.md"
    if not skill_md.exists():
        return JSONResponse({"error": "Game skill not found"}, status_code=404)
    try:
        content = skill_md.read_text(encoding="utf-8")
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    files = [item.name for item in game_dir.iterdir() if item.is_file()]
    return JSONResponse({"id": f"gaming/{safe_id}", "content": content, "files": files})


SELF_IMPROVEMENT_ALLOWED_LAYERS = {
    "agent_core",
    "tooling",
    "cron_autonomy",
    "memory_becomussy",
    "subagents",
    "provider_routing",
    "testing_verification",
    "dashboard_control_surface",
}
SELF_IMPROVEMENT_BANNED_PHRASES = (
    "new github project",
    "github actions",
    "repo creation",
    "standalone project",
    "unrelated project",
    "gh repo create",
    "git push",
)


def _self_improvement_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_self_improvement_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_self_improvement_audit(action: str, details: dict, actor: str = "dashboard") -> dict:
    entry = {
        "id": f"audit_{uuid.uuid4().hex[:12]}",
        "action": action,
        "actor": actor,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "details": details,
    }
    audit_path = SELF_IMPROVEMENT_HOME / "control-audit.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def _read_self_improvement_audit(limit: int = 20) -> list[dict]:
    audit_path = SELF_IMPROVEMENT_HOME / "control-audit.jsonl"
    entries: list[dict] = []
    if audit_path.exists():
        for line in audit_path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                entries.append(item)
    return list(reversed(entries[-limit:]))


def _summarize_validation(validation: dict) -> tuple[str, float, list[str]]:
    status = str(validation.get("status") or validation.get("result") or "").lower()
    commands_raw = validation.get("commands") or validation.get("verification_commands") or []
    commands: list[str] = []
    failures = 0
    if isinstance(commands_raw, list):
        for item in commands_raw:
            if isinstance(item, dict):
                command = item.get("command") or item.get("cmd")
                if command:
                    commands.append(str(command))
                if item.get("exit_code") not in (None, 0, "0"):
                    failures += 1
            elif isinstance(item, str):
                commands.append(item)
    if status in {"passed", "pass", "ok", "success"} and failures == 0:
        return "verified_useful_change", 1.0, commands
    if status in {"skipped", "skip", "silent", "noop", "no-op", "paused"}:
        return "valid_skip", 0.5, commands
    if status or failures:
        return "failed_or_unsafe_attempt", 0.0, commands
    return "unknown", 0.0, commands


def _read_self_improvement_candidate_events(limit: int = 20) -> dict:
    """Read the append-only self-improvement candidate event sidecar for UI audit timelines."""
    events_path = SELF_IMPROVEMENT_HOME / "feature-candidate-events.jsonl"
    candidates_by_id = {
        str(candidate.get("id")): candidate
        for candidate in _load_self_improvement_jsonl_queue(_self_improvement_feature_queue_path())
        if candidate.get("id")
    }
    events: list[dict] = []
    malformed = 0
    if events_path.exists():
        for line_no, line in enumerate(events_path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception:
                malformed += 1
                continue
            if not isinstance(item, dict):
                malformed += 1
                continue
            candidate_id = str(item.get("candidate_id") or item.get("id") or "")
            candidate = candidates_by_id.get(candidate_id, {})
            events.append(
                {
                    "at": item.get("at") or item.get("created_at") or item.get("updated_at"),
                    "operation": item.get("operation"),
                    "candidate_id": candidate_id,
                    "candidate_title": item.get("candidate_title") or item.get("title") or candidate.get("title"),
                    "previous_status": item.get("previous_status"),
                    "new_status": item.get("new_status") or item.get("status"),
                    "actor": item.get("actor"),
                    "reason": item.get("reason"),
                    "artifact": item.get("artifact"),
                    "line_no": line_no,
                }
            )
    events = sorted(events, key=lambda event: str(event.get("at") or ""), reverse=True)[:limit]
    operation_counts: dict[str, int] = {}
    status_transition_counts: dict[str, int] = {}
    for event in events:
        operation = str(event.get("operation") or "unknown")
        transition = f"{event.get('previous_status') or 'unknown'}->{event.get('new_status') or 'unknown'}"
        operation_counts[operation] = operation_counts.get(operation, 0) + 1
        status_transition_counts[transition] = status_transition_counts.get(transition, 0) + 1
    return {
        "events": events,
        "count": len(events),
        "limit": limit,
        "malformed_count": malformed,
        "operation_counts": operation_counts,
        "status_transition_counts": status_transition_counts,
        "source": str(events_path),
        "ok": malformed == 0,
    }


def _read_self_improvement_candidate_event_coverage() -> dict:
    """Return compact read-only event-ledger replay coverage for the dashboard.

    The canonical queue helper owns lifecycle replay and missing-coverage
    severity.  Surface its summary contract here so operators can see when the
    mutable queue looks healthy but older built/debated candidates lack durable
    append-only event coverage.
    """
    queue_path = _self_improvement_feature_queue_path()
    event_ledger_path = SELF_IMPROVEMENT_HOME / "feature-candidate-events.jsonl"
    helper = _load_self_improvement_queue_helper()
    if helper is not None and hasattr(helper, "replay_events"):
        try:
            result = helper.replay_events(queue_path, event_ledger_path, summary=True)
            if isinstance(result, dict):
                result = dict(result)
                result.setdefault("source", "self_improvement_queue.replay_events")
                result.setdefault("queue_path", str(queue_path))
                result.setdefault("event_ledger_path", str(event_ledger_path))
                return result
        except Exception as exc:
            return {
                "ok": False,
                "coverage_ok": False,
                "source": "self_improvement_queue.replay_events",
                "queue_path": str(queue_path),
                "event_ledger_path": str(event_ledger_path),
                "error": str(exc),
                "missing_event_coverage": {"count": None, "status_counts": {}, "candidate_ids_by_status": {}, "candidates": []},
                "missing_event_coverage_severity": {"coverage_ok": False, "level": "unknown", "reason": str(exc)},
            }

    # Last-resort read-only fallback for test/lightweight environments without
    # the helper: report whether known queue candidates have no event rows.
    candidates = _load_self_improvement_jsonl_queue(queue_path)
    events = _read_self_improvement_candidate_events(limit=10_000)
    covered_ids = {str(event.get("candidate_id")) for event in events.get("events", []) if event.get("candidate_id")}
    missing_by_status: dict[str, list[str]] = {}
    for candidate in candidates:
        cid = str(candidate.get("id") or "")
        if cid and cid not in covered_ids:
            status = str(candidate.get("status") or "queued")
            missing_by_status.setdefault(status, []).append(cid)
    missing_count = sum(len(values) for values in missing_by_status.values())
    level = "high" if any(status in missing_by_status for status in ("built", "debated", "selected")) else ("low" if missing_count else "ok")
    return {
        "ok": events.get("ok", True),
        "coverage_ok": missing_count == 0,
        "source": "dashboard-fallback",
        "queue_path": str(queue_path),
        "event_ledger_path": str(event_ledger_path),
        "event_count": events.get("count", 0),
        "candidate_count": len(candidates),
        "anomaly_count": events.get("malformed_count", 0),
        "missing_event_coverage": {
            "count": missing_count,
            "status_counts": {status: len(ids) for status, ids in missing_by_status.items()},
            "candidate_ids_by_status": missing_by_status,
            "candidates": [
                {"id": cid, "status": status}
                for status, ids in missing_by_status.items()
                for cid in ids[:5]
            ][:10],
        },
        "missing_event_coverage_severity": {
            "coverage_ok": missing_count == 0,
            "level": level,
            "missing_count": missing_count,
            "reason": "dashboard fallback event coverage summary",
        },
    }



def _read_step_journal_summary(path: Path) -> dict:
    """Summarize a run's append-only step_journal.jsonl for recovery visibility."""
    records: list[dict] = []
    malformed = 0
    if path.exists():
        for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception:
                malformed += 1
                continue
            if not isinstance(item, dict):
                malformed += 1
                continue
            record = dict(item)
            record.setdefault("line_no", line_no)
            records.append(record)
    status_counts: dict[str, int] = {}
    latest_by_step: dict[str, dict] = {}
    for record in records:
        status = str(record.get("status") or "unknown")
        step_name = str(record.get("step_name") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        latest_by_step[step_name] = record
    latest_records = sorted(
        records,
        key=lambda item: str(item.get("completed_at") or item.get("started_at") or item.get("at") or ""),
        reverse=True,
    )
    latest_step = latest_records[0] if latest_records else None
    recoverable_steps = [
        record
        for record in latest_by_step.values()
        if str(record.get("status") or "") in {"failed", "started", "waiting"}
    ]
    recoverable_steps = sorted(
        recoverable_steps,
        key=lambda item: str(item.get("started_at") or item.get("completed_at") or item.get("at") or ""),
    )
    return {
        "exists": path.exists(),
        "source": str(path),
        "count": len(records),
        "malformed_count": malformed,
        "status_counts": status_counts,
        "latest_step": latest_step,
        "latest_step_status": latest_step.get("status") if isinstance(latest_step, dict) else None,
        "recoverable": bool(recoverable_steps),
        "recoverable_steps": recoverable_steps,
        "recoverable_step_count": len(recoverable_steps),
        "ok": malformed == 0,
    }


def get_self_improvement_ledger(limit: int = 25) -> dict:
    runs_dir = SELF_IMPROVEMENT_HOME / "runs"
    runs: list[dict] = []
    if runs_dir.exists():
        for run_dir in sorted((p for p in runs_dir.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True):
            decision = _self_improvement_json(run_dir / "decision.json", {})
            validation = _self_improvement_json(run_dir / "validation.json", {})
            backup = _self_improvement_json(run_dir / "backup.json", {})
            changes_path = run_dir / "changes.md"
            summary = ""
            if changes_path.exists():
                summary = changes_path.read_text(encoding="utf-8", errors="replace").strip().split("\n", 1)[0][:240]
            outcome, score, commands = _summarize_validation(validation if isinstance(validation, dict) else {})
            artifacts = [p.name for p in sorted(run_dir.iterdir()) if p.is_file()]
            run_id = str(decision.get("run_id") or run_dir.name) if isinstance(decision, dict) else run_dir.name
            step_journal_summary = _read_step_journal_summary(run_dir / "step_journal.jsonl")
            runs.append(
                {
                    "run_id": run_id,
                    "started_at": decision.get("started_at") if isinstance(decision, dict) else None,
                    "ended_at": validation.get("ended_at") if isinstance(validation, dict) else None,
                    "trigger_source": decision.get("trigger_source") if isinstance(decision, dict) else None,
                    "selected_layer": decision.get("selected_layer") if isinstance(decision, dict) else None,
                    "candidate": decision.get("candidate") or decision.get("candidate_title") if isinstance(decision, dict) else None,
                    "files_touched": validation.get("files_touched", []) if isinstance(validation, dict) else [],
                    "verification_commands": commands,
                    "status": validation.get("status") if isinstance(validation, dict) else None,
                    "outcome": outcome,
                    "outcome_score": score,
                    "summary": summary,
                    "artifacts": artifacts,
                    "artifact_dir": str(run_dir),
                    "backup_dir": backup.get("backup_dir") if isinstance(backup, dict) else None,
                    "step_journal_summary": step_journal_summary,
                    "recoverable_step_count": step_journal_summary["recoverable_step_count"],
                    "latest_step_status": step_journal_summary["latest_step_status"],
                }
            )
            if len(runs) >= limit:
                break
    return {"runs": runs, "count": len(runs), "candidate_event_timeline": _read_self_improvement_candidate_events()}


def _self_improvement_feature_queue_path() -> Path:
    return SELF_IMPROVEMENT_HOME / "feature-candidates.jsonl"


def _self_improvement_queue_helper_path() -> Path:
    return Path.home() / "scripts" / "self-augment" / "self_improvement_queue.py"


def _load_self_improvement_queue_helper():
    """Load the canonical queue helper used by research/tournament crons."""
    helper_path = _self_improvement_queue_helper_path()
    if not helper_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("hermes_self_improvement_queue", helper_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalize_dashboard_candidate_for_strict_queue(candidate: dict) -> dict:
    """Map dashboard submissions to the canonical strict JSONL queue schema."""
    item = _candidate_for_dashboard_policy(candidate)
    title = str(item.get("title") or "").strip()
    evidence_source = str(item.get("evidence_source") or "").strip()
    benefit = str(item.get("expected_measurable_benefit") or "").strip()
    problem = str(item.get("problem") or evidence_source or title or "Manual dashboard candidate").strip()
    if "proposed_solution" in item:
        proposed_solution = str(item.get("proposed_solution") or "").strip()
    else:
        proposed_solution = str(benefit or item.get("explanation") or "").strip()
    raw_has_evidence = isinstance((candidate or {}).get("evidence"), list)
    evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
    evidence = [str(value).strip() for value in evidence if str(value).strip()]
    if not raw_has_evidence:
        for value in (evidence_source, benefit, problem, proposed_solution):
            if value and value not in evidence:
                evidence.append(value)
    normalized = dict(item)
    normalized["title"] = title
    normalized["problem"] = problem
    normalized["proposed_solution"] = proposed_solution
    normalized["target_layer"] = item.get("target_layer") or item.get("allowed_layer") or "dashboard_control_surface"
    normalized["evidence"] = evidence[:4]
    normalized.setdefault("source", "dashboard")
    for dashboard_key, strict_key in (
        ("expected_impact", "usefulness_score"),
        ("evidence_strength", "novelty_score"),
        ("verification_clarity", "testability_score"),
    ):
        if strict_key not in normalized or normalized.get(strict_key) is None:
            normalized[strict_key] = int(item.get(dashboard_key, 5) or 5)
    return normalized


def _normalize_self_improvement_queue_candidate(candidate: dict, *, source_path: str) -> dict:
    """Normalize both dashboard legacy JSON and cron JSONL queue rows for the UI.

    The active self-improvement research/tournament pipeline writes JSONL rows
    with fields such as ``target_layer``, ``problem``, and
    ``proposed_solution``.  The dashboard originally used ``queue.json`` with
    ``allowed_layer`` and score/explanation fields.  Keep both shapes readable
    so the control surface reflects the live cron queue instead of a divergent
    legacy file.
    """
    item = dict(candidate or {})
    layer = str(item.get("target_layer") or item.get("allowed_layer") or "")
    item.setdefault("allowed_layer", layer)
    item.setdefault("target_layer", layer)
    if "score" not in item:
        score_parts = []
        for key in ("usefulness_score", "testability_score", "novelty_score"):
            try:
                value = item.get(key)
                if value is not None:
                    score_parts.append(float(value))
            except (TypeError, ValueError):
                pass
        item["score"] = round(sum(score_parts) / len(score_parts), 2) if score_parts else None
    if not item.get("explanation"):
        item["explanation"] = (
            item.get("selection_reason")
            or item.get("problem")
            or item.get("proposed_solution")
            or item.get("expected_measurable_benefit")
            or ""
        )
    item["queue_source"] = source_path
    return item


def _load_self_improvement_jsonl_queue(path: Path) -> list[dict]:
    if not path.exists():
        return []
    candidates: list[dict] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            normalized = _normalize_self_improvement_queue_candidate(row, source_path=path.name)
            normalized.setdefault("_queue_line", line_no)
            candidates.append(normalized)
    return candidates


def _load_self_improvement_legacy_queue(path: Path) -> list[dict]:
    data = _self_improvement_json(path, {"candidates": []})
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
        return []
    return [
        _normalize_self_improvement_queue_candidate(candidate, source_path=path.name)
        for candidate in data["candidates"]
        if isinstance(candidate, dict)
    ]


def _summarize_self_improvement_queue(candidates: list[dict]) -> dict:
    status_counts: dict[str, int] = {}
    target_layer_counts: dict[str, int] = {}
    for candidate in candidates:
        status = str(candidate.get("status") or "queued")
        layer = str(candidate.get("target_layer") or candidate.get("allowed_layer") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        target_layer_counts[layer] = target_layer_counts.get(layer, 0) + 1
    return {"total": len(candidates), "statuses": status_counts, "target_layers": target_layer_counts}


def _self_improvement_backlog_gate_summary(jsonl_path: Path, jsonl_candidates: list[dict]) -> dict:
    """Return the canonical research-cron backlog gate for dashboard visibility.

    The queue helper owns the live research/tournament capacity rules.  The
    dashboard should surface those read-only decisions instead of forcing
    operators to infer them from historical JSONL row counts.
    """
    helper = _load_self_improvement_queue_helper()
    if helper is not None and hasattr(helper, "backlog_gate"):
        try:
            result = helper.backlog_gate(jsonl_path)
            if isinstance(result, dict):
                return result
        except Exception as exc:
            return {"ok": False, "action": "unknown", "reason": str(exc), "queue_path": str(jsonl_path)}

    summary = _summarize_self_improvement_queue(jsonl_candidates)
    statuses = summary.get("statuses", {})
    queued_count = int(statuses.get("queued", 0))
    selected_count = int(statuses.get("selected", 0))
    target_queued_backlog = 6
    selected_pause_threshold = 3
    max_additions = 3
    if selected_count >= selected_pause_threshold:
        action = "silent"
        needed_additions = 0
        reason = "selected backlog is full; let the build loop consume selected candidates"
    elif queued_count >= target_queued_backlog:
        action = "silent"
        needed_additions = 0
        reason = "queued backlog is full; research cron should not add candidates"
    else:
        needed_additions = min(max_additions, max(0, target_queued_backlog - queued_count))
        action = "add_candidates" if needed_additions else "silent"
        reason = f"queued backlog has room for {needed_additions} candidate(s)"
    return {
        "ok": True,
        "action": action,
        "reason": reason,
        "queued_count": queued_count,
        "selected_count": selected_count,
        "target_queued_backlog": target_queued_backlog,
        "selected_pause_threshold": selected_pause_threshold,
        "max_additions_configured": max_additions,
        "max_additions_this_tick": needed_additions,
        "needed_additions": needed_additions,
        "summary": summary,
        "queue_path": str(jsonl_path),
    }


def _load_self_improvement_queue() -> dict:
    jsonl_path = _self_improvement_feature_queue_path()
    legacy_path = SELF_IMPROVEMENT_HOME / "queue.json"
    jsonl_candidates = _load_self_improvement_jsonl_queue(jsonl_path)
    legacy_candidates = _load_self_improvement_legacy_queue(legacy_path)
    seen = {str(candidate.get("id")) for candidate in jsonl_candidates if candidate.get("id")}
    merged = jsonl_candidates + [
        candidate for candidate in legacy_candidates
        if not candidate.get("id") or str(candidate.get("id")) not in seen
    ]
    return {
        "candidates": merged,
        "queue_path": str(jsonl_path if jsonl_path.exists() else legacy_path),
        "legacy_queue_path": str(legacy_path),
        "source_counts": {"feature-candidates.jsonl": len(jsonl_candidates), "queue.json": len(legacy_candidates)},
        "status_counts": _summarize_self_improvement_queue(merged).get("statuses", {}),
        "target_layer_counts": _summarize_self_improvement_queue(merged).get("target_layers", {}),
        "backlog_gate": _self_improvement_backlog_gate_summary(jsonl_path, jsonl_candidates),
    }


def _candidate_for_jsonl_queue(candidate: dict) -> dict:
    item = dict(candidate or {})
    item.setdefault("problem", item.get("evidence_source") or item.get("title") or "Manual dashboard candidate")
    item.setdefault("proposed_solution", item.get("expected_measurable_benefit") or item.get("explanation") or "")
    item.setdefault("target_layer", item.get("allowed_layer") or "dashboard_control_surface")
    item.setdefault("evidence", [item.get("evidence_source")] if item.get("evidence_source") else [])
    item.setdefault("updated_at", datetime.datetime.now(datetime.timezone.utc).isoformat())
    return item


def _candidate_for_dashboard_policy(candidate: dict) -> dict:
    """Accept either legacy dashboard fields or live JSONL queue fields for policy scoring."""
    item = dict(candidate or {})
    layer = item.get("allowed_layer") or item.get("target_layer")
    if layer is not None:
        item.setdefault("allowed_layer", layer)
        item.setdefault("target_layer", layer)

    evidence = item.get("evidence")
    if not str(item.get("evidence_source") or "").strip():
        if isinstance(evidence, list):
            first_evidence = next((str(value).strip() for value in evidence if str(value).strip()), "")
            if first_evidence:
                item["evidence_source"] = first_evidence
        elif str(evidence or "").strip():
            item["evidence_source"] = str(evidence).strip()

    if not str(item.get("expected_measurable_benefit") or "").strip():
        benefit = item.get("proposed_solution") or item.get("selection_reason") or item.get("problem")
        if str(benefit or "").strip():
            item["expected_measurable_benefit"] = str(benefit).strip()

    if not str(item.get("explanation") or "").strip():
        item["explanation"] = (
            item.get("selection_reason")
            or item.get("proposed_solution")
            or item.get("problem")
            or item.get("expected_measurable_benefit")
            or ""
        )
    return item


def _save_self_improvement_queue(data: dict) -> None:
    candidates = data.get("candidates", []) if isinstance(data, dict) else []
    if not isinstance(candidates, list):
        candidates = []
    path = _self_improvement_feature_queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        json.dumps(_candidate_for_jsonl_queue(candidate), sort_keys=True)
        for candidate in candidates
        if isinstance(candidate, dict)
    ]
    path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")


def _score_self_improvement_candidate(candidate: dict) -> tuple[float, list[str]]:
    candidate = _candidate_for_dashboard_policy(candidate)
    reasons: list[str] = []
    layer = str(candidate.get("allowed_layer") or "")
    if layer not in SELF_IMPROVEMENT_ALLOWED_LAYERS:
        reasons.append("outside allowed layers")
    title_blob = " ".join(
        str(candidate.get(k) or "")
        for k in ("title", "evidence_source", "expected_measurable_benefit", "explanation", "problem", "proposed_solution")
    ).lower()
    for phrase in SELF_IMPROVEMENT_BANNED_PHRASES:
        if phrase in title_blob:
            reasons.append(f"banned scope: {phrase}")
    if not str(candidate.get("evidence_source") or "").strip():
        reasons.append("missing evidence source")
    if not str(candidate.get("expected_measurable_benefit") or "").strip():
        reasons.append("missing measurable benefit")
    def bounded(name: str, default: int = 3) -> int:
        try:
            return max(1, min(5, int(candidate.get(name, default))))
        except Exception:
            return default
    evidence = bounded("evidence_strength")
    impact = bounded("expected_impact")
    clarity = bounded("verification_clarity")
    size = bounded("implementation_size")
    risk_text = str(candidate.get("risk") or "medium").strip().lower()
    risk_value = next(
        (prefix for prefix in ("low", "medium", "high") if risk_text.startswith(prefix)),
        "medium",
    )
    risk_penalty = {"low": 0.5, "medium": 1.5, "high": 3.0}[risk_value]
    score = evidence + impact + clarity - size - risk_penalty
    if reasons:
        score = min(score, 0.0)
    return round(score, 2), reasons


def add_self_improvement_candidate(candidate: dict) -> dict:
    queue = _load_self_improvement_queue()
    helper = _load_self_improvement_queue_helper()
    strict_item = _normalize_dashboard_candidate_for_strict_queue(candidate)
    strict_item.setdefault("id", f"cand_{uuid.uuid4().hex[:12]}")
    strict_item.setdefault("created_at", datetime.datetime.now(datetime.timezone.utc).isoformat())
    strict_item.setdefault("decision", None)
    strict_item.setdefault("selected_run_id", None)

    if helper is not None:
        result = helper.add_candidates(
            _self_improvement_feature_queue_path(),
            [strict_item],
            source="dashboard",
            strict=True,
        )
        if not result.get("ok"):
            item = _candidate_for_dashboard_policy(strict_item)
            item["score"] = 0.0
            item["status"] = "rejected"
            policy_score, policy_reasons = _score_self_improvement_candidate(item)
            errors = list(result.get("errors") or ["strict queue validation failed"])
            errors.extend(reason for reason in policy_reasons if reason not in errors)
            item["explanation"] = "; ".join(errors)
            _append_self_improvement_audit("candidate_added", {"candidate_id": item.get("id"), "status": item["status"]})
            return {"accepted": False, "candidate": item, "queue_result": result}
        if result.get("duplicates"):
            item = _candidate_for_dashboard_policy(strict_item)
            item["score"] = 0.0
            item["status"] = "rejected"
            item["explanation"] = "duplicate candidate already exists in canonical queue"
            _append_self_improvement_audit("candidate_added", {"candidate_id": item.get("id"), "status": item["status"]})
            return {"accepted": False, "candidate": item, "queue_result": result}
        refreshed = _load_self_improvement_queue()
        added_id = (result.get("candidate_ids") or [strict_item.get("id")])[0]
        item = next((entry for entry in refreshed["candidates"] if entry.get("id") == added_id), strict_item)
        item = _candidate_for_dashboard_policy(item)
        score, reasons = _score_self_improvement_candidate(item)
        item["score"] = score
        item["status"] = "queued" if not reasons else "rejected"
        item["explanation"] = "Accepted: canonical strict queue validation passed." if not reasons else "; ".join(reasons)
        _append_self_improvement_audit("candidate_added", {"candidate_id": item.get("id"), "status": item["status"]})
        return {"accepted": item["status"] == "queued", "candidate": item, "queue_result": result}

    item = _candidate_for_dashboard_policy(candidate)
    item.setdefault("id", f"cand_{uuid.uuid4().hex[:12]}")
    item.setdefault("created_at", datetime.datetime.now(datetime.timezone.utc).isoformat())
    item.setdefault("decision", None)
    item.setdefault("selected_run_id", None)
    score, reasons = _score_self_improvement_candidate(item)
    item["score"] = score
    item["status"] = "queued" if not reasons else "rejected"
    item["explanation"] = "Accepted: evidence-backed and in-scope." if not reasons else "; ".join(reasons)
    queue["candidates"].append(item)
    _save_self_improvement_queue(queue)
    _append_self_improvement_audit("candidate_added", {"candidate_id": item["id"], "status": item["status"]})
    return {"accepted": item["status"] == "queued", "candidate": item}


def list_self_improvement_candidates() -> dict:
    queue = _load_self_improvement_queue()
    candidates = sorted(queue["candidates"], key=lambda c: (c.get("status") != "queued", -float(c.get("score") or 0)))
    return {
        "candidates": candidates,
        "count": len(candidates),
        "queue_path": queue.get("queue_path"),
        "legacy_queue_path": queue.get("legacy_queue_path"),
        "source_counts": queue.get("source_counts", {}),
        "status_counts": queue.get("status_counts", {}),
        "target_layer_counts": queue.get("target_layer_counts", {}),
        "backlog_gate": queue.get("backlog_gate", {}),
    }


def select_self_improvement_candidate(threshold: float = 5.0) -> dict:
    queue = _load_self_improvement_queue()
    queued = [c for c in queue["candidates"] if c.get("status") == "queued"]
    if not queued:
        explanation = "No queued candidate clears policy; pause instead of inventing work."
        _append_self_improvement_audit("candidate_selection_paused", {"explanation": explanation})
        return {"decision": "pause", "explanation": explanation, "candidate": None}
    best = max(queued, key=lambda c: float(c.get("score") or 0))
    if float(best.get("score") or 0) < threshold:
        explanation = f"Best candidate score {best.get('score')} is below threshold {threshold}."
        _append_self_improvement_audit("candidate_selection_paused", {"explanation": explanation, "candidate_id": best.get("id")})
        return {"decision": "pause", "explanation": explanation, "candidate": best}
    best["status"] = "selected"
    best["decision"] = "build"
    best["selected_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    helper = _load_self_improvement_queue_helper()
    if helper is not None and best.get("id"):
        try:
            helper.update_status(
                _self_improvement_feature_queue_path(),
                str(best["id"]),
                "selected",
                reason="selected by dashboard control surface",
            )
        except Exception:
            _save_self_improvement_queue(queue)
    else:
        _save_self_improvement_queue(queue)
    _append_self_improvement_audit("candidate_selected", {"candidate_id": best.get("id"), "score": best.get("score")})
    return {"decision": "build", "explanation": best.get("explanation", "selected"), "candidate": best}


def _self_improvement_jobs_path() -> Path:
    return HERMES_HOME / "cron" / "jobs.json"


def _load_cron_jobs_file() -> dict:
    return _self_improvement_json(_self_improvement_jobs_path(), {"jobs": []})


def _iter_cron_jobs(jobs_data) -> list[dict]:
    if isinstance(jobs_data, dict):
        jobs = jobs_data.get("jobs", [])
    elif isinstance(jobs_data, list):
        jobs = jobs_data
    else:
        jobs = []
    return [job for job in jobs if isinstance(job, dict)]


def _cron_job_enabled(job: dict) -> bool:
    return bool(job.get("enabled", job.get("state") not in {"paused", "disabled"}))


def _find_self_improvement_job(jobs_data) -> Optional[dict]:
    for job in _iter_cron_jobs(jobs_data):
        if job.get("name") == "self-improvement-loop" or job.get("script") == "self-improvement-loop.py":
            return job
    return None


def get_self_improvement_cron_mesh() -> dict:
    jobs_data = _load_cron_jobs_file()
    jobs = _iter_cron_jobs(jobs_data)
    self_jobs = []
    legacy_jobs = []
    required_skills = {
        "self-aug-decision-packet",
        "self-gap-scout",
        "self-tool-registry",
        "self-tool-hygiene",
        "self-tool-smoke",
        "hermes-agent",
        "becomussy",
        "systematic-debugging",
    }
    banned_skills = {"zai-web-search", "spec-driven-build", "tournament-build", "github-repo-management"}
    for job in jobs:
        name = str(job.get("name") or "")
        script = str(job.get("script") or "")
        skills = [str(skill) for skill in (job.get("skills") or [])]
        enabled = _cron_job_enabled(job)
        summary = {
            "id": job.get("id"),
            "name": name,
            "script": script or None,
            "enabled": enabled,
            "state": job.get("state") or ("scheduled" if enabled else "paused"),
            "schedule": job.get("schedule"),
            "max_runs_per_day": job.get("max_runs_per_day"),
            "last_run_at": job.get("last_run_at"),
            "next_run_at": job.get("next_run_at"),
            "skills": skills,
            "missing_required_skills": sorted(required_skills - set(skills)) if name == "self-improvement-loop" else [],
            "banned_skills_present": sorted(set(skills) & banned_skills),
        }
        if "self-improvement" in name or "self-augmentation" in name or script == "self-improvement-loop.py":
            self_jobs.append(summary)
        elif name in {"autonomous-research", "autonomous-build", "tournament-build", "project-curation-tournament"}:
            legacy_jobs.append(summary)
    active_legacy = [job for job in legacy_jobs if job["enabled"]]
    primary = _find_self_improvement_job(jobs_data)
    primary_skills = set(primary.get("skills") or []) if primary else set()
    blockers: list[str] = []
    if not primary:
        blockers.append("self-improvement-loop cron job is missing")
    elif not _cron_job_enabled(primary):
        blockers.append("self-improvement-loop is paused")
    if primary and (required_skills - primary_skills):
        blockers.append("self-improvement-loop is missing required skills")
    if active_legacy:
        blockers.append("legacy build/research cron jobs are still active")
    return {
        "jobs_path": str(_self_improvement_jobs_path()),
        "job_count": len(jobs),
        "self_improvement_jobs": self_jobs,
        "legacy_jobs": legacy_jobs,
        "active_legacy_count": len(active_legacy),
        "primary_job_id": primary.get("id") if primary else None,
        "required_skills": sorted(required_skills),
        "ok": not blockers,
        "blockers": blockers,
    }


def get_self_improvement_drift_status() -> dict:
    runs_dir = SELF_IMPROVEMENT_HOME / "runs"
    latest = None
    if runs_dir.exists():
        candidates = []
        for path in runs_dir.glob("*/cron-drift*.json"):
            try:
                candidates.append((path.stat().st_mtime, path))
            except OSError:
                continue
        if candidates:
            latest = max(candidates, key=lambda item: item[0])[1]
    if latest:
        payload = _self_improvement_json(latest, {})
        if isinstance(payload, dict):
            return {
                "source": str(latest),
                "ok": bool(payload.get("ok", False)),
                "scope": payload.get("scope"),
                "finding_count": payload.get("finding_count", 0),
                "severity_counts": payload.get("severity_counts", {}),
                "inactive_skipped_count": payload.get("inactive_skipped_count"),
                "findings": payload.get("findings", [])[:8] if isinstance(payload.get("findings"), list) else [],
            }
    return {"source": None, "ok": None, "finding_count": None, "severity_counts": {}, "findings": []}


def get_self_improvement_supervisor() -> dict:
    jobs_data = _load_cron_jobs_file()
    job = _find_self_improvement_job(jobs_data)
    lock_path = SELF_IMPROVEMENT_HOME / "self-improvement.lock.json"
    lock = _self_improvement_json(lock_path, None) if lock_path.exists() else None
    ledger = get_self_improvement_ledger(limit=1)
    queue = list_self_improvement_candidates()
    queued_count = len([c for c in queue["candidates"] if c.get("status") == "queued"])
    return {
        "cron_job": job,
        "active": bool(job and job.get("enabled", job.get("state") != "paused")),
        "state": job.get("state") if job else "missing",
        "last_run_at": job.get("last_run_at") if job else None,
        "next_run_at": job.get("next_run_at") if job else None,
        "lock": {"locked": lock is not None, "path": str(lock_path), "data": lock},
        "recent_outcome_score": ledger["runs"][0]["outcome_score"] if ledger["runs"] else None,
        "queued_candidate_count": queued_count,
        "audit": _read_self_improvement_audit(),
    }


def _save_cron_jobs_file(jobs_data: dict) -> None:
    _write_self_improvement_json(_self_improvement_jobs_path(), jobs_data)


def apply_self_improvement_control(action: str, confirm: bool = False, actor: str = "dashboard") -> dict:
    action = str(action or "").strip().lower()
    jobs_data = _load_cron_jobs_file()
    job = _find_self_improvement_job(jobs_data)
    if action in {"pause", "resume"}:
        if not job:
            return {"success": False, "error": "self-improvement-loop cron job not found"}
        if action == "pause":
            job["enabled"] = False
            job["state"] = "paused"
            job["paused_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            job["paused_reason"] = "Paused from Hermes Dashboard supervisor"
        else:
            job["enabled"] = True
            job["state"] = "scheduled"
            job["paused_at"] = None
            job["paused_reason"] = None
        _save_cron_jobs_file(jobs_data)
        audit = _append_self_improvement_audit(f"cron_{action}", {"job_id": job.get("id")}, actor=actor)
        return {"success": True, "action": action, "cron_job": job, "audit": audit}
    if action == "clear_stale_lock":
        lock_path = SELF_IMPROVEMENT_HOME / "self-improvement.lock.json"
        if not confirm:
            return {"success": False, "error": "confirmation required to clear stale lock"}
        if lock_path.exists():
            lock_path.unlink()
        audit = _append_self_improvement_audit("lock_cleared", {"path": str(lock_path)}, actor=actor)
        return {"success": True, "action": action, "audit": audit}
    if action == "kill":
        audit = _append_self_improvement_audit("kill_requested", {"result": "no tracked process handle; cron paused only"}, actor=actor)
        if job:
            job["enabled"] = False
            job["state"] = "paused"
            job["paused_reason"] = "Kill-switch requested from Hermes Dashboard supervisor"
            _save_cron_jobs_file(jobs_data)
        return {"success": True, "action": action, "audit": audit, "note": "No live process handle was discoverable; future runs paused."}
    return {"success": False, "error": f"unknown control action: {action}"}


def _parse_outbox_datetime(value: object) -> datetime.datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed.astimezone(datetime.timezone.utc)
    except Exception:
        return None


def _nonempty_outbox_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_becomussy_outbox_record(record: dict) -> list[str]:
    """Mirror the local Becomussy outbox preflight checks used before replay."""
    issues: list[str] = []
    method = str(record.get("method") or "").upper()
    path = str(record.get("path") or "")
    data = record.get("data")
    if not path.startswith("/"):
        issues.append("path must start with /")
    if method not in {"POST", "PATCH", "PUT"}:
        issues.append("method must be POST, PATCH, or PUT")
    if not isinstance(data, dict):
        issues.append("data must be an object")
        return issues

    if path == "/memory" and method == "POST":
        if not _nonempty_outbox_text(data.get("summary")):
            issues.append("memory.summary is required")
        if "importance_score" in data:
            try:
                importance = float(data["importance_score"])
            except (TypeError, ValueError):
                issues.append("memory.importance_score must be numeric")
            else:
                if importance < 0 or importance > 999.99:
                    issues.append("memory.importance_score must be between 0 and 999.99")
        if "confidence_level" in data and data["confidence_level"] not in {"low", "medium", "high"}:
            issues.append("memory.confidence_level must be one of: low, medium, high")
    elif path == "/journal" and method == "POST":
        if not _nonempty_outbox_text(data.get("entry_type")):
            issues.append("journal.entry_type is required")
        if not _nonempty_outbox_text(data.get("title")):
            issues.append("journal.title is required")
        if not _nonempty_outbox_text(data.get("body_md")):
            issues.append("journal.body_md is required")
        if "tags" in data and not isinstance(data["tags"], list):
            issues.append("journal.tags must be a list")
    elif path.startswith("/threads/") and method == "PATCH":
        if path.rstrip("/") == "/threads":
            issues.append("threads update path must include a thread id")
        if "status" in data and data["status"] not in {"active", "archived", "deprecated", "deleted_soft"}:
            issues.append("threads.status must be one of: active, archived, deprecated, deleted_soft")
        if "next_action" in data and not _nonempty_outbox_text(data.get("next_action")):
            issues.append("threads.next_action must be non-empty when provided")
    return issues


def _becomussy_resume_packet_helper_path() -> Path:
    return Path.home() / "scripts" / "self-augment" / "becomussy_resume_packet.py"


def _load_becomussy_resume_packet_helper():
    helper_path = _becomussy_resume_packet_helper_path()
    if not helper_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("hermes_becomussy_resume_packet", helper_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json_chars(value) -> int:
    try:
        return len(json.dumps(value, sort_keys=True, default=str))
    except Exception:
        return len(str(value))


def _fallback_compact_becomussy_resume_packet(packet: dict, *, max_section_chars: int) -> dict:
    """Small local fallback matching the resume-packet compact contract shape."""
    compacted = json.loads(json.dumps(packet, default=str))
    section_sizes = {key: _json_chars(value) for key, value in packet.items()}
    truncated_sections: list[str] = []
    never_truncate = {"schema", "generated_at", "sources", "next_actions", "ok"}
    for key, size in section_sizes.items():
        if key in never_truncate or size <= max_section_chars:
            continue
        value = packet.get(key)
        summary: dict = {
            "_compact": {
                "truncated": True,
                "section": key,
                "original_json_chars": size,
                "max_section_chars": max_section_chars,
                "strategy": "dashboard_fallback_counts_preview",
            }
        }
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                if isinstance(child_value, list):
                    summary[child_key] = child_value[:1]
                    summary[f"{child_key}_total_count"] = len(child_value)
                elif isinstance(child_value, dict):
                    summary[child_key] = {
                        nested_key: nested_value
                        for nested_key, nested_value in child_value.items()
                        if isinstance(nested_value, (str, int, float, bool)) or nested_value is None
                    }
                elif isinstance(child_value, (str, int, float, bool)) or child_value is None:
                    summary[child_key] = child_value if not isinstance(child_value, str) else child_value[:240]
        elif isinstance(value, list):
            summary["items"] = value[:1]
            summary["items_total_count"] = len(value)
        compacted[key] = summary
        truncated_sections.append(key)
    compacted["compact"] = {
        "enabled": True,
        "max_section_chars": max_section_chars,
        "section_sizes": section_sizes,
        "truncated_sections": truncated_sections,
        "truncated_section_count": len(truncated_sections),
        "source": "dashboard_fallback" if truncated_sections else "dashboard_noop",
    }
    return compacted


def _compact_becomussy_resume_packet_for_dashboard(packet: dict, *, max_section_chars: int = 12000) -> dict:
    helper = _load_becomussy_resume_packet_helper()
    if helper is not None and hasattr(helper, "compact_packet"):
        try:
            compacted = helper.compact_packet(packet, max_section_chars=max_section_chars)
            if isinstance(compacted, dict):
                return compacted
        except Exception:
            pass
    return _fallback_compact_becomussy_resume_packet(packet, max_section_chars=max_section_chars)


def get_becomussy_resume_packet() -> dict:
    """Return the latest Becomussy-backed self-improvement resume packet.

    The packet is generated by ~/scripts/self-augment/becomussy_resume_packet.py
    and gives the dashboard one compact contract for resuming dashboard/features
    work even when live Becomussy retrieval is sparse or unavailable.
    """
    packet_path = SELF_IMPROVEMENT_HOME / "becomussy-resume-packet.json"
    compact_packet_path = SELF_IMPROVEMENT_HOME / "becomussy-resume-packet.compact.json"
    compact_packet = _self_improvement_json(compact_packet_path, {})
    if isinstance(compact_packet, dict) and compact_packet:
        packet = dict(compact_packet)
        packet.setdefault("source", str(compact_packet_path))
        packet.setdefault("full_source", str(packet_path))
        packet.setdefault("exists", compact_packet_path.exists() or packet_path.exists())
        return packet

    packet = _self_improvement_json(packet_path, {})
    if not isinstance(packet, dict) or not packet:
        return {
            "exists": packet_path.exists() or compact_packet_path.exists(),
            "source": str(packet_path),
            "compact_source": str(compact_packet_path),
            "ok": None,
            "schema": "hermes.becomussy_resume_packet.v1",
            "next_actions": ["Generate resume packet with ~/scripts/self-augment/becomussy_resume_packet.py before relying on dashboard resume state."],
        }
    packet = dict(packet)
    max_section_chars = int(os.getenv("DASHBOARD_BECOMUSSY_RESUME_PACKET_MAX_SECTION_CHARS", "12000"))
    if any(_json_chars(value) > max_section_chars for key, value in packet.items() if key not in {"schema", "generated_at", "sources", "next_actions", "ok"}):
        packet = _compact_becomussy_resume_packet_for_dashboard(packet, max_section_chars=max_section_chars)
    packet.setdefault("source", str(packet_path))
    packet.setdefault("compact_source", str(compact_packet_path))
    packet.setdefault("exists", packet_path.exists())
    return packet


def get_becomussy_outbox_health(limit_errors: int = 5) -> dict:
    """Summarize queued Becomussy continuity writes without mutating the outbox."""
    outbox_path = HERMES_HOME / "becomussy_outbox.jsonl"
    records: list[dict] = []
    malformed = 0
    if outbox_path.exists():
        for line_no, line in enumerate(outbox_path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception:
                malformed += 1
                continue
            if not isinstance(item, dict):
                malformed += 1
                continue
            item = dict(item)
            item["line_no"] = line_no
            records.append(item)

    pending = [item for item in records if not bool(item.get("done"))]
    done = [item for item in records if bool(item.get("done"))]
    pending_sorted = sorted(pending, key=lambda item: str(item.get("created_at") or ""))
    oldest_pending = pending_sorted[0] if pending_sorted else None
    oldest_pending_age_hours = None
    if oldest_pending:
        created_at = _parse_outbox_datetime(oldest_pending.get("created_at"))
        if created_at:
            oldest_pending_age_hours = round(
                (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds() / 3600,
                2,
            )
    error_rows = [item for item in records if item.get("last_error")]
    error_rows = sorted(error_rows, key=lambda item: str(item.get("created_at") or ""), reverse=True)[:limit_errors]
    invalid_records: list[dict] = []
    valid_pending_count = 0
    for item in pending:
        issues = _validate_becomussy_outbox_record(item)
        if issues:
            invalid_records.append({
                "id": item.get("id"),
                "path": item.get("path"),
                "method": item.get("method"),
                "created_at": item.get("created_at"),
                "line_no": item.get("line_no"),
                "issues": issues,
            })
        else:
            valid_pending_count += 1
    invalid_total_count = len(invalid_records)
    invalid_records = invalid_records[:limit_errors]
    recent_errors = [
        {
            "id": item.get("id"),
            "path": item.get("path"),
            "attempts": item.get("attempts", 0),
            "last_error": item.get("last_error"),
            "created_at": item.get("created_at"),
            "line_no": item.get("line_no"),
        }
        for item in error_rows
    ]
    status = "ok"
    status_reason = "no_pending_outbox_records"
    if malformed:
        status = "error"
        status_reason = "malformed_outbox_records"
    elif invalid_total_count:
        status = "attention"
        status_reason = "invalid_outbox_records"
    elif recent_errors:
        status = "attention"
        status_reason = "pending_replay_errors"
    elif pending:
        status = "attention"
        status_reason = "pending_replay_needed"
    return {
        "ok": malformed == 0,
        "status": status,
        "severity": status,
        "status_reason": status_reason,
        "exists": outbox_path.exists(),
        "source": str(outbox_path),
        "total_count": len(records),
        "pending_count": len(pending),
        "done_count": len(done),
        "malformed_count": malformed,
        "preflight_ok": invalid_total_count == 0,
        "invalid_count": invalid_total_count,
        "invalid_records": invalid_records,
        "valid_pending_count": valid_pending_count,
        "replay_needed": bool(pending),
        "oldest_pending": oldest_pending,
        "oldest_pending_age_hours": oldest_pending_age_hours,
        "recent_errors": recent_errors,
        "replay_command_hint": "~/scripts/self-augment/becomussy_outbox.py replay --preflight",
    }


def get_self_improvement_status() -> dict:
    cron_mesh = get_self_improvement_cron_mesh()
    drift = get_self_improvement_drift_status()
    return {
        "ledger": get_self_improvement_ledger(),
        "queue": list_self_improvement_candidates(),
        "candidate_event_timeline": _read_self_improvement_candidate_events(),
        "candidate_event_coverage": _read_self_improvement_candidate_event_coverage(),
        "becomussy_outbox": get_becomussy_outbox_health(),
        "becomussy_resume_packet": get_becomussy_resume_packet(),
        "supervisor": get_self_improvement_supervisor(),
        "cron_mesh": cron_mesh,
        "drift": drift,
        "policy": {
            "allowed_layers": sorted(SELF_IMPROVEMENT_ALLOWED_LAYERS),
            "banned_phrases": sorted(SELF_IMPROVEMENT_BANNED_PHRASES),
            "hub_ok": bool(cron_mesh.get("ok") and drift.get("ok") is not False),
        },
    }


AUTONOMOUS_DEVELOPMENT_DEFAULT_PIPELINES = [
    {
        "id": "self-improvement",
        "name": "Hermes Self-Improvement Pipeline",
        "description": "Active guarded pipeline for improving Hermes backend capabilities, tooling, Becomussy continuity, cron reliability, subagent workflows, tests, and dashboard control surfaces.",
        "kind": "self_improvement",
        "activation_mode": "managed",
        "desired_enabled": True,
        "schedule": "research every 180m · tournament every 120m · build every 120m",
        "job_names": ["self-improvement-research-queue", "self-improvement-feature-tournament", "self-improvement-loop"],
        "directories": ["~/self-improvement", "~/scripts/self-augment", "~/.hermes/scripts"],
        "specifications": {
            "research": "Mine Becomussy, cron outputs, skills, and self-augment scripts for small, testable Hermes self-improvement candidates; avoid Z.AI web search and duplicates.",
            "tournament": "Run a champion/judge tournament over queued candidates only when selection capacity exists; record exactly one winner and do not build in the tournament job.",
            "build": "Build one selected candidate with rollback snapshot, focused tests, self-tool hygiene/smoke, run artifacts, and lock release.",
            "safety": "Only improve Hermes itself; do not build unrelated standalone projects.",
        },
    },
    {
        "id": "legacy-software-development",
        "name": "Legacy Automated Software Development Pipeline",
        "description": "Paused research/spec/tournament/build system for generating standalone projects from specs. Registered here for visibility but intentionally not activated.",
        "kind": "legacy_software_development",
        "activation_mode": "manual",
        "desired_enabled": False,
        "schedule": "research every 120m · build every 240m · tournament every 60m",
        "job_names": ["autonomous-research", "autonomous-build", "tournament-build"],
        "directories": ["~/specs", "~/builds", "~/scripts/autonomous-cycle"],
        "specifications": {
            "research": "Generate genuinely novel non-developer consumer project specs with overlap checks, daily theme coverage, and uniqueness guarantees.",
            "tournament": "Debate eligible specs under diversity constraints before selecting a build target.",
            "build": "Build selected specs with tests and packaging; legacy pipeline remains disabled until explicitly enabled.",
            "safety": "Keep disabled by default; no GitHub push/repo creation without explicit approval.",
        },
    },
    {
        "id": "legacy-project-curation",
        "name": "Legacy Project Curation Pipeline",
        "description": "Paused local-only curation tournament over existing assistant-built projects. Registered for management but intentionally not activated.",
        "kind": "legacy_project_curation",
        "activation_mode": "manual",
        "desired_enabled": False,
        "schedule": "curation tournament every 60m",
        "job_names": ["project-curation-tournament"],
        "directories": ["~/curation", "~/scripts/project-curation", "~/.hermes/scripts/project-curation-tournament.py"],
        "specifications": {
            "research": "Inventory direct ~/builds/* folders with .built markers and <=1 local git commit; exclude user-built/Ussyverse/multi-commit repos.",
            "tournament": "Champion/judge local-only curation tournament deciding develop, preserve, archive, or needs_manual_review.",
            "build": "No builds; write local curation artifacts, validation.json, and ledger rows only.",
            "safety": "Hard ban git push/fetch/pull, gh, GitHub Actions, repo creation, and project source mutations.",
        },
    },
]


def _autonomous_development_home() -> Path:
    return HERMES_HOME / "autonomous-development"


def _autonomous_development_registry_path() -> Path:
    return _autonomous_development_home() / "pipelines.json"


def _autonomous_development_audit_path() -> Path:
    return _autonomous_development_home() / "audit.jsonl"


def _slugify_pipeline_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "pipeline").lower()).strip("-") or "pipeline"
    return slug[:60]


def _read_autonomous_development_audit(limit: int = 30) -> list[dict]:
    path = _autonomous_development_audit_path()
    entries: list[dict] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                entries.append(item)
    return list(reversed(entries[-limit:]))


def _append_autonomous_development_audit(action: str, details: dict, actor: str = "dashboard") -> dict:
    entry = {
        "id": f"audit_{uuid.uuid4().hex[:12]}",
        "action": action,
        "actor": actor,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "details": details,
    }
    path = _autonomous_development_audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def _normalize_pipeline_specifications(data: dict) -> dict:
    specs = data.get("specifications") if isinstance(data.get("specifications"), dict) else {}
    return {
        "research": str(data.get("research_specification") or specs.get("research") or ""),
        "tournament": str(data.get("tournament_specification") or specs.get("tournament") or ""),
        "build": str(data.get("build_specification") or specs.get("build") or ""),
        "safety": str(data.get("safety_policy") or specs.get("safety") or ""),
    }


def _load_autonomous_development_registry() -> dict:
    path = _autonomous_development_registry_path()
    existing = _self_improvement_json(path, None)
    if isinstance(existing, dict) and isinstance(existing.get("pipelines"), list):
        pipelines = [p for p in existing["pipelines"] if isinstance(p, dict)]
        by_id = {str(p.get("id")): p for p in pipelines if p.get("id")}
        changed = False
        for default in AUTONOMOUS_DEVELOPMENT_DEFAULT_PIPELINES:
            if default["id"] not in by_id:
                pipelines.append(dict(default))
                changed = True
        registry = {"version": 1, "pipelines": pipelines, "updated_at": existing.get("updated_at")}
        if changed:
            registry["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            _write_self_improvement_json(path, registry)
        return registry
    registry = {
        "version": 1,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "pipelines": [dict(pipeline) for pipeline in AUTONOMOUS_DEVELOPMENT_DEFAULT_PIPELINES],
    }
    _write_self_improvement_json(path, registry)
    return registry


def _save_autonomous_development_registry(registry: dict) -> None:
    registry = dict(registry or {})
    registry["version"] = registry.get("version") or 1
    registry["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _write_self_improvement_json(_autonomous_development_registry_path(), registry)


def _find_autonomous_pipeline(registry: dict, pipeline_id: str) -> Optional[dict]:
    for pipeline in registry.get("pipelines", []):
        if str(pipeline.get("id")) == str(pipeline_id):
            return pipeline
    return None


def _jobs_by_name() -> dict[str, dict]:
    return {str(job.get("name") or ""): job for job in _iter_cron_jobs(_load_cron_jobs_file())}


def _pipeline_jobs_summary(pipeline: dict, jobs_by_name: dict[str, dict]) -> dict:
    names = [str(name) for name in pipeline.get("job_names", []) if str(name)]
    linked = []
    active = 0
    missing = []
    for name in names:
        job = jobs_by_name.get(name)
        if not job:
            missing.append(name)
            continue
        enabled = _cron_job_enabled(job)
        if enabled:
            active += 1
        linked.append({
            "id": job.get("id"),
            "name": name,
            "enabled": enabled,
            "state": job.get("state") or ("scheduled" if enabled else "paused"),
            "schedule": job.get("schedule"),
            "schedule_display": job.get("schedule_display") or (job.get("schedule") or {}).get("display"),
            "script": job.get("script"),
            "skills": job.get("skills") or [],
            "last_run_at": job.get("last_run_at"),
            "next_run_at": job.get("next_run_at"),
        })
    return {"total": len(names), "linked": len(linked), "active": active, "missing": missing, "jobs": linked}


def _hydrate_autonomous_pipeline(pipeline: dict, jobs_by_name: dict[str, dict]) -> dict:
    item = dict(pipeline)
    item["specifications"] = _normalize_pipeline_specifications(item)
    item.setdefault("job_names", [])
    item.setdefault("directories", [])
    item.setdefault("activation_mode", "manual")
    item.setdefault("desired_enabled", False)
    summary = _pipeline_jobs_summary(item, jobs_by_name)
    item["jobs_summary"] = summary
    item["active"] = bool(summary["active"] > 0)
    item["missing_jobs"] = summary["missing"]
    return item


def get_autonomous_development_status() -> dict:
    registry = _load_autonomous_development_registry()
    jobs_by_name = _jobs_by_name()
    pipelines = [_hydrate_autonomous_pipeline(pipeline, jobs_by_name) for pipeline in registry.get("pipelines", [])]
    return {
        "registry_path": str(_autonomous_development_registry_path()),
        "jobs_path": str(_self_improvement_jobs_path()),
        "pipelines": pipelines,
        "count": len(pipelines),
        "active_count": len([pipeline for pipeline in pipelines if pipeline.get("active")]),
        "audit": _read_autonomous_development_audit(),
    }


def create_autonomous_development_pipeline(data: dict, actor: str = "dashboard") -> dict:
    data = data or {}
    name = str(data.get("name") or "").strip()
    if not name:
        return {"success": False, "error": "pipeline name is required"}
    registry = _load_autonomous_development_registry()
    existing_ids = {str(p.get("id")) for p in registry.get("pipelines", [])}
    pipeline_id = str(data.get("id") or "").strip() or f"pipeline_{uuid.uuid4().hex[:10]}"
    if pipeline_id in existing_ids:
        pipeline_id = f"pipeline_{uuid.uuid4().hex[:10]}"
    pipeline = {
        "id": pipeline_id,
        "name": name,
        "description": str(data.get("description") or ""),
        "kind": str(data.get("kind") or "custom"),
        "activation_mode": "manual",
        "desired_enabled": bool(data.get("enabled", False)),
        "schedule": str(data.get("schedule") or ""),
        "job_names": [str(x).strip() for x in data.get("job_names", []) if str(x).strip()],
        "directories": [str(x).strip() for x in data.get("directories", []) if str(x).strip()],
        "specifications": _normalize_pipeline_specifications(data),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    registry.setdefault("pipelines", []).append(pipeline)
    _save_autonomous_development_registry(registry)
    audit = _append_autonomous_development_audit("pipeline_created", {"pipeline_id": pipeline_id}, actor=actor)
    return {"success": True, "pipeline": _hydrate_autonomous_pipeline(pipeline, _jobs_by_name()), "audit": audit}


def update_autonomous_development_pipeline(pipeline_id: str, data: dict, actor: str = "dashboard") -> dict:
    registry = _load_autonomous_development_registry()
    pipeline = _find_autonomous_pipeline(registry, pipeline_id)
    if not pipeline:
        return {"success": False, "error": "pipeline not found"}
    for field in ("name", "description", "kind", "schedule"):
        if field in data:
            pipeline[field] = str(data.get(field) or "")
    if "enabled" in data:
        pipeline["desired_enabled"] = bool(data.get("enabled"))
    if "desired_enabled" in data:
        pipeline["desired_enabled"] = bool(data.get("desired_enabled"))
    if "job_names" in data and isinstance(data.get("job_names"), list):
        pipeline["job_names"] = [str(x).strip() for x in data.get("job_names", []) if str(x).strip()]
    if "directories" in data and isinstance(data.get("directories"), list):
        pipeline["directories"] = [str(x).strip() for x in data.get("directories", []) if str(x).strip()]
    specs = pipeline.get("specifications") if isinstance(pipeline.get("specifications"), dict) else {}
    merged = dict(specs)
    incoming_specs = data.get("specifications") if isinstance(data.get("specifications"), dict) else {}
    for key in ("research", "tournament", "build", "safety"):
        if key in incoming_specs:
            merged[key] = str(incoming_specs.get(key) or "")
    flat_fields = {
        "research_specification": "research",
        "tournament_specification": "tournament",
        "build_specification": "build",
        "safety_policy": "safety",
    }
    for flat, key in flat_fields.items():
        if flat in data:
            merged[key] = str(data.get(flat) or "")
    for key in ("research", "tournament", "build", "safety"):
        merged.setdefault(key, "")
    pipeline["specifications"] = merged
    pipeline["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _save_autonomous_development_registry(registry)
    audit = _append_autonomous_development_audit("pipeline_updated", {"pipeline_id": pipeline_id}, actor=actor)
    return {"success": True, "pipeline": _hydrate_autonomous_pipeline(pipeline, _jobs_by_name()), "audit": audit}


def _schedule_from_display(display: str):
    text = str(display or "").strip()
    match = re.search(r"(\d+)\s*(m|min|minute|minutes|h|hr|hour|hours)", text, re.I)
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2).lower()
    minutes = value * 60 if unit.startswith("h") else value
    return {"kind": "interval", "minutes": minutes, "display": f"every {minutes}m"}


def apply_autonomous_development_pipeline_control(pipeline_id: str, action: str, actor: str = "dashboard") -> dict:
    action = str(action or "").strip().lower()
    if action not in {"enable", "disable"}:
        return {"success": False, "error": f"unknown control action: {action}"}
    registry = _load_autonomous_development_registry()
    pipeline = _find_autonomous_pipeline(registry, pipeline_id)
    if not pipeline:
        return {"success": False, "error": "pipeline not found"}
    jobs_data = _load_cron_jobs_file()
    jobs = _iter_cron_jobs(jobs_data)
    names = {str(name) for name in pipeline.get("job_names", [])}
    touched = []
    for job in jobs:
        if str(job.get("name") or "") not in names:
            continue
        if action == "enable":
            job["enabled"] = True
            job["state"] = "scheduled"
            if pipeline.get("schedule"):
                job["schedule_display"] = str(pipeline.get("schedule"))
                parsed = _schedule_from_display(str(pipeline.get("schedule")))
                if parsed:
                    job["schedule"] = parsed
            job["paused_at"] = None
            job["paused_reason"] = None
        else:
            job["enabled"] = False
            job["state"] = "paused"
            job["paused_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            job["paused_reason"] = f"Disabled from Autonomous Development dashboard pipeline {pipeline_id}"
        touched.append(job.get("id") or job.get("name"))
    pipeline["desired_enabled"] = action == "enable"
    pipeline["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _save_cron_jobs_file(jobs_data)
    _save_autonomous_development_registry(registry)
    audit = _append_autonomous_development_audit(f"pipeline_{action}d", {"pipeline_id": pipeline_id, "jobs": touched}, actor=actor)
    return {"success": True, "action": action, "pipeline": _hydrate_autonomous_pipeline(pipeline, _jobs_by_name()), "touched_jobs": touched, "audit": audit}


async def get_autonomous_development_endpoint(request):
    return JSONResponse(get_autonomous_development_status())


async def create_autonomous_development_pipeline_endpoint(request):
    try:
        data = json.loads((await request.body()) or b"{}")
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    result = create_autonomous_development_pipeline(data)
    return JSONResponse(result, status_code=200 if result.get("success") else 400)


async def update_autonomous_development_pipeline_endpoint(request):
    pipeline_id = request.path_params.get("pipeline_id")
    try:
        data = json.loads((await request.body()) or b"{}")
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    result = update_autonomous_development_pipeline(pipeline_id, data)
    return JSONResponse(result, status_code=200 if result.get("success") else 404)


async def control_autonomous_development_pipeline_endpoint(request):
    pipeline_id = request.path_params.get("pipeline_id")
    try:
        data = json.loads((await request.body()) or b"{}")
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    result = apply_autonomous_development_pipeline_control(pipeline_id, data.get("action"), actor=data.get("actor") or "dashboard")
    return JSONResponse(result, status_code=200 if result.get("success") else 400)


async def get_self_improvement_endpoint(request):
    return JSONResponse(get_self_improvement_status())


async def get_self_improvement_runs_endpoint(request):
    return JSONResponse(get_self_improvement_ledger())


async def get_self_improvement_candidates_endpoint(request):
    return JSONResponse(list_self_improvement_candidates())


async def create_self_improvement_candidate_endpoint(request):
    try:
        data = json.loads((await request.body()) or b"{}")
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    result = add_self_improvement_candidate(data)
    return JSONResponse(result, status_code=201 if result["accepted"] else 400)


async def select_self_improvement_candidate_endpoint(request):
    return JSONResponse(select_self_improvement_candidate())


async def control_self_improvement_endpoint(request):
    try:
        data = json.loads((await request.body()) or b"{}")
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    result = apply_self_improvement_control(
        data.get("action"), confirm=bool(data.get("confirm")), actor=str(data.get("actor") or "dashboard")
    )
    return JSONResponse(result, status_code=200 if result.get("success") else 400)


async def get_cron_jobs(request):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{HERMES_API}/api/jobs", headers={"Authorization": f"Bearer {API_KEY}"}
            )
            return JSONResponse(resp.json())
        except Exception as e:
            return JSONResponse({"jobs": [], "error": str(e)})


async def create_cron_job(request):
    body = await request.body()
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{HERMES_API}/api/jobs",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                content=body,
            )
            return JSONResponse(resp.json(), status_code=resp.status_code)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)


async def update_cron_job(request):
    job_id = request.path_params["job_id"]
    body = await request.body()
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.patch(
                f"{HERMES_API}/api/jobs/{job_id}",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                content=body,
            )
            return JSONResponse(resp.json(), status_code=resp.status_code)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)


async def delete_cron_job(request):
    job_id = request.path_params["job_id"]
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.delete(
                f"{HERMES_API}/api/jobs/{job_id}",
                headers={"Authorization": f"Bearer {API_KEY}"},
            )
            return JSONResponse(resp.json(), status_code=resp.status_code)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)


async def pause_cron_job(request):
    job_id = request.path_params["job_id"]
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{HERMES_API}/api/jobs/{job_id}/pause",
                headers={"Authorization": f"Bearer {API_KEY}"},
            )
            return JSONResponse(resp.json(), status_code=resp.status_code)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)


async def resume_cron_job(request):
    job_id = request.path_params["job_id"]
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{HERMES_API}/api/jobs/{job_id}/resume",
                headers={"Authorization": f"Bearer {API_KEY}"},
            )
            return JSONResponse(resp.json(), status_code=resp.status_code)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)


async def run_cron_job(request):
    job_id = request.path_params["job_id"]
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{HERMES_API}/api/jobs/{job_id}/run",
                headers={"Authorization": f"Bearer {API_KEY}"},
            )
            return JSONResponse(resp.json(), status_code=resp.status_code)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)


def _extract_cron_schedule_name(session_id: str, title: Optional[str]) -> str:
    """Extract schedule name from cron session ID or title."""
    # Pattern: session_cron_<name>_<date>_<time> or cron_<name>_<date>_<time>
    match = re.match(r"(?:session_)?cron_([a-zA-Z0-9\-]+)(?:_\d{8}_\d{6})?", session_id)
    if match:
        return match.group(1)
    # Fallback: use first word of title if it looks meaningful
    if title:
        clean = str(title).strip()
        if clean and not clean.startswith("Session ") and not clean.startswith("{"):
            first = clean.split()[0] if clean.split() else clean
            if len(first) > 2:
                return first.lower()[:30]
    # Final fallback: date prefix from timestamp-based IDs
    match = re.match(r"(\d{8})_\d{6}_[a-zA-Z0-9]+", session_id)
    if match:
        return f"cron-{match.group(1)}"
    return "untitled"


def _iso_from_ts(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_next_run_simple(cron_expr: str, after: float) -> Optional[float]:
    """Minimal cron next-run calculator for common expressions."""
    if not cron_expr or not cron_expr.strip():
        return None
    parts = cron_expr.strip().split()
    if len(parts) < 5:
        return None
    minute, hour, dom, month, dow = parts[:5]
    now = datetime.datetime.fromtimestamp(after, tz=datetime.timezone.utc)
    # Start searching from the next minute
    candidate = now.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    max_iter = 366 * 24 * 60  # One year in minutes
    for _ in range(max_iter):
        # month
        if month != "*" and str(candidate.month) != month:
            candidate += datetime.timedelta(minutes=1)
            continue
        # day of month
        if dom != "*" and str(candidate.day) != dom:
            candidate += datetime.timedelta(minutes=1)
            continue
        # day of week (0=Mon in Python, but cron uses 0=Sun; keep it simple)
        if dow != "*":
            cron_dow = int(dow)
            # Python weekday: Monday=0 ... Sunday=6
            # Cron weekday: Sunday=0 ... Saturday=6
            py_dow = (candidate.weekday() + 1) % 7
            if py_dow != cron_dow:
                candidate += datetime.timedelta(minutes=1)
                continue
        # hour
        if hour != "*" and str(candidate.hour) != hour:
            candidate += datetime.timedelta(minutes=1)
            continue
        # minute
        if minute != "*" and str(candidate.minute) != minute:
            candidate += datetime.timedelta(minutes=1)
            continue
        return candidate.timestamp()
    return None


async def get_cron_schedule(request):
    db_path = HERMES_HOME / "state.db"
    if not db_path.exists():
        return JSONResponse({"schedules": []})

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Detect cron sessions by source='cron' or id prefix patterns
        rows = conn.execute(
            """
            SELECT id, title, summary, started_at, ended_at, source
            FROM sessions
            WHERE source = 'cron' OR id LIKE 'session_cron_%' OR id LIKE 'cron_%'
            ORDER BY started_at DESC
            """
        ).fetchall()

        schedules: dict[str, dict] = {}
        for row in rows:
            session_id = row["id"]
            name = _extract_cron_schedule_name(session_id, row["title"])
            if name not in schedules:
                schedules[name] = {"name": name, "runs": []}

            status = "complete" if row["ended_at"] else "running"
            duration = None
            if row["started_at"] and row["ended_at"]:
                duration = round(row["ended_at"] - row["started_at"])

            schedules[name]["runs"].append(
                {
                    "session_id": session_id,
                    "status": status,
                    "started_at": _iso_from_ts(row["started_at"]),
                    "duration_seconds": duration,
                }
            )

        result = []
        for name, data in schedules.items():
            runs = data["runs"]
            last_run = runs[0] if runs else None
            recent_runs = runs[:5]

            schedule: dict = {
                "name": name,
                "last_run": last_run,
                "recent_runs": recent_runs,
            }

            # Attempt to infer cron_expr from the most recent run's title/summary
            cron_expr = None
            if last_run:
                first_run_row = conn.execute(
                    "SELECT title, summary FROM sessions WHERE id = ?",
                    (last_run["session_id"],),
                ).fetchone()
                if first_run_row:
                    for field in (first_run_row["title"], first_run_row["summary"]):
                        if field and "*" in str(field):
                            # Heuristic: look for a 5-part cron expression
                            m = re.search(r"(\S+\s+\S+\s+\S+\s+\S+\s+\S+)", str(field))
                            if m:
                                candidate = m.group(1)
                                if candidate.count("*") >= 1 and len(candidate.split()) == 5:
                                    cron_expr = candidate
                                    break

            if cron_expr:
                schedule["cron_expr"] = cron_expr
                next_ts = _compute_next_run_simple(cron_expr, time.time())
                if next_ts:
                    schedule["next_run"] = _iso_from_ts(next_ts)

            result.append(schedule)

        conn.close()
        return JSONResponse({"schedules": result})
    except Exception as e:
        return JSONResponse({"schedules": [], "error": str(e)})


async def get_secrets(request):
    return JSONResponse({"secrets": _build_secrets_payload(get_env())})


async def set_secret(request):
    body = await request.body()
    data = json.loads(body)
    key = data.get("key")
    value = data.get("value")

    if not key:
        return JSONResponse(
            {"success": False, "error": "Key required"}, status_code=400
        )

    try:
        save_env_value(key, value)
    except Exception:
        _save_env_value_local(key, value)

    return JSONResponse(
        {"success": True, "key": key, "masked_value": _mask_secret(value)}
    )


async def delete_secret(request):
    key = request.path_params["key"]

    env = get_env()
    if key in env:
        del env[key]
        save_env(env)
        return JSONResponse({"success": True})

    return JSONResponse({"success": False, "error": "Key not found"}, status_code=404)


# ---------------------------------------------------------------------------
# Graph API
# ---------------------------------------------------------------------------


def _infer_file_category(path_str: str) -> str:
    """Infer a broad category from a file extension."""
    ext = Path(path_str).suffix.lower()
    cat_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".json": "config",
        ".yaml": "config",
        ".yml": "config",
        ".toml": "config",
        ".md": "docs",
        ".txt": "docs",
        ".rst": "docs",
        ".sh": "shell",
        ".bash": "shell",
        ".zsh": "shell",
        ".html": "web",
        ".css": "web",
        ".scss": "web",
        ".sql": "data",
        ".csv": "data",
        ".xml": "data",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".c": "c",
        ".cpp": "c",
        ".h": "c",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".kt": "kotlin",
        ".r": "r",
        ".jl": "julia",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".gif": "image",
        ".svg": "image",
        ".ico": "image",
    }
    return cat_map.get(ext, "other")


def _parse_skill_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from a SKILL.md file."""
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(content[3:end]) or {}
    except Exception:
        return {}


def _extract_skill_ids_from_payload(payload) -> list[str]:
    skill_ids: list[str] = []

    def _collect(value):
        if isinstance(value, str):
            if value and value not in skill_ids:
                skill_ids.append(value)
        elif isinstance(value, dict):
            for key in ("skill_id", "name", "id"):
                maybe = value.get(key)
                if isinstance(maybe, str) and maybe and maybe not in skill_ids:
                    skill_ids.append(maybe)
            for nested in value.values():
                _collect(nested)
        elif isinstance(value, list):
            for item in value:
                _collect(item)

    _collect(payload)
    return skill_ids


def _canonical_skill_id(raw_skill_id: str) -> str:
    value = str(raw_skill_id or "").strip().strip("/")
    if not value:
        return ""
    if "/" in value:
        value = value.split("/")[-1]
    if value.endswith("SKILL.md"):
        parts = Path(value).parts
        if len(parts) >= 2:
            value = parts[-2]
    return value


def _session_label(title, summary, session_id: str) -> str:
    clean_title = " ".join(str(title or "").split()).strip()
    if clean_title:
        return clean_title
    clean_summary = " ".join(str(summary or "").split()).strip()
    if clean_summary:
        return (
            clean_summary[:77].rstrip() + "..."
            if len(clean_summary) > 80
            else clean_summary
        )
    return session_id[:8]


def _get_messages_from_session_files(since_ts: Optional[float] = None) -> list[dict]:
    """Read session JSON files to get messages that aren't in the SQLite DB."""
    import os
    messages = []
    sessions_dir = HERMES_HOME / "sessions"
    if not sessions_dir.exists():
        return messages

    # Use scandir for better performance
    files_processed = 0
    max_files = 500  # Limit to prevent timeouts

    with os.scandir(sessions_dir) as it:
        for entry in it:
            if not entry.name.startswith("session_") or not entry.name.endswith(".json"):
                continue
            if files_processed >= max_files:
                break

            try:
                # Quick mtime check without full stat
                mtime = entry.stat().st_mtime
                if since_ts is not None and mtime < since_ts:
                    continue

                with open(entry.path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                session_id = data.get("id")
                if not session_id:
                    # Strip "session_" prefix from filename stem
                    stem = entry.name[:-5]  # Remove .json
                    if stem.startswith("session_"):
                        session_id = stem[8:]  # Remove "session_" prefix
                    else:
                        session_id = stem

                for msg in data.get("messages", []):
                    msg["session_id"] = session_id
                    # Convert timestamp to float if it's a string
                    ts = msg.get("timestamp")
                    if isinstance(ts, str):
                        try:
                            msg["timestamp"] = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                        except:
                            msg["timestamp"] = mtime
                    elif ts is None:
                        msg["timestamp"] = mtime
                    messages.append(msg)

                files_processed += 1
            except Exception:
                continue

    return messages


async def get_graph_data(request):
    """
    Return nodes and edges for a relationship graph visualization.

    Node types: session, file, tool, model, skill
    Edge types: accessed, used_tool, used_model, delegated, relates_to

    Query params:
      depth=full|shallow  (default: full)
        shallow = sessions + models only
        full    = all node types including files, tools, skills
    """
    depth = request.query_params.get("depth", "full")

    # Time-scoping: hours=0.5 (30m), 1, 3, 6, 12, 24, 168 (7d), 720 (30d), 0|all (no filter)
    hours_str = request.query_params.get("hours", "24")
    if hours_str == "all" or hours_str == "0":
        since_ts = None
    else:
        since_ts = time.time() - (float(hours_str) * 3600)

    nodes: list[dict] = []
    edges: list[dict] = []
    node_ids: set[str] = set()

    def _add_node(nid: str, label: str, ntype: str, **extra) -> None:
        if nid in node_ids:
            return
        node_ids.add(nid)
        node = {"id": nid, "label": label, "type": ntype}
        node.update(extra)
        nodes.append(node)

    db_path = HERMES_HOME / "state.db"
    if not db_path.exists():
        return JSONResponse(
            {
                "nodes": nodes,
                "edges": edges,
                "node_count": 0,
                "edge_count": 0,
            }
        )

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        _ensure_sessions_summary_column(conn)

        if not _sessions_table_exists(conn):
            conn.close()
            return JSONResponse(
                {
                    "nodes": nodes,
                    "edges": edges,
                    "node_count": 0,
                    "edge_count": 0,
                }
            )

        # --- 1. Session nodes + model nodes + delegation edges ---
        if since_ts is not None:
            sessions = conn.execute(
                """SELECT id, title, source, model, parent_session_id,
                          summary, started_at, ended_at, message_count, tool_call_count,
                          input_tokens, output_tokens, estimated_cost_usd
                   FROM sessions WHERE started_at >= ?
                   ORDER BY started_at DESC""",
                (since_ts,),
            ).fetchall()
        else:
            sessions = conn.execute(
                """SELECT id, title, source, model, parent_session_id,
                          summary, started_at, ended_at, message_count, tool_call_count,
                          input_tokens, output_tokens, estimated_cost_usd
                   FROM sessions ORDER BY started_at DESC"""
            ).fetchall()

        model_counts: dict[str, int] = {}
        session_skill_edges: set[tuple[str, str]] = set()

        for s in sessions:
            sid = f"session:{s['id']}"
            _add_node(
                sid,
                _session_label(s["title"], s["summary"], s["id"]),
                "session",
                session_id=s["id"],
                source=s["source"],
                model=s["model"],
                summary=s["summary"],
                started_at=s["started_at"],
                ended_at=s["ended_at"],
                message_count=s["message_count"],
                tool_call_count=s["tool_call_count"],
                input_tokens=s["input_tokens"],
                output_tokens=s["output_tokens"],
                estimated_cost_usd=s["estimated_cost_usd"],
            )

            # Model edge
            if s["model"]:
                model_name = s["model"]
                model_counts[model_name] = model_counts.get(model_name, 0) + 1
                edges.append(
                    {
                        "source": sid,
                        "target": f"model:{model_name}",
                        "type": "used_model",
                    }
                )

            # Delegation edge
            if s["parent_session_id"]:
                parent_sid = f"session:{s['parent_session_id']}"
                edges.append(
                    {
                        "source": parent_sid,
                        "target": sid,
                        "type": "delegated",
                    }
                )

        # Add model nodes
        for model_name, count in model_counts.items():
            _add_node(
                f"model:{model_name}",
                model_name,
                "model",
                name=model_name,
                session_count=count,
            )

        # --- 2. Tool + file nodes (full depth only) ---
        if depth == "full":
            tool_counts: dict[str, int] = {}
            pending_skill_calls: dict[tuple[str, str], set[str]] = {}

            if since_ts is not None:
                msgs = conn.execute(
                    """SELECT session_id, role, content, tool_call_id, tool_calls, tool_name, timestamp, id
                       FROM messages
                       WHERE timestamp >= ?
                       ORDER BY timestamp, id""",
                    (since_ts,),
                ).fetchall()
            else:
                msgs = conn.execute(
                    """SELECT session_id, role, content, tool_call_id, tool_calls, tool_name, timestamp, id
                       FROM messages
                       ORDER BY timestamp, id"""
                ).fetchall()

            # Also get messages from session JSON files (not yet flushed to DB)
            session_file_msgs = _get_messages_from_session_files(since_ts)
            import sys
            print(f"[graph-debug] Loaded {len(session_file_msgs)} messages from session files", file=sys.stderr)
            # Convert session file msgs to same format as DB rows
            for msg in session_file_msgs:
                msgs.append({
                    "session_id": msg.get("session_id", ""),
                    "role": msg.get("role", ""),
                    "content": msg.get("content", ""),
                    "tool_call_id": msg.get("tool_call_id", ""),
                    "tool_calls": json.dumps(msg.get("tool_calls")) if msg.get("tool_calls") else None,
                    "tool_name": msg.get("tool_name", ""),
                    "timestamp": msg.get("timestamp", 0),
                    "id": msg.get("id", ""),
                })

            # Also get messages from session JSON files (not yet flushed to DB)
            session_file_msgs = _get_messages_from_session_files(since_ts)
            import sys
            print(f"[graph-debug] Loaded {len(session_file_msgs)} messages from session files", file=sys.stderr)
            # Convert session file msgs to same format as DB rows
            for msg in session_file_msgs:
                msgs.append({
                    "session_id": msg.get("session_id", ""),
                    "role": msg.get("role", ""),
                    "content": msg.get("content", ""),
                    "tool_call_id": msg.get("tool_call_id", ""),
                    "tool_calls": json.dumps(msg.get("tool_calls")) if msg.get("tool_calls") else None,
                    "tool_name": msg.get("tool_name", ""),
                    "timestamp": msg.get("timestamp", 0),
                    "id": msg.get("id", ""),
                })

            for msg in msgs:
                session_id = msg["session_id"]
                sid = f"session:{session_id}"
                tc_data = _safe_json_loads(msg["tool_calls"])
                if isinstance(tc_data, list):
                    for tc in tc_data:
                        if not isinstance(tc, dict):
                            continue
                        func = tc.get("function", {})
                        tool_name = func.get("name", "")
                        if not tool_name:
                            continue

                        tool_id = f"tool:{tool_name}"
                        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

                        edges.append(
                            {
                                "source": sid,
                                "target": tool_id,
                                "type": "used_tool",
                            }
                        )

                        args_str = func.get("arguments", "")
                        args_data = _safe_json_loads(args_str)
                        if args_data:
                            file_paths = _collect_paths_from_payload(args_data)
                            for fp in file_paths:
                                file_id = f"file:{fp}"
                                _add_node(
                                    file_id,
                                    Path(fp).name,
                                    "file",
                                    path=fp,
                                    basename=Path(fp).name,
                                    category=_infer_file_category(fp),
                                )
                                edges.append(
                                    {
                                        "source": sid,
                                        "target": file_id,
                                        "type": "accessed",
                                    }
                                )

                        if tool_name == "skill_manage":
                            skill_ids = (
                                set(_extract_skill_ids_from_payload(args_data))
                                if args_data
                                else set()
                            )
                            pending_skill_calls[
                                (session_id, str(tc.get("id") or ""))
                            ] = skill_ids

                if str(msg["role"] or "") == "tool":
                    # Extract file paths from tool result content
                    parsed_result = _safe_json_loads(msg["content"] or "")
                    if parsed_result:
                        result_paths = _collect_paths_from_payload(parsed_result)
                        for fp in result_paths:
                            file_id = f"file:{fp}"
                            _add_node(
                                file_id,
                                Path(fp).name,
                                "file",
                                path=fp,
                                basename=Path(fp).name,
                                category=_infer_file_category(fp),
                            )
                            edges.append(
                                {
                                    "source": sid,
                                    "target": file_id,
                                    "type": "accessed",
                                }
                            )

                    key = (session_id, str(msg["tool_call_id"] or ""))
                    skill_ids = pending_skill_calls.get(key)
                    if skill_ids is not None:
                        for skill_id in _extract_skill_ids_from_payload(parsed_result):
                            skill_ids.add(skill_id)
                        for skill_id in skill_ids:
                            session_skill_edges.add((session_id, skill_id))

            # Add tool nodes (after counting)
            for tool_name, count in tool_counts.items():
                _add_node(
                    f"tool:{tool_name}",
                    tool_name,
                    "tool",
                    name=tool_name,
                    usage_count=count,
                )

        conn.close()

        # --- 3. Skill nodes + relates_to edges (full depth only) ---
        if depth == "full":
            skills_dir = HERMES_HOME / "skills"
            config = get_config()
            disabled_skills = set(config.get("skills", {}).get("disabled", []))

            known_skill_ids: set[str] = set()
            if skills_dir.exists():
                for category_dir in sorted(skills_dir.iterdir()):
                    if not category_dir.is_dir() or category_dir.name.startswith("."):
                        continue
                    for skill_dir in sorted(category_dir.iterdir()):
                        if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                            continue

                        skill_id_str = skill_dir.name
                        known_skill_ids.add(skill_id_str)
                        skill_md = skill_dir / "SKILL.md"
                        fm = {}
                        if skill_md.exists():
                            try:
                                fm = _parse_skill_frontmatter(skill_md.read_text())
                            except Exception:
                                pass

                        _add_node(
                            f"skill:{skill_id_str}",
                            fm.get("name", skill_id_str),
                            "skill",
                            name=fm.get("name", skill_id_str),
                            description=fm.get("description", ""),
                            category=category_dir.name,
                            enabled=skill_id_str not in disabled_skills,
                        )

                        # Related-skill edges
                        related = (
                            fm.get("metadata", {})
                            .get("hermes", {})
                            .get("related_skills", [])
                        )
                        if isinstance(related, list):
                            for rel in related:
                                if isinstance(rel, str) and rel:
                                    edges.append(
                                        {
                                            "source": f"skill:{skill_id_str}",
                                            "target": f"skill:{rel}",
                                            "type": "relates_to",
                                        }
                                    )

                for session_id, skill_id in sorted(session_skill_edges):
                    canonical_skill_id = _canonical_skill_id(skill_id)
                    if not canonical_skill_id:
                        continue
                    if canonical_skill_id not in known_skill_ids:
                        continue
                    edges.append(
                        {
                            "source": f"session:{session_id}",
                            "target": f"skill:{canonical_skill_id}",
                            "type": "used_skill",
                        }
                    )

    except Exception as e:
        return JSONResponse(
            {
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
                "error": str(e),
            },
            status_code=500,
        )

    # Filter out edges referencing non-existent nodes
    edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

    return JSONResponse(
        {
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }
    )


async def interrupt_session(request):
    session_id = request.path_params["session_id"]
    try:
        body = await request.body()
        data = json.loads(body) if body else {}
    except Exception:
        data = {}

    action = data.get("action", "")
    if action != "pause":
        return JSONResponse(
            {"status": "invalid_action", "session_id": session_id}, status_code=400
        )

    # Check if session has an active run in ACTIVE_RUNS
    has_active_run = False
    for state in ACTIVE_RUNS.values():
        if state.get("session_id") == session_id and not state.get("done"):
            has_active_run = True
            break

    if not has_active_run:
        return JSONResponse({"status": "not_running", "session_id": session_id})

    set_interrupt_flag(session_id, True)
    for state in ACTIVE_RUNS.values():
        if state.get("session_id") != session_id or state.get("done"):
            continue
        task = state.get("task")
        if task is not None and not task.done():
            task.cancel()
        state["done"] = True
        state["events"].append(
            {
                "data": json.dumps(
                    {
                        "type": "content",
                        "content": "\n\nInterrupted by user.",
                    }
                )
            }
        )
        state["events"].append({"data": "[DONE]"})
    return JSONResponse({"status": "interrupt_queued", "session_id": session_id})


async def session_stream(request):
    session_id = request.path_params["session_id"]
    db_path = HERMES_HOME / "state.db"

    if not db_path.exists():
        return JSONResponse({"error": "No sessions database"}, status_code=404)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    session_row = conn.execute(
        "SELECT id, ended_at FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    conn.close()

    if not session_row:
        return JSONResponse({"error": "Session not found"}, status_code=404)

    active_run = None
    for state in ACTIVE_RUNS.values():
        if state.get("session_id") == session_id and not state.get("done"):
            active_run = state
            break

    async def generate():
        if active_run:
            sent = 0
            while True:
                while sent < len(active_run["events"]):
                    event = active_run["events"][sent]
                    sent += 1
                    yield event
                    if event.get("data") == "[DONE]":
                        return
                if active_run.get("done"):
                    if sent >= len(active_run["events"]):
                        yield {"data": "[DONE]"}
                    return
                await asyncio.sleep(0.1)
        else:
            status = "complete" if session_row["ended_at"] else "unknown"
            yield {
                "data": json.dumps(
                    {
                        "type": "run_state",
                        "session_id": session_id,
                        "status": status,
                    }
                )
            }
            yield {"data": "[DONE]"}

    return EventSourceResponse(
        generate(),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",
        },
    )


def _message_board_db_path() -> Path:
    return HERMES_HOME / "dashboard_message_board.sqlite3"


def _message_board_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _message_board_connection() -> sqlite3.Connection:
    db_path = _message_board_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS message_board_posts (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS message_board_messages (
            id TEXT PRIMARY KEY,
            post_id TEXT NOT NULL REFERENCES message_board_posts(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            author TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return conn


def _message_board_row_to_message(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "post_id": row["post_id"],
        "role": row["role"],
        "author": row["author"],
        "content": row["content"],
        "created_at": row["created_at"],
    }


def _load_message_board_post(conn: sqlite3.Connection, post_id: str) -> Optional[dict]:
    post_row = conn.execute(
        """
        SELECT id, title, author, status, created_at, updated_at
        FROM message_board_posts
        WHERE id = ?
        """,
        (post_id,),
    ).fetchone()
    if not post_row:
        return None
    message_rows = conn.execute(
        """
        SELECT id, post_id, role, author, content, created_at
        FROM message_board_messages
        WHERE post_id = ?
        ORDER BY created_at, rowid
        """,
        (post_id,),
    ).fetchall()
    post = dict(post_row)
    post["messages"] = [_message_board_row_to_message(row) for row in message_rows]
    post["reply_count"] = sum(1 for msg in post["messages"] if msg["role"] == "assistant")
    return post


def get_message_board_post(post_id: str) -> Optional[dict]:
    with _message_board_connection() as conn:
        return _load_message_board_post(conn, post_id)


def list_message_board_posts(limit: int = 50) -> list[dict]:
    with _message_board_connection() as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.title, p.author, p.status, p.created_at, p.updated_at,
                   COUNT(CASE WHEN m.role = 'assistant' THEN 1 END) AS reply_count,
                   (
                       SELECT mm.content
                       FROM message_board_messages mm
                       WHERE mm.post_id = p.id AND mm.role = 'assistant'
                       ORDER BY mm.created_at DESC, mm.rowid DESC
                       LIMIT 1
                   ) AS last_reply_preview
            FROM message_board_posts p
            LEFT JOIN message_board_messages m ON m.post_id = p.id
            GROUP BY p.id
            ORDER BY p.updated_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        posts = []
        for row in rows:
            item = dict(row)
            preview = item.get("last_reply_preview") or ""
            item["last_reply_preview"] = preview[:240]
            item["reply_count"] = int(item.get("reply_count") or 0)
            posts.append(item)
        return posts


def add_message_board_reply(post_id: str, content: str, author: str = "Hermes", role: str = "assistant") -> dict:
    content = str(content or "").strip()
    if not content:
        raise ValueError("Reply content is required")
    if role not in {"assistant", "user"}:
        raise ValueError("Reply role must be assistant or user")
    now = _message_board_now()
    with _message_board_connection() as conn:
        if not _load_message_board_post(conn, post_id):
            raise KeyError(post_id)
        conn.execute(
            """
            INSERT INTO message_board_messages (id, post_id, role, author, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"msg_{uuid.uuid4().hex}", post_id, role, author, content, now),
        )
        status = "answered" if role == "assistant" else "open"
        conn.execute(
            """
            UPDATE message_board_posts
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, now, post_id),
        )
        conn.commit()
        return _load_message_board_post(conn, post_id)


def add_message_board_user_message(post_id: str, content: str, author: str = "mojo") -> dict:
    return add_message_board_reply(post_id, content, author=author, role="user")


def create_message_board_post(
    title: str,
    body: str,
    author: str = "mojo",
    agent_reply: Optional[str] = None,
) -> dict:
    title = str(title or "").strip()
    body = str(body or "").strip()
    author = str(author or "mojo").strip() or "mojo"
    if not title:
        raise ValueError("Post title is required")
    if not body:
        raise ValueError("Post body is required")
    post_id = f"post_{uuid.uuid4().hex}"
    now = _message_board_now()
    with _message_board_connection() as conn:
        conn.execute(
            """
            INSERT INTO message_board_posts (id, title, author, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (post_id, title, author, "open", now, now),
        )
        conn.execute(
            """
            INSERT INTO message_board_messages (id, post_id, role, author, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"msg_{uuid.uuid4().hex}", post_id, "user", author, body, now),
        )
        conn.commit()
    if agent_reply:
        return add_message_board_reply(post_id, agent_reply, author="Hermes", role="assistant")
    loaded = get_message_board_post(post_id)
    if not loaded:
        raise RuntimeError("Created message board post could not be loaded")
    return loaded


def _extract_non_stream_chat_content(payload: dict) -> str:
    try:
        choices = payload.get("choices") or []
        first = choices[0] if choices else {}
        message = first.get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text") or part.get("content")
                    if text:
                        parts.append(str(text))
                elif part:
                    parts.append(str(part))
            return "".join(parts).strip()
    except Exception:
        return ""
    return ""


def _parse_json_object_content(content: str) -> dict:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Hermes chat completion JSON content must be an object")
    return parsed


async def call_dnd_hermes_json(messages: list[dict], timeout_seconds: float = 90.0) -> dict:
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=15.0, read=timeout_seconds, write=30.0, pool=15.0)
    ) as client:
        resp = await client.post(
            f"{HERMES_API}/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"model": "hermes-agent", "messages": _sanitize_chat_messages(messages), "stream": False},
        )
        resp.raise_for_status()
        content = _extract_non_stream_chat_content(resp.json())
    if not content:
        raise ValueError("Hermes chat completion returned no message content")
    return _parse_json_object_content(content)


async def generate_message_board_agent_reply(post: dict) -> str:
    thread_messages = []
    for msg in post.get("messages", []):
        role = msg.get("role")
        content = str(msg.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        thread_messages.append({"role": role, "content": content})
    messages = [
        {
            "role": "system",
            "content": (
                "You are Hermes replying inside one dashboard message-board thread. "
                "Treat this thread as its own forum conversation and use only the thread title "
                "and ordered thread messages as conversational context. Be concrete, concise, "
                "and iteration-focused. If the user asks for work, say what you did or what the "
                "next action is. Do not imply you saw unrelated dashboard chat context."
            ),
        },
        {
            "role": "user",
            "content": f"Thread title: {post.get('title', '')}\n\nContinue this forum thread.",
        },
    ]
    messages.extend(thread_messages)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=15.0, read=90.0, write=30.0, pool=15.0)) as client:
            resp = await client.post(
                f"{HERMES_API}/v1/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={"model": "hermes-agent", "messages": messages, "stream": False},
            )
            resp.raise_for_status()
            content = _extract_non_stream_chat_content(resp.json())
            if content:
                return content
    except Exception as exc:
        return f"I saw this post, but my live reply path hit the Hermes gateway error: {exc}"
    return "I saw this post. I do not have a generated reply yet, but it is saved here for iteration."


async def get_message_board_posts_endpoint(request):
    return JSONResponse({"posts": list_message_board_posts()})


async def get_message_board_post_endpoint(request, post_id: Optional[str] = None):
    if post_id is None:
        post_id = getattr(request, "path_params", {}).get("post_id")
    post = get_message_board_post(str(post_id or ""))
    if not post:
        return JSONResponse({"error": "Post not found"}, status_code=404)
    return JSONResponse(post)


async def create_message_board_post_endpoint(request):
    data = await request.json()
    try:
        post = create_message_board_post(
            title=data.get("title", ""),
            body=data.get("body", ""),
            author=data.get("author", "mojo"),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    reply = await generate_message_board_agent_reply(post)
    post = add_message_board_reply(post["id"], reply, author="Hermes", role="assistant")
    return JSONResponse(post, status_code=201)


async def create_message_board_message_endpoint(request):
    post_id = request.path_params["post_id"]
    data = await request.json()
    content = str(data.get("content") or "").strip()
    author = str(data.get("author") or "mojo").strip() or "mojo"
    ask_agent = bool(data.get("ask_agent", True))
    try:
        post = add_message_board_user_message(post_id, content, author=author)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except KeyError:
        return JSONResponse({"error": "Post not found"}, status_code=404)
    if ask_agent:
        reply = await generate_message_board_agent_reply(post)
        post = add_message_board_reply(post_id, reply, author="Hermes", role="assistant")
    return JSONResponse(post, status_code=201)


async def get_session_tokens(request):
    session_id = request.path_params["session_id"]
    db_path = HERMES_HOME / "state.db"

    if not db_path.exists():
        return JSONResponse({"error": "No sessions database"}, status_code=404)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    session_row = conn.execute(
        """
        SELECT input_tokens, output_tokens, estimated_cost_usd, model
        FROM sessions
        WHERE id = ?
        """,
        (session_id,),
    ).fetchone()

    if not session_row:
        conn.close()
        return JSONResponse({"error": "Session not found"}, status_code=404)

    session = dict(session_row)
    cursor = conn.execute(
        """
        SELECT id, role, token_count, timestamp
        FROM messages
        WHERE session_id = ? AND token_count IS NOT NULL
        ORDER BY timestamp, id
        """,
        (session_id,),
    )

    steps = []
    step_index = 0
    for row in cursor.fetchall():
        item = dict(row)
        token_count = item.get("token_count")
        if token_count is None:
            continue
        steps.append(
            {
                "step_index": step_index,
                "role": item.get("role") or "unknown",
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": int(token_count),
                "model": session.get("model"),
            }
        )
        step_index += 1

    conn.close()

    input_tokens = session.get("input_tokens")
    output_tokens = session.get("output_tokens")
    estimated_cost_usd = session.get("estimated_cost_usd")

    has_step_data = bool(steps)
    has_session_totals = (
        input_tokens is not None
        and output_tokens is not None
        and (input_tokens > 0 or output_tokens > 0 or has_step_data)
    )

    if has_session_totals:
        input_tokens = int(input_tokens)
        output_tokens = int(output_tokens)
        total_tokens = input_tokens + output_tokens
    elif has_step_data:
        input_tokens = None
        output_tokens = None
        total_tokens = sum((s["total_tokens"] or 0) for s in steps)
    else:
        input_tokens = None
        output_tokens = None
        total_tokens = None

    if estimated_cost_usd is None and total_tokens is not None:
        rates = MODEL_COST_TABLE.get("default")
        est_input = (input_tokens or 0) * (rates["input"] / 1_000_000)
        est_output = (output_tokens or 0) * (rates["output"] / 1_000_000)
        estimated_cost_usd = round(est_input + est_output, 6)

    return JSONResponse(
        {
            "session_id": session_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": estimated_cost_usd,
            "steps": steps,
        }
    )


DND_CONTROLLER_TYPES = {"human", "subagent"}
DND_CHARACTER_KINDS = {"pc", "npc", "monster", "companion"}
DND_WORLD_ENTITY_TYPES = {"location", "faction", "npc", "quest", "encounter", "item", "lore", "deity", "settlement"}
DND_SCHEMA_REGISTRY = {
    "dnd.character_creation.v1": {
        "required": ["name"],
        "fields": ["name", "kind", "ancestry", "class_name", "background", "level", "ability_scores", "equipment", "spells", "personality", "backstory", "goals"],
    },
    "dnd.world_generation.v1": {
        "required": ["world"],
        "fields": ["world", "locations", "npcs", "factions", "quests", "encounters", "starting_scene"],
    },
    "dnd.dm_resolution.v1": {"mechanics": ["roll", "scene_update", "world_entity_update", "quest_update", "npc_update"]},
}
DND_TURN_LOCKS: dict[str, asyncio.Lock] = {}
DND_AUTO_TURN_JOBS: dict[str, dict] = {}
DND_ACTIVE_AUTO_TURN_JOB_BY_CAMPAIGN: dict[str, str] = {}
DND_AUTO_TURN_JOB_TTL_SECONDS = 1800


def _dnd_turn_lock(campaign_id: str) -> asyncio.Lock:
    lock = DND_TURN_LOCKS.get(str(campaign_id))
    if lock is None:
        lock = asyncio.Lock()
        DND_TURN_LOCKS[str(campaign_id)] = lock
    return lock


def _dnd_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _dnd_db_path() -> Path:
    return HERMES_HOME / "dnd" / "campaigns.sqlite3"


class _DndClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def _dnd_connect() -> sqlite3.Connection:
    db_path = _dnd_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), factory=_DndClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _init_dnd_db(conn)
    return conn


def _init_dnd_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS campaigns (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            turn_number INTEGER NOT NULL DEFAULT 1,
            current_scene TEXT NOT NULL DEFAULT '{}',
            world_state TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS players (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL,
            name TEXT NOT NULL,
            controller_type TEXT NOT NULL CHECK(controller_type IN ('human', 'subagent')),
            agent_prompt TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS characters (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL,
            player_id TEXT,
            name TEXT NOT NULL,
            character_sheet TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS turns (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL,
            turn_number INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS player_actions (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL,
            turn_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            action_text TEXT NOT NULL,
            action_source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
            FOREIGN KEY(turn_id) REFERENCES turns(id) ON DELETE CASCADE,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL,
            turn_id TEXT,
            event_type TEXT NOT NULL,
            body TEXT NOT NULL,
            actor TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}',
            sequence_index INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
            FOREIGN KEY(turn_id) REFERENCES turns(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS world_entities (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            name TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            tags_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS dnd_jobs (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL,
            input_json TEXT NOT NULL DEFAULT '{}',
            progress_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT NOT NULL DEFAULT '{}',
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
        );
        """
    )
    _dnd_ensure_columns(
        conn,
        "campaigns",
        {
            "current_scene": "TEXT NOT NULL DEFAULT '{}'",
            "world_state": "TEXT NOT NULL DEFAULT '{}'",
            "world_metadata": "TEXT NOT NULL DEFAULT '{}'",
        },
    )
    _dnd_ensure_columns(
        conn,
        "characters",
        {
            "kind": "TEXT NOT NULL DEFAULT 'pc'",
            "status": "TEXT NOT NULL DEFAULT 'active'",
            "updated_at": "TEXT",
        },
    )
    _dnd_ensure_columns(
        conn,
        "events",
        {
            "actor": "TEXT",
            "payload_json": "TEXT NOT NULL DEFAULT '{}'",
            "sequence_index": "INTEGER NOT NULL DEFAULT 0",
        },
    )
    conn.commit()


def _dnd_ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _dnd_row_to_dict(row) -> dict | None:
    if row is None:
        return None
    item = dict(row)
    if "character_sheet" in item:
        try:
            item["character_sheet"] = json.loads(item.get("character_sheet") or "{}")
        except Exception:
            item["character_sheet"] = {}
    if "current_scene" in item:
        raw_scene = item.get("current_scene") or "{}"
        try:
            item["current_scene"] = json.loads(raw_scene) if isinstance(raw_scene, str) else raw_scene
        except Exception:
            item["current_scene"] = {"summary": str(raw_scene)}
    if "world_state" in item:
        try:
            item["world_state"] = json.loads(item.get("world_state") or "{}")
        except Exception:
            item["world_state"] = {}
    if "world_metadata" in item:
        try:
            item["world_metadata"] = json.loads(item.get("world_metadata") or "{}")
        except Exception:
            item["world_metadata"] = {}
    for raw_key, public_key, default in (
        ("tags_json", "tags", []),
        ("metadata_json", "metadata", {}),
        ("input_json", "input", {}),
        ("progress_json", "progress", {}),
        ("result_json", "result", {}),
    ):
        if raw_key in item:
            try:
                item[public_key] = json.loads(item.get(raw_key) or json.dumps(default))
            except Exception:
                item[public_key] = default
            item.pop(raw_key, None)
    if "payload_json" in item:
        try:
            item["payload"] = json.loads(item.get("payload_json") or "{}")
        except Exception:
            item["payload"] = {}
        item.pop("payload_json", None)
    return item


def _dnd_rows_to_dicts(rows) -> list[dict]:
    return [_dnd_row_to_dict(row) for row in rows]


def create_dnd_campaign(name: str, description: str = "", world_metadata: dict | None = None) -> dict:
    name = str(name or "").strip()
    if not name:
        raise ValueError("Campaign name is required")
    if world_metadata is not None and not isinstance(world_metadata, dict):
        raise ValueError("world_metadata must be an object")
    world_metadata = dict(world_metadata or {})
    campaign_id = uuid.uuid4().hex
    now = _dnd_now()
    scene_summary = str(description or "").strip() or "The campaign is ready for the first scene."
    tone = str(world_metadata.get("tone") or "").strip()
    current_scene = {
        "summary": scene_summary,
        "location": "",
        "mood": tone,
        "visible_threats": [],
        "open_questions": [],
        "updated_at": now,
    }
    with _dnd_connect() as conn:
        conn.execute(
            "INSERT INTO campaigns (id, name, description, status, turn_number, current_scene, world_state, world_metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (campaign_id, name, str(description or ""), "active", 1, json.dumps(current_scene, sort_keys=True), "{}", json.dumps(world_metadata, sort_keys=True), now, now),
        )
        conn.commit()
    return get_dnd_campaign(campaign_id)


def list_dnd_campaigns() -> list[dict]:
    with _dnd_connect() as conn:
        rows = conn.execute(
            """
            SELECT campaigns.*,
                   (SELECT COUNT(*) FROM players WHERE players.campaign_id = campaigns.id) AS player_count
            FROM campaigns
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
    return _dnd_rows_to_dicts(rows)


def get_dnd_campaign(campaign_id: str) -> dict | None:
    with _dnd_connect() as conn:
        row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (str(campaign_id),)).fetchone()
    return _dnd_row_to_dict(row)


def create_dnd_player(campaign_id: str, name: str, controller_type: str, agent_prompt: str | None = None) -> dict:
    if not get_dnd_campaign(campaign_id):
        raise KeyError("Campaign not found")
    name = str(name or "").strip()
    controller_type = str(controller_type or "").strip().lower()
    if not name:
        raise ValueError("Player name is required")
    if controller_type not in DND_CONTROLLER_TYPES:
        raise ValueError("controller_type must be 'human' or 'subagent'")
    player_id = uuid.uuid4().hex
    now = _dnd_now()
    with _dnd_connect() as conn:
        conn.execute(
            "INSERT INTO players (id, campaign_id, name, controller_type, agent_prompt, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (player_id, str(campaign_id), name, controller_type, agent_prompt if agent_prompt is not None else None, now),
        )
        conn.commit()
    return _get_dnd_player(player_id)


def _get_dnd_player(player_id: str) -> dict | None:
    with _dnd_connect() as conn:
        row = conn.execute("SELECT * FROM players WHERE id = ?", (str(player_id),)).fetchone()
    return _dnd_row_to_dict(row)


def list_dnd_players(campaign_id: str) -> list[dict]:
    if not get_dnd_campaign(campaign_id):
        raise KeyError("Campaign not found")
    with _dnd_connect() as conn:
        rows = conn.execute(
            "SELECT * FROM players WHERE campaign_id = ? ORDER BY created_at, id",
            (str(campaign_id),),
        ).fetchall()
    return _dnd_rows_to_dicts(rows)


def create_dnd_character(campaign_id: str, player_id: str | None, name: str, character_sheet: dict | None = None) -> dict:
    if not get_dnd_campaign(campaign_id):
        raise KeyError("Campaign not found")
    player_id = str(player_id or "").strip() or None
    if player_id:
        player = _get_dnd_player(player_id)
        if not player or str(player.get("campaign_id")) != str(campaign_id):
            raise KeyError("Player not found")
    name = str(name or "").strip()
    if not name:
        raise ValueError("Character name is required")
    character_id = uuid.uuid4().hex
    now = _dnd_now()
    with _dnd_connect() as conn:
        sheet = dict(character_sheet or {})
        kind = str(sheet.get("kind") or "pc").lower()
        if kind not in DND_CHARACTER_KINDS:
            kind = "pc"
        conn.execute(
            "INSERT INTO characters (id, campaign_id, player_id, name, character_sheet, kind, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (character_id, str(campaign_id), player_id, name, json.dumps(sheet, sort_keys=True), kind, str(sheet.get("status") or "active"), now, now),
        )
        conn.commit()
    with _dnd_connect() as conn:
        row = conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
    return _dnd_row_to_dict(row)


def list_dnd_characters(campaign_id: str) -> list[dict]:
    if not get_dnd_campaign(campaign_id):
        raise KeyError("Campaign not found")
    with _dnd_connect() as conn:
        rows = conn.execute(
            "SELECT * FROM characters WHERE campaign_id = ? ORDER BY created_at, id",
            (str(campaign_id),),
        ).fetchall()
    return _dnd_rows_to_dicts(rows)


def update_dnd_scene(campaign_id: str, current_scene) -> dict:
    campaign = get_dnd_campaign(campaign_id)
    if not campaign:
        raise KeyError("Campaign not found")
    scene_payload = _coerce_dnd_scene_payload(current_scene)
    now = scene_payload["updated_at"]
    with _dnd_connect() as conn:
        conn.execute(
            "UPDATE campaigns SET current_scene = ?, updated_at = ? WHERE id = ?",
            (json.dumps(scene_payload, sort_keys=True), now, str(campaign_id)),
        )
        conn.commit()
    append_dnd_event(campaign_id, "scene_update", scene_payload.get("summary", "Scene updated."), actor="DM", payload=scene_payload)
    return get_dnd_campaign(campaign_id)


def _coerce_dnd_scene_payload(current_scene) -> dict:
    now = _dnd_now()
    if isinstance(current_scene, str):
        scene_payload = {"summary": current_scene.strip(), "updated_at": now}
    elif isinstance(current_scene, dict):
        scene_payload = dict(current_scene)
        scene_payload.setdefault("summary", "")
        scene_payload["updated_at"] = now
        for key in ("visible_threats", "open_questions"):
            if key in scene_payload and not isinstance(scene_payload[key], list):
                raise ValueError(f"current_scene.{key} must be a list")
    else:
        raise ValueError("current_scene must be an object or string")
    return scene_payload


def set_dnd_scene_state(campaign_id: str, current_scene) -> dict:
    if not get_dnd_campaign(campaign_id):
        raise KeyError("Campaign not found")
    scene_payload = _coerce_dnd_scene_payload(current_scene)
    now = scene_payload["updated_at"]
    with _dnd_connect() as conn:
        conn.execute(
            "UPDATE campaigns SET current_scene = ?, updated_at = ? WHERE id = ?",
            (json.dumps(scene_payload, sort_keys=True), now, str(campaign_id)),
        )
        conn.commit()
    return scene_payload


def append_dnd_event(
    campaign_id: str,
    event_type: str,
    body: str,
    turn_id: str | None = None,
    actor: str | None = None,
    payload: dict | None = None,
    sequence_index: int | None = None,
) -> dict:
    if not get_dnd_campaign(campaign_id):
        raise KeyError("Campaign not found")
    event_id = uuid.uuid4().hex
    now = _dnd_now()
    with _dnd_connect() as conn:
        if sequence_index is None:
            row = conn.execute(
                "SELECT COALESCE(MAX(sequence_index), -1) + 1 AS next_sequence FROM events WHERE campaign_id = ? AND (turn_id IS ? OR turn_id = ?)",
                (str(campaign_id), turn_id, turn_id),
            ).fetchone()
            sequence_index = int(row["next_sequence"] if row else 0)
        conn.execute(
            "INSERT INTO events (id, campaign_id, turn_id, event_type, body, actor, payload_json, sequence_index, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                str(campaign_id),
                turn_id,
                str(event_type or "event"),
                str(body or ""),
                actor if actor is not None else None,
                json.dumps(payload or {}, sort_keys=True),
                int(sequence_index or 0),
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return _dnd_row_to_dict(row)


def roll_and_record_dnd_dice(
    campaign_id: str,
    expression: str,
    label: str = "",
    actor: str = "",
    seed: str | int | None = None,
    turn_id: str | None = None,
) -> dict:
    if not get_dnd_campaign(campaign_id):
        raise KeyError("Campaign not found")
    roll = roll_dnd_dice(expression, seed=seed)
    roll.update({"label": str(label or ""), "actor": str(actor or "")})
    label_text = roll["label"] or "Dice roll"
    actor_text = f"{roll['actor']} " if roll["actor"] else ""
    modifier_text = f" {roll['modifier']:+d}" if int(roll.get("modifier") or 0) else ""
    body = f"{actor_text}{label_text}: {roll['expression']} = {roll['total']} ({roll['rolls']}{modifier_text})"
    event = append_dnd_event(campaign_id, "dice_roll", body, turn_id=turn_id, actor=roll["actor"] or None, payload=roll)
    return {"roll": roll, "event": event}


def _validate_dnd_human_actions(players: list[dict], human_actions: dict) -> None:
    human_ids = {player["id"] for player in players if player.get("controller_type") == "human"}
    known_ids = {player["id"] for player in players}
    for player_id, action in human_actions.items():
        if player_id not in known_ids:
            raise ValueError("human_actions contains an unknown player ID")
        if player_id not in human_ids:
            raise ValueError("human_actions may only contain human player IDs")
        if not isinstance(action, str):
            raise ValueError("human action values must be strings")

def roll_dnd_dice(expression: str, seed: str | int | None = None) -> dict:
    import random

    match = re.fullmatch(r"\s*(\d+)d(\d+)(?:\s*([+-])\s*(\d+))?\s*", str(expression or ""), re.IGNORECASE)
    if not match:
        raise ValueError("Dice expression must look like 1d20+3 or 2d6")
    count = int(match.group(1))
    sides = int(match.group(2))
    sign = match.group(3)
    mod_value = int(match.group(4) or 0)
    modifier = -mod_value if sign == "-" else mod_value
    if count < 1 or count > 100 or sides < 2 or sides > 1000:
        raise ValueError("Dice expression is out of supported range")
    rng = random.Random(f"{expression}:{seed}") if seed is not None else random.Random()
    rolls = [rng.randint(1, sides) for _ in range(count)]
    return {"expression": expression, "rolls": rolls, "modifier": modifier, "total": sum(rolls) + modifier}


def _fallback_subagent_action(player: dict, turn_number: int) -> str:
    prompt = (player.get("agent_prompt") or "").strip()
    focus = f" following prompt: {prompt}" if prompt else ""
    return f"{player.get('name', 'Subagent')} takes a cautious, useful action on turn {turn_number}{focus}."


async def _emit_dnd_turn_progress(progress, event_type: str, **payload) -> None:
    if progress is None:
        return
    event = {"type": event_type, "at": _dnd_now(), **payload}
    result = progress(event)
    if inspect.isawaitable(result):
        await result


def _serialize_dnd_auto_turn_job(job: dict) -> dict:
    return {
        "id": job["id"],
        "campaign_id": job["campaign_id"],
        "status": job["status"],
        "turn_number": job.get("turn_number"),
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "progress": dict(job.get("progress") or {}),
        "events": [dict(event) for event in job.get("events") or []],
        "poll_url": f"/api/dnd/campaigns/{job['campaign_id']}/turns/auto/jobs/{job['id']}",
        **({"result": job.get("result")} if job.get("status") == "completed" else {}),
        **({"error": job.get("error")} if job.get("error") else {}),
    }


def _record_dnd_auto_turn_job_event(job: dict, event: dict) -> None:
    enriched = dict(event)
    enriched.setdefault("at", _dnd_now())
    enriched.setdefault("type", "progress")
    enriched["index"] = len(job.get("events") or [])
    enriched["job_id"] = job["id"]
    enriched["campaign_id"] = job["campaign_id"]
    job.setdefault("events", []).append(enriched)
    job["updated_at"] = _dnd_now()
    if enriched.get("type") == "turn_started":
        job["turn_number"] = enriched.get("turn_number")
        job["progress"] = {"phase": "collecting_actions", "percent": 15}
    elif enriched.get("type") == "subagent_status":
        status = enriched.get("status")
        if status == "thinking":
            job["progress"] = {"phase": "collecting_actions", "percent": max(int((job.get("progress") or {}).get("percent") or 0), 20)}
        elif status in {"json_received", "validated"}:
            job["progress"] = {"phase": "collecting_actions", "percent": max(int((job.get("progress") or {}).get("percent") or 0), 45)}
        elif status in {"committed", "fallback_used"}:
            job["progress"] = {"phase": "persisting_actions", "percent": max(int((job.get("progress") or {}).get("percent") or 0), 65)}
    elif enriched.get("type") == "dm_status":
        job["progress"] = {"phase": "resolving_dm", "percent": 75 if enriched.get("status") == "thinking" else 85}
    elif enriched.get("type") == "turn_committed":
        job["progress"] = {"phase": "completed", "percent": 100}


def _dnd_recent_events_chronological(campaign_id: str, limit: int = 20) -> list[dict]:
    return list(reversed(list_dnd_events(campaign_id)[:limit]))


def build_dnd_turn_context(campaign_id: str) -> dict:
    return {
        "campaign": get_dnd_campaign(campaign_id),
        "players": list_dnd_players(campaign_id),
        "characters": list_dnd_characters(campaign_id),
        "recent_events": _dnd_recent_events_chronological(campaign_id),
    }


def validate_dnd_player_action_response(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Subagent action response must be a JSON object")
    action = str(payload.get("action") or payload.get("action_text") or "").strip()
    if not action:
        raise ValueError("Subagent action JSON must include non-empty action")
    result = {
        "action": action[:2000],
        "intent": str(payload.get("intent") or "").strip()[:1000],
        "dialogue": str(payload.get("dialogue") or payload.get("speech") or "").strip()[:1000],
        "requested_roll": None,
    }
    requested_roll = payload.get("requested_roll") or payload.get("dice_request")
    if requested_roll:
        if not isinstance(requested_roll, dict):
            raise ValueError("requested_roll must be an object")
        expression = str(requested_roll.get("expression") or "").strip()
        roll_dnd_dice(expression, seed="validation")
        result["requested_roll"] = {
            "expression": expression,
            "label": str(requested_roll.get("label") or requested_roll.get("purpose") or "").strip()[:200],
        }
    return result


def validate_dnd_dm_resolution(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("DM resolution response must be a JSON object")
    narration = str(payload.get("narration") or payload.get("body") or "").strip()
    if not narration:
        raise ValueError("DM resolution must include narration")
    mechanics = payload.get("mechanics") or []
    if not isinstance(mechanics, list):
        raise ValueError("DM mechanics must be a list")
    validated: list[dict] = []
    for item in mechanics[:20]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").strip()
        if kind == "roll":
            expression = str(item.get("expression") or "").strip()
            roll_dnd_dice(expression, seed="validation")
            validated.append(
                {
                    "type": "roll",
                    "actor": str(item.get("actor") or "").strip()[:200],
                    "expression": expression,
                    "label": str(item.get("label") or item.get("purpose") or "Check").strip()[:200],
                }
            )
        elif kind == "scene_update":
            scene = item.get("current_scene") or item.get("scene")
            if not isinstance(scene, dict):
                raise ValueError("scene_update.current_scene must be an object")
            scene = dict(scene)
            scene.setdefault("summary", "")
            for key in ("visible_threats", "open_questions"):
                if key in scene and not isinstance(scene[key], list):
                    raise ValueError(f"scene_update.current_scene.{key} must be a list")
            validated.append({"type": "scene_update", "current_scene": scene})
    return {"narration": narration[:5000], "mechanics": validated}


def fallback_dnd_dm_resolution(actions: list[dict]) -> dict:
    narration = "The party advances: " + "; ".join(action["action_text"] for action in actions) if actions else "The quiet dungeon waits."
    return {"narration": narration, "mechanics": []}


def _dnd_prompt_context(context: dict, turn_number: int) -> str:
    return json.dumps(
        {
            "turn_number": turn_number,
            "campaign": context.get("campaign"),
            "players": context.get("players"),
            "characters": context.get("characters"),
            "recent_events": context.get("recent_events"),
        },
        sort_keys=True,
    )


async def generate_dnd_subagent_action(player: dict, context: dict, turn_number: int, progress=None) -> dict:
    await _emit_dnd_turn_progress(
        progress,
        "subagent_status",
        player_id=player.get("id"),
        player_name=player.get("name", ""),
        status="thinking",
        turn_number=turn_number,
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are an autonomous D&D player subagent inside Hermes. Stay in character, "
                "choose exactly one useful action for your player, never control other players, "
                "and return JSON only with keys action, intent, dialogue, and optional requested_roll."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "player": player,
                    "turn_context": json.loads(_dnd_prompt_context(context, turn_number)),
                    "required_schema": {
                        "action": "required string",
                        "intent": "optional string",
                        "dialogue": "optional in-character quote",
                        "requested_roll": {"expression": "optional dice expression", "label": "optional roll label"},
                    },
                },
                sort_keys=True,
            ),
        },
    ]
    try:
        payload = await call_dnd_hermes_json(messages)
        await _emit_dnd_turn_progress(
            progress,
            "subagent_status",
            player_id=player.get("id"),
            player_name=player.get("name", ""),
            status="json_received",
            turn_number=turn_number,
        )
        validated = validate_dnd_player_action_response(payload)
        await _emit_dnd_turn_progress(
            progress,
            "subagent_status",
            player_id=player.get("id"),
            player_name=player.get("name", ""),
            status="validated",
            turn_number=turn_number,
        )
        return {"action_text": validated["action"], "action_source": "hermes_subagent", "payload": validated, "error": None}
    except Exception as exc:
        await _emit_dnd_turn_progress(
            progress,
            "subagent_status",
            player_id=player.get("id"),
            player_name=player.get("name", ""),
            status="fallback_used",
            turn_number=turn_number,
            error=str(exc),
        )
        return {
            "action_text": _fallback_subagent_action(player, turn_number),
            "action_source": "deterministic_subagent_fallback",
            "payload": {},
            "error": str(exc),
        }


async def collect_dnd_turn_actions(players: list[dict], human_actions: dict, context: dict, turn_number: int, progress=None) -> list[dict]:
    tasks = {
        player["id"]: asyncio.create_task(generate_dnd_subagent_action(player, context, turn_number, progress=progress))
        for player in players
        if player.get("controller_type") == "subagent"
    }
    subagent_results = {}
    if tasks:
        results = await asyncio.gather(*tasks.values())
        subagent_results = dict(zip(tasks.keys(), results))
    actions = []
    for player in players:
        if player.get("controller_type") == "human":
            actions.append(
                {"player": player, "action_text": str(human_actions.get(player["id"]) or "waits and observes."), "action_source": "human", "payload": {}, "error": None}
            )
        else:
            actions.append({"player": player, **subagent_results[player["id"]]})
    return actions


async def generate_dnd_dm_resolution(context: dict, actions: list[dict], turn_number: int, progress=None) -> dict:
    await _emit_dnd_turn_progress(progress, "dm_status", status="thinking", turn_number=turn_number)
    messages = [
        {
            "role": "system",
            "content": (
                "You are the D&D Dungeon Master for a Hermes dashboard campaign. Resolve the "
                "batched player actions fairly and vividly. Return JSON only with narration and "
                "mechanics. Mechanics may be roll or scene_update only; the server will execute dice."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "turn_number": turn_number,
                    "campaign": context.get("campaign"),
                    "players": context.get("players"),
                    "characters": context.get("characters"),
                    "recent_events": context.get("recent_events"),
                    "actions": [
                        {
                            "player_id": action["player"].get("id"),
                            "player_name": action["player"].get("name"),
                            "controller_type": action["player"].get("controller_type"),
                            "action_text": action.get("action_text"),
                            "action_source": action.get("action_source"),
                            "payload": action.get("payload") or {},
                        }
                        for action in actions
                    ],
                    "schema": {
                        "narration": "required string",
                        "mechanics": [
                            {"type": "roll", "actor": "string", "expression": "1d20+3", "label": "string"},
                            {"type": "scene_update", "current_scene": {"summary": "string", "visible_threats": [], "open_questions": []}},
                        ],
                    },
                },
                sort_keys=True,
            ),
        },
    ]
    payload = await call_dnd_hermes_json(messages)
    await _emit_dnd_turn_progress(progress, "dm_status", status="json_received", turn_number=turn_number)
    resolution = validate_dnd_dm_resolution(payload)
    await _emit_dnd_turn_progress(progress, "dm_status", status="validated", turn_number=turn_number)
    return resolution


def _insert_dnd_event(
    conn: sqlite3.Connection,
    campaign_id: str,
    event_type: str,
    body: str,
    turn_id: str | None = None,
    actor: str | None = None,
    payload: dict | None = None,
    sequence_index: int | None = None,
) -> dict:
    event_id = uuid.uuid4().hex
    now = _dnd_now()
    if sequence_index is None:
        row = conn.execute(
            "SELECT COALESCE(MAX(sequence_index), -1) + 1 AS next_sequence FROM events WHERE campaign_id = ? AND (turn_id IS ? OR turn_id = ?)",
            (str(campaign_id), turn_id, turn_id),
        ).fetchone()
        sequence_index = int(row["next_sequence"] if row else 0)
    conn.execute(
        "INSERT INTO events (id, campaign_id, turn_id, event_type, body, actor, payload_json, sequence_index, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (event_id, str(campaign_id), turn_id, event_type, str(body or ""), actor if actor else None, json.dumps(payload or {}, sort_keys=True), int(sequence_index or 0), now),
    )
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return _dnd_row_to_dict(row)


def _apply_dnd_dm_resolution(conn: sqlite3.Connection, campaign_id: str, turn_id: str, resolution: dict, source: str) -> list[dict]:
    events: list[dict] = []
    events.append(
        _insert_dnd_event(conn, campaign_id, "dm_narration", resolution["narration"], turn_id=turn_id, actor="DM", payload={"resolution_source": source})
    )
    for mechanic in resolution.get("mechanics", []):
        if mechanic.get("type") == "roll":
            roll = roll_dnd_dice(mechanic["expression"], seed=f"{campaign_id}:{turn_id}:{mechanic.get('actor')}:{mechanic.get('label')}:{mechanic.get('expression')}")
            roll.update({"label": mechanic.get("label") or "Check", "actor": mechanic.get("actor") or ""})
            modifier_text = f" {roll['modifier']:+d}" if int(roll.get("modifier") or 0) else ""
            actor_text = f"{roll['actor']} " if roll.get("actor") else ""
            body = f"{actor_text}{roll['label']}: {roll['expression']} = {roll['total']} ({roll['rolls']}{modifier_text})"
            events.append(_insert_dnd_event(conn, campaign_id, "dice_roll", body, turn_id=turn_id, actor=roll.get("actor") or None, payload=roll))
        elif mechanic.get("type") == "scene_update":
            scene = dict(mechanic.get("current_scene") or {})
            now = _dnd_now()
            scene["updated_at"] = now
            conn.execute(
                "UPDATE campaigns SET current_scene = ?, updated_at = ? WHERE id = ?",
                (json.dumps(scene, sort_keys=True), now, str(campaign_id)),
            )
            events.append(_insert_dnd_event(conn, campaign_id, "scene_update", scene.get("summary") or "Scene updated.", turn_id=turn_id, actor="DM", payload=scene))
    return events


async def run_dnd_auto_turn(campaign_id: str, human_actions: dict | None = None, progress=None) -> dict:
    async with _dnd_turn_lock(str(campaign_id)):
        return await _run_dnd_auto_turn_unlocked(campaign_id, human_actions=human_actions, progress=progress)


async def _run_dnd_auto_turn_unlocked(campaign_id: str, human_actions: dict | None = None, progress=None) -> dict:
    campaign = get_dnd_campaign(campaign_id)
    if not campaign:
        raise KeyError("Campaign not found")
    players = list_dnd_players(campaign_id)
    human_actions = human_actions or {}
    _validate_dnd_human_actions(players, human_actions)
    turn_number = int(campaign.get("turn_number") or 1)
    await _emit_dnd_turn_progress(progress, "turn_started", turn_number=turn_number)
    context = build_dnd_turn_context(campaign_id)
    collected = await collect_dnd_turn_actions(players, human_actions, context, turn_number, progress=progress)
    try:
        dm_resolution = await generate_dnd_dm_resolution(context, collected, turn_number, progress=progress)
        dm_source = "hermes_dm"
    except Exception as exc:
        dm_resolution = fallback_dnd_dm_resolution(collected)
        dm_resolution["error"] = str(exc)
        dm_source = "deterministic_dm_fallback"
    turn_id = uuid.uuid4().hex
    now = _dnd_now()
    actions: list[dict] = []
    events: list[dict] = []
    with _dnd_connect() as conn:
        conn.execute(
            "INSERT INTO turns (id, campaign_id, turn_number, created_at) VALUES (?, ?, ?, ?)",
            (turn_id, str(campaign_id), turn_number, now),
        )
        for collected_action in collected:
            player = collected_action["player"]
            action_id = uuid.uuid4().hex
            action_text = collected_action["action_text"]
            source = collected_action["action_source"]
            status = "submitted" if player.get("controller_type") == "human" else ("fallback_used" if source == "deterministic_subagent_fallback" else "acted")
            conn.execute(
                "INSERT INTO player_actions (id, campaign_id, turn_id, player_id, action_text, action_source, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (action_id, str(campaign_id), turn_id, player["id"], action_text, source, now),
            )
            action_payload = {
                "player_id": player["id"],
                "player_name": player.get("name", ""),
                "controller_type": player.get("controller_type", ""),
                "action_source": source,
                "status": status,
                "action": collected_action.get("payload") or {},
            }
            if collected_action.get("error"):
                action_payload["error"] = collected_action["error"]
            action = {
                "id": action_id,
                "campaign_id": str(campaign_id),
                "turn_id": turn_id,
                "player_id": player["id"],
                "player_name": player.get("name", ""),
                "controller_type": player.get("controller_type", ""),
                "action_text": action_text,
                "action_source": source,
                "status": status,
                "error": collected_action.get("error"),
                "payload": collected_action.get("payload") or {},
                "created_at": now,
            }
            actions.append(action)
            event = _insert_dnd_event(conn, campaign_id, "player_action", action_text, turn_id=turn_id, actor=player.get("name"), payload=action_payload)
            events.append(event)
            if player.get("controller_type") == "subagent":
                await _emit_dnd_turn_progress(
                    progress,
                    "subagent_status",
                    player_id=player.get("id"),
                    player_name=player.get("name", ""),
                    status="committed",
                    turn_number=turn_number,
                    event_id=event.get("id"),
                )
            else:
                await _emit_dnd_turn_progress(
                    progress,
                    "human_action_committed",
                    player_id=player.get("id"),
                    player_name=player.get("name", ""),
                    turn_number=turn_number,
                    event_id=event.get("id"),
                )
            if collected_action.get("error"):
                events.append(
                    _insert_dnd_event(
                        conn,
                        campaign_id,
                        "subagent_status",
                        f"{player.get('name', 'Subagent')} used deterministic fallback: {collected_action['error']}",
                        turn_id=turn_id,
                        actor=player.get("name"),
                        payload={**action_payload, "status": "fallback_used"},
                    )
                )
        events.extend(_apply_dnd_dm_resolution(conn, campaign_id, turn_id, dm_resolution, dm_source))
        conn.execute(
            "UPDATE campaigns SET turn_number = ?, updated_at = ? WHERE id = ?",
            (turn_number + 1, now, str(campaign_id)),
        )
        conn.commit()
    await _emit_dnd_turn_progress(progress, "turn_committed", turn_number=turn_number, turn_id=turn_id)
    turn = {"id": turn_id, "campaign_id": str(campaign_id), "turn_number": turn_number, "created_at": now}
    return {"campaign": get_dnd_campaign(campaign_id), "turn": turn, "actions": actions, "events": events, "dm_resolution": {**dm_resolution, "source": dm_source}}


def list_dnd_events(campaign_id: str) -> list[dict]:
    if not get_dnd_campaign(campaign_id):
        raise KeyError("Campaign not found")
    with _dnd_connect() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE campaign_id = ? ORDER BY created_at DESC, sequence_index DESC, id DESC",
            (str(campaign_id),),
        ).fetchall()
    return _dnd_rows_to_dicts(rows)


async def _dnd_json_body(request):
    try:
        data = await request.json()
    except Exception:
        raise ValueError("Invalid JSON request body")
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("JSON request body must be an object")
    return data




def validate_dnd_character_creation_response(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Character creation response must be a JSON object")
    raw_character = payload.get("character") if isinstance(payload.get("character"), dict) else payload
    name = str(raw_character.get("name") or "").strip()
    if not name:
        raise ValueError("AI character JSON must include character.name")
    level = raw_character.get("level", 1)
    try:
        level = max(1, min(20, int(level)))
    except Exception:
        level = 1
    kind = str(raw_character.get("kind") or "pc").strip().lower()
    if kind not in DND_CHARACTER_KINDS:
        kind = "pc"
    character = {
        "name": name[:160],
        "kind": kind,
        "ancestry": str(raw_character.get("ancestry") or raw_character.get("race") or raw_character.get("species") or "").strip()[:120],
        "class_name": str(raw_character.get("class_name") or raw_character.get("class") or "").strip()[:120],
        "background": str(raw_character.get("background") or "").strip()[:400],
        "level": level,
        "ability_scores": raw_character.get("ability_scores") if isinstance(raw_character.get("ability_scores"), dict) else {},
        "equipment": raw_character.get("equipment") if isinstance(raw_character.get("equipment"), list) else [],
        "spells": raw_character.get("spells") if isinstance(raw_character.get("spells"), list) else [],
        "personality": raw_character.get("personality") if isinstance(raw_character.get("personality"), dict) else {},
        "backstory": str(raw_character.get("backstory") or "").strip()[:2000],
        "goals": raw_character.get("goals") if isinstance(raw_character.get("goals"), list) else [],
        "schema": "dnd.character_creation.v1",
    }
    return {"character": character, "questions": payload.get("questions") if isinstance(payload.get("questions"), list) else [], "assumptions": payload.get("assumptions") if isinstance(payload.get("assumptions"), list) else []}


def fallback_dnd_character_creation(campaign_id: str, prompt: str, constraints: dict | None = None) -> dict:
    campaign = get_dnd_campaign(campaign_id) or {}
    constraints = constraints or {}
    seed = str(prompt or "adventurer").strip() or "adventurer"
    name = seed.split()[0].strip(".,;:!?'")[:24].title() or "New Hero"
    character = {
        "name": f"{name} of {str((campaign.get('name') or 'the Road')).split()[0]}",
        "kind": "pc",
        "ancestry": str(constraints.get("ancestry") or constraints.get("species") or "Human"),
        "class_name": str(constraints.get("class_name") or constraints.get("class") or "Fighter"),
        "background": str(constraints.get("background") or "Folk Hero"),
        "level": int(constraints.get("level") or 1),
        "ability_scores": {"str": 14, "dex": 12, "con": 13, "int": 10, "wis": 11, "cha": 8},
        "equipment": ["adventurer's pack", "trusty weapon", "keepsake tied to the premise"],
        "spells": [],
        "personality": {"trait": "pragmatic and brave", "ideal": "protect the party"},
        "backstory": f"Generated offline from brief: {str(prompt or '').strip()[:400]}",
        "goals": ["survive the opening scene", "discover what the campaign premise is hiding"],
        "schema": "dnd.character_creation.v1",
    }
    return {"character": character, "questions": [], "assumptions": ["Hermes model unavailable; deterministic SRD-safe starter used."]}


async def generate_dnd_character_creation(campaign_id: str, prompt: str, constraints: dict | None = None, player_id: str | None = None) -> dict:
    campaign = get_dnd_campaign(campaign_id)
    if not campaign:
        raise KeyError("Campaign not found")
    constraints = constraints or {}
    messages = [
        {"role": "system", "content": "You are a D&D 5e character creation assistant inside Hermes. Return JSON only using schema dnd.character_creation.v1. Be rules-plausible, playable, and concise."},
        {"role": "user", "content": json.dumps({"campaign": campaign, "players": list_dnd_players(campaign_id), "existing_characters": list_dnd_characters(campaign_id), "brief": str(prompt or ""), "constraints": constraints, "schema": DND_SCHEMA_REGISTRY["dnd.character_creation.v1"]}, sort_keys=True)},
    ]
    try:
        payload = await call_dnd_hermes_json(messages)
        result = validate_dnd_character_creation_response(payload)
        result["source"] = "hermes_character_builder"
    except Exception as exc:
        result = fallback_dnd_character_creation(campaign_id, prompt, constraints)
        result["source"] = "deterministic_character_builder_fallback"
        result["error"] = str(exc)
    character = create_dnd_character(campaign_id, player_id, result["character"]["name"], result["character"])
    event = append_dnd_event(campaign_id, "character_generated", f"Created character {character['name']} from AI-assisted builder.", actor="Character Forge", payload={"schema": "dnd.character_creation.v1", "source": result.get("source"), "prompt": str(prompt or "")[:1000], "character_id": character["id"], "error": result.get("error")})
    return {"character": character, "draft": result, "event": event}


def create_dnd_world_entity(campaign_id: str, entity_type: str, name: str, summary: str = "", description: str = "", tags: list | None = None, metadata: dict | None = None) -> dict:
    if not get_dnd_campaign(campaign_id):
        raise KeyError("Campaign not found")
    entity_type = str(entity_type or "lore").strip().lower()
    if entity_type not in DND_WORLD_ENTITY_TYPES:
        raise ValueError("Unsupported world entity type")
    name = str(name or "").strip()
    if not name:
        raise ValueError("World entity name is required")
    entity_id = uuid.uuid4().hex
    now = _dnd_now()
    with _dnd_connect() as conn:
        conn.execute(
            "INSERT INTO world_entities (id, campaign_id, entity_type, name, summary, description, tags_json, metadata_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entity_id, str(campaign_id), entity_type, name[:200], str(summary or "")[:1000], str(description or "")[:6000], json.dumps(tags or [], sort_keys=True), json.dumps(metadata or {}, sort_keys=True), "active", now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM world_entities WHERE id = ?", (entity_id,)).fetchone()
    return _dnd_row_to_dict(row)


def list_dnd_world_entities(campaign_id: str, entity_type: str | None = None) -> list[dict]:
    if not get_dnd_campaign(campaign_id):
        raise KeyError("Campaign not found")
    with _dnd_connect() as conn:
        if entity_type:
            rows = conn.execute("SELECT * FROM world_entities WHERE campaign_id = ? AND entity_type = ? ORDER BY entity_type, name", (str(campaign_id), str(entity_type))).fetchall()
        else:
            rows = conn.execute("SELECT * FROM world_entities WHERE campaign_id = ? ORDER BY entity_type, name", (str(campaign_id),)).fetchall()
    return _dnd_rows_to_dicts(rows)


def validate_dnd_world_generation_response(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("World generation response must be a JSON object")
    world = payload.get("world") if isinstance(payload.get("world"), dict) else {}
    entities = []
    for key, entity_type in (("locations", "location"), ("npcs", "npc"), ("factions", "faction"), ("quests", "quest"), ("encounters", "encounter"), ("lore", "lore")):
        raw_items = payload.get(key) or []
        if not isinstance(raw_items, list):
            continue
        for item in raw_items[:25]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("title") or "").strip()
            if not name:
                continue
            entities.append({"entity_type": entity_type, "name": name[:200], "summary": str(item.get("summary") or item.get("hook") or item.get("description") or "")[:1000], "description": str(item.get("description") or item.get("details") or "")[:6000], "tags": item.get("tags") if isinstance(item.get("tags"), list) else [], "metadata": {k: v for k, v in item.items() if k not in {"name", "title", "summary", "description", "details", "tags"}}})
    starting_scene = payload.get("starting_scene") if isinstance(payload.get("starting_scene"), dict) else None
    return {"world": world, "entities": entities, "starting_scene": starting_scene, "schema": "dnd.world_generation.v1"}


def fallback_dnd_world_generation(campaign_id: str, brief: str, parameters: dict | None = None) -> dict:
    campaign = get_dnd_campaign(campaign_id) or {}
    parameters = parameters or {}
    tone = parameters.get("tone") or "mythic frontier"
    premise = str(brief or campaign.get("description") or campaign.get("name") or "a new adventure")
    payload = {
        "world": {"theme": tone, "premise": premise[:800], "rules_profile_id": parameters.get("rules_profile_id", "dnd5e"), "content_pack_id": parameters.get("content_pack_id", "fantasy_core")},
        "locations": [{"name": "The Lantern Gate", "summary": "A threshold settlement where rumors become quests."}, {"name": "Whisperdeep Ruins", "summary": "Ancient chambers under pressure from a newly awakened threat."}],
        "npcs": [{"name": "Mara Vell", "summary": "A nervous guide with a useful map and one dangerous omission."}],
        "factions": [{"name": "The Ember Compact", "summary": "Local defenders split between caution and glory."}],
        "quests": [{"title": "Find the Missing Bell", "hook": "A warding bell vanished the night before monsters stirred."}],
        "encounters": [{"title": "Gatehouse Ambush", "summary": "A tactical opening scene with noise, cover, and frightened witnesses."}],
        "starting_scene": {"summary": f"The party gathers at the Lantern Gate as {premise[:180]}", "location": "The Lantern Gate", "mood": str(tone), "visible_threats": [], "open_questions": ["Who benefits if the gate falls?"]},
    }
    return validate_dnd_world_generation_response(payload)


async def generate_dnd_world(campaign_id: str, brief: str = "", parameters: dict | None = None) -> dict:
    campaign = get_dnd_campaign(campaign_id)
    if not campaign:
        raise KeyError("Campaign not found")
    parameters = parameters or {}
    messages = [
        {"role": "system", "content": "You are a D&D campaign world builder inside Hermes. Return JSON only using schema dnd.world_generation.v1 with world, locations, npcs, factions, quests, encounters, and starting_scene."},
        {"role": "user", "content": json.dumps({"campaign": campaign, "brief": brief, "parameters": parameters, "schema": DND_SCHEMA_REGISTRY["dnd.world_generation.v1"]}, sort_keys=True)},
    ]
    source = "hermes_world_builder"
    error = None
    try:
        payload = await call_dnd_hermes_json(messages, timeout_seconds=120.0)
        generated = validate_dnd_world_generation_response(payload)
    except Exception as exc:
        generated = fallback_dnd_world_generation(campaign_id, brief, parameters)
        source = "deterministic_world_builder_fallback"
        error = str(exc)
    entities = [create_dnd_world_entity(campaign_id, **entity) for entity in generated["entities"]]
    world_state = {"schema": "dnd.world_generation.v1", "source": source, "world": generated["world"], "entity_count": len(entities), "updated_at": _dnd_now()}
    with _dnd_connect() as conn:
        conn.execute("UPDATE campaigns SET world_state = ?, world_metadata = ?, updated_at = ? WHERE id = ?", (json.dumps(world_state, sort_keys=True), json.dumps(parameters, sort_keys=True), _dnd_now(), str(campaign_id)))
        conn.commit()
    scene = None
    if generated.get("starting_scene"):
        scene = set_dnd_scene_state(campaign_id, generated["starting_scene"])
    event = append_dnd_event(campaign_id, "world_generated", f"Generated {len(entities)} world entities for the campaign.", actor="World Forge", payload={"schema": "dnd.world_generation.v1", "source": source, "entity_ids": [e["id"] for e in entities], "error": error})
    return {"campaign": get_dnd_campaign(campaign_id), "world": world_state, "entities": entities, "starting_scene": scene, "event": event, "source": source, **({"error": error} if error else {})}


async def dnd_campaigns_endpoint(request):
    method = str(getattr(request, "method", "POST") or "POST").upper()
    if method == "GET":
        return JSONResponse({"campaigns": list_dnd_campaigns()})
    try:
        data = await _dnd_json_body(request)
        campaign = create_dnd_campaign(data.get("name", ""), description=data.get("description", ""))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"campaign": campaign})


async def dnd_campaign_detail_endpoint(request):
    campaign_id = getattr(request, "path_params", {}).get("campaign_id")
    campaign = get_dnd_campaign(str(campaign_id or ""))
    if not campaign:
        return JSONResponse({"error": "Campaign not found"}, status_code=404)
    return JSONResponse(
        {"campaign": campaign, "players": list_dnd_players(campaign["id"]), "characters": list_dnd_characters(campaign["id"])}
    )


async def create_dnd_player_endpoint(request):
    campaign_id = getattr(request, "path_params", {}).get("campaign_id")
    try:
        data = await _dnd_json_body(request)
        player = create_dnd_player(
            str(campaign_id or ""),
            data.get("name", ""),
            data.get("controller_type", ""),
            agent_prompt=data.get("agent_prompt"),
        )
    except KeyError:
        return JSONResponse({"error": "Campaign not found"}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"player": player})




async def dnd_characters_endpoint(request):
    campaign_id = str(getattr(request, "path_params", {}).get("campaign_id") or "")
    method = str(getattr(request, "method", "GET") or "GET").upper()
    try:
        if method == "GET":
            return JSONResponse({"characters": list_dnd_characters(campaign_id)})
        data = await _dnd_json_body(request)
        sheet = data.get("character_sheet") or data.get("sheet") or {}
        if not isinstance(sheet, dict):
            raise ValueError("character_sheet must be an object")
        for key in ("kind", "ancestry", "class_name", "background", "level"):
            if key in data and key not in sheet:
                sheet[key] = data[key]
        character = create_dnd_character(campaign_id, data.get("player_id"), data.get("name", ""), sheet)
    except KeyError:
        return JSONResponse({"error": "Campaign not found"}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"character": character})


async def dnd_character_generate_endpoint(request):
    campaign_id = str(getattr(request, "path_params", {}).get("campaign_id") or "")
    try:
        data = await _dnd_json_body(request)
        constraints = data.get("constraints") or {}
        if not isinstance(constraints, dict):
            raise ValueError("constraints must be an object")
        result = await generate_dnd_character_creation(campaign_id, data.get("prompt") or data.get("brief") or "", constraints=constraints, player_id=data.get("player_id"))
    except KeyError:
        return JSONResponse({"error": "Campaign not found"}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


async def dnd_world_entities_endpoint(request):
    campaign_id = str(getattr(request, "path_params", {}).get("campaign_id") or "")
    method = str(getattr(request, "method", "GET") or "GET").upper()
    try:
        if method == "GET":
            entity_type = None
            query = getattr(request, "query_params", {}) or {}
            if hasattr(query, "get"):
                entity_type = query.get("entity_type") or query.get("type")
            return JSONResponse({"entities": list_dnd_world_entities(campaign_id, entity_type=entity_type)})
        data = await _dnd_json_body(request)
        tags = data.get("tags") or []
        metadata = data.get("metadata") or data.get("payload") or {}
        if not isinstance(tags, list):
            raise ValueError("tags must be a list")
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        entity = create_dnd_world_entity(campaign_id, data.get("entity_type") or data.get("type") or "lore", data.get("name", ""), summary=data.get("summary", ""), description=data.get("description", ""), tags=tags, metadata=metadata)
    except KeyError:
        return JSONResponse({"error": "Campaign not found"}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"entity": entity})


async def dnd_world_generate_endpoint(request):
    campaign_id = str(getattr(request, "path_params", {}).get("campaign_id") or "")
    try:
        data = await _dnd_json_body(request)
        parameters = data.get("parameters") or {}
        if not isinstance(parameters, dict):
            raise ValueError("parameters must be an object")
        result = await generate_dnd_world(campaign_id, brief=data.get("brief") or data.get("prompt") or "", parameters=parameters)
    except KeyError:
        return JSONResponse({"error": "Campaign not found"}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


async def dnd_schemas_endpoint(request):
    return JSONResponse({"schemas": DND_SCHEMA_REGISTRY, "bounded_context": {"player": "controller/human at table", "character": "fictional sheet/persona", "subagent": "AI controller for a player", "turn": "batched action/resolution unit", "scene": "current narrated situation", "world_entity": "editable lore/map/quest/NPC record"}})


def _validate_dnd_auto_turn_start(campaign_id: str, human_actions: dict) -> None:
    if not get_dnd_campaign(campaign_id):
        raise KeyError("Campaign not found")
    if not isinstance(human_actions, dict):
        raise ValueError("human_actions must be an object mapping player IDs to actions")
    _validate_dnd_human_actions(list_dnd_players(campaign_id), human_actions)


async def _run_dnd_auto_turn_job(job_id: str, human_actions: dict) -> None:
    job = DND_AUTO_TURN_JOBS.get(job_id)
    if not job:
        return
    campaign_id = job["campaign_id"]

    def progress(event: dict) -> None:
        current = DND_AUTO_TURN_JOBS.get(job_id)
        if current:
            _record_dnd_auto_turn_job_event(current, event)

    try:
        job["status"] = "running"
        job["progress"] = {"phase": "collecting_actions", "percent": 5}
        job["updated_at"] = _dnd_now()
        result = await run_dnd_auto_turn(campaign_id, human_actions=human_actions, progress=progress)
        job["result"] = result
        job["status"] = "completed"
        job["progress"] = {"phase": "completed", "percent": 100}
        job["updated_at"] = _dnd_now()
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        job["progress"] = {"phase": "failed", "percent": int((job.get("progress") or {}).get("percent") or 0)}
        job["updated_at"] = _dnd_now()
        _record_dnd_auto_turn_job_event(job, {"type": "turn_failed", "status": "failed", "error": str(exc)})
    finally:
        if DND_ACTIVE_AUTO_TURN_JOB_BY_CAMPAIGN.get(campaign_id) == job_id:
            DND_ACTIVE_AUTO_TURN_JOB_BY_CAMPAIGN.pop(campaign_id, None)


async def dnd_auto_turn_job_start_endpoint(request):
    campaign_id = str(getattr(request, "path_params", {}).get("campaign_id") or "")
    try:
        data = await _dnd_json_body(request)
        human_actions = data.get("human_actions") or {}
        _validate_dnd_auto_turn_start(campaign_id, human_actions)
    except KeyError:
        return JSONResponse({"error": "Campaign not found"}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    active_job_id = DND_ACTIVE_AUTO_TURN_JOB_BY_CAMPAIGN.get(campaign_id)
    active_job = DND_AUTO_TURN_JOBS.get(active_job_id or "")
    if active_job and active_job.get("status") in {"queued", "running"}:
        return JSONResponse(
            {"error": "A live turn job is already active for this campaign", "job": _serialize_dnd_auto_turn_job(active_job)},
            status_code=409,
        )

    campaign = get_dnd_campaign(campaign_id)
    now = _dnd_now()
    job_id = f"dnd_turn_job_{uuid.uuid4().hex}"
    job = {
        "id": job_id,
        "campaign_id": campaign_id,
        "status": "queued",
        "turn_number": int((campaign or {}).get("turn_number") or 1),
        "created_at": now,
        "updated_at": now,
        "progress": {"phase": "queued", "percent": 0},
        "events": [],
        "result": None,
        "error": None,
        "task": None,
    }
    DND_AUTO_TURN_JOBS[job_id] = job
    for player in list_dnd_players(campaign_id):
        if player.get("controller_type") == "subagent":
            _record_dnd_auto_turn_job_event(
                job,
                {
                    "type": "subagent_status",
                    "player_id": player.get("id"),
                    "player_name": player.get("name", ""),
                    "status": "thinking",
                    "turn_number": job["turn_number"],
                },
            )
    DND_ACTIVE_AUTO_TURN_JOB_BY_CAMPAIGN[campaign_id] = job_id
    task = asyncio.create_task(_run_dnd_auto_turn_job(job_id, dict(human_actions)))
    job["task"] = task
    return JSONResponse({"job": _serialize_dnd_auto_turn_job(job)}, status_code=202)


async def dnd_auto_turn_job_status_endpoint(request):
    campaign_id = str(getattr(request, "path_params", {}).get("campaign_id") or "")
    job_id = str(getattr(request, "path_params", {}).get("job_id") or "")
    if not get_dnd_campaign(campaign_id):
        return JSONResponse({"error": "Campaign not found"}, status_code=404)
    job = DND_AUTO_TURN_JOBS.get(job_id)
    if not job or str(job.get("campaign_id")) != campaign_id:
        return JSONResponse({"error": "Live turn job not found"}, status_code=404)
    return JSONResponse({"job": _serialize_dnd_auto_turn_job(job)})


async def dnd_auto_turn_endpoint(request):
    campaign_id = getattr(request, "path_params", {}).get("campaign_id")
    try:
        data = await _dnd_json_body(request)
        human_actions = data.get("human_actions") or {}
        if not isinstance(human_actions, dict):
            raise ValueError("human_actions must be an object mapping player IDs to actions")
        result = await run_dnd_auto_turn(str(campaign_id or ""), human_actions=human_actions)
    except KeyError:
        return JSONResponse({"error": "Campaign not found"}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


async def dnd_campaign_scene_endpoint(request):
    campaign_id = getattr(request, "path_params", {}).get("campaign_id")
    try:
        data = await _dnd_json_body(request)
        scene = data.get("current_scene", data.get("scene", data.get("summary", "")))
        campaign = update_dnd_scene(str(campaign_id or ""), scene)
    except KeyError:
        return JSONResponse({"error": "Campaign not found"}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"campaign": campaign})


async def dnd_dice_roll_endpoint(request):
    campaign_id = getattr(request, "path_params", {}).get("campaign_id")
    try:
        data = await _dnd_json_body(request)
        result = roll_and_record_dnd_dice(
            str(campaign_id or ""),
            data.get("expression", ""),
            label=data.get("label") or data.get("purpose") or "",
            actor=data.get("actor") or "",
            seed=data.get("seed"),
            turn_id=data.get("turn_id"),
        )
    except KeyError:
        return JSONResponse({"error": "Campaign not found"}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


def _dnd_event_payload_from_request(data: dict) -> tuple[str, str, str | None, dict]:
    event_type = str(data.get("event_type") or data.get("type") or "dm_narration").strip()
    body = str(data.get("body") or data.get("content") or data.get("message") or "").strip()
    actor = data.get("actor")
    payload = data.get("payload") or {}
    if not event_type:
        raise ValueError("event_type is required")
    if not body:
        raise ValueError("Event body is required")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    return event_type, body, str(actor).strip() if actor is not None and str(actor).strip() else None, payload


async def dnd_campaign_events_endpoint(request):
    campaign_id = getattr(request, "path_params", {}).get("campaign_id")
    method = str(getattr(request, "method", "GET") or "GET").upper()
    has_payload = getattr(request, "_payload", None) is not None
    if method == "POST" or has_payload:
        try:
            data = await _dnd_json_body(request)
            event_type, body, actor, payload = _dnd_event_payload_from_request(data)
            if event_type == "scene_update":
                scene_payload = payload.get("current_scene") or payload.get("scene") or {"summary": body}
                payload = set_dnd_scene_state(str(campaign_id or ""), scene_payload)
                body = payload.get("summary") or body
            event = append_dnd_event(str(campaign_id or ""), event_type, body, actor=actor, payload=payload)
        except KeyError:
            return JSONResponse({"error": "Campaign not found"}, status_code=404)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"event": event})
    try:
        events = list_dnd_events(str(campaign_id or ""))
    except KeyError:
        return JSONResponse({"error": "Campaign not found"}, status_code=404)
    return JSONResponse({"events": events})



# ---------------------------------------------------------------------------
# ScrollPrize / Vesuvius AutoResearch dashboard helpers
# ---------------------------------------------------------------------------
_SCROLLS_PROJECT_ROOT = Path(os.environ.get(
    "HERMES_SCROLLS_RESEARCH_ROOT",
    str(Path.home() / "projects" / "vesuvius-autoresearch"),
)).expanduser()
_SCROLLS_LOOP_LOCK = threading.Lock()
_SCROLLS_LOOP_STOP = threading.Event()
_SCROLLS_LOOP_STATE: dict[str, Any] = {
    "active": False,
    "started_at": None,
    "deadline_at": None,
    "duration_minutes": 0,
    "iterations": 0,
    "current_pid": None,
    "last_returncode": None,
    "last_error": None,
    "status": "idle",
}


def _scrolls_python(project_root: Path) -> str:
    venv_python = project_root / ".venv" / "bin" / "python"
    return str(venv_python) if venv_python.exists() else sys.executable


def _scrolls_safe_config_name(name: str) -> str:
    candidate = Path(str(name or "")).name
    if candidate != name or not candidate.endswith((".yaml", ".yml", ".json")):
        raise ValueError("Config must be a file name under configs/ ending in .yaml, .yml, or .json")
    return candidate


def _scrolls_tail(path: Path, lines: int = 80) -> list[str]:
    try:
        if not path.exists():
            return []
        return path.read_text(errors="replace").splitlines()[-lines:]
    except Exception as exc:
        return [f"<failed to read {path}: {exc}>"]


def _scrolls_read_yaml_json(path: Path) -> dict:
    try:
        with path.open("r") as fh:
            value = json.load(fh) if path.suffix == ".json" else yaml.safe_load(fh)
        return value if isinstance(value, dict) else {}
    except Exception as exc:
        return {"_error": str(exc)}


def _scrolls_lock_active(project_root: Path) -> bool:
    lock_path = project_root / "logs" / "autoresearch.lock"
    if not lock_path.exists():
        return False
    try:
        import fcntl
        with lock_path.open("a+") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fh, fcntl.LOCK_UN)
                return False
            except BlockingIOError:
                return True
    except Exception:
        return False


def _scrolls_data_summary(project_root: Path) -> dict:
    if not project_root.exists():
        return {"source": "missing_project", "scrolls": [], "splits": {}}
    script = "import json; from data.vesuvius_data import get_dataset_summary; print(json.dumps(get_dataset_summary()))"
    try:
        proc = subprocess.run(
            [_scrolls_python(project_root), "-c", script],
            cwd=str(project_root),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout)
        return {"source": "summary_error", "error": proc.stderr.strip() or proc.stdout.strip(), "scrolls": [], "splits": {}}
    except Exception as exc:
        return {"source": "summary_error", "error": str(exc), "scrolls": [], "splits": {}}


def _scrolls_prepared_datasets(project_root: Path) -> list[dict]:
    items = []
    meta_paths = []
    for root in [project_root / "data" / "prepared", project_root / "data" / "real"]:
        if root.exists():
            meta_paths.extend(root.glob("**/metadata.json"))
            meta_paths.extend(root.glob("**/*.metadata.json"))
    for meta_path in sorted(set(meta_paths), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            metadata = json.loads(meta_path.read_text())
        except Exception as exc:
            metadata = {"_error": str(exc)}
        npz = Path(str(meta_path)[:-len(".metadata.json")] + ".npz") if meta_path.name.endswith(".metadata.json") else next(meta_path.parent.glob("*.npz"), None)
        items.append({"path": str(npz or meta_path.parent), "metadata": metadata})
    return items[:50]


def _scrolls_configs(project_root: Path) -> list[dict]:
    cfg_dir = project_root / "configs"
    if not cfg_dir.exists():
        return []
    paths = list(cfg_dir.glob("*.yaml")) + list(cfg_dir.glob("*.yml")) + list(cfg_dir.glob("*.json"))
    out = []
    for cfg in sorted(paths, key=lambda x: x.stat().st_mtime, reverse=True):
        out.append({"name": cfg.name, "path": str(cfg), "modified_at": cfg.stat().st_mtime, "summary": _scrolls_read_yaml_json(cfg)})
    return out


def _scrolls_autoresearch_inventory(project_root: Path) -> dict:
    def command_item(title: str, command: str, detail: str, paths: list[str] | None = None, kind: str = "command") -> dict:
        paths = paths or []
        return {
            "title": title,
            "kind": kind,
            "command": command,
            "detail": detail,
            "paths": paths,
            "available": all((project_root / path).exists() for path in paths) if paths else project_root.exists(),
        }

    commands = [
        command_item(
            "Seed-repeat LOO dry-run",
            ".venv/bin/python scripts/evaluate_leave_one_out.py --base-config configs/robust_multisegment_dice035_expanded.yaml --fold-map data/real_cross_folds_expanded_combined/fold_map.json --output-jsonl /tmp/opencode/vesuvius_loo_seed_dry_run.jsonl --summary-json /tmp/opencode/vesuvius_loo_seed_dry_run.summary.json --label dice035_seed_repeat --seeds 13,37,101 --dry-run",
            "Plans repeated leave-one-segment-out folds without launching training.",
            ["scripts/evaluate_leave_one_out.py", "configs/robust_multisegment_dice035_expanded.yaml"],
        ),
        command_item(
            "Verify prepared segments",
            ".venv/bin/python scripts/verify_prepared_segments.py --segments-root data/real_cross_folds_v2",
            "Checks train/val NPZ metadata before trusting fold results.",
            ["scripts/verify_prepared_segments.py"],
        ),
        command_item(
            "Build fold map dry-run",
            ".venv/bin/python scripts/build_segment_fold_map.py --segments-root data/real_cross_folds_v2 --output-root /tmp/opencode/vesuvius_folds_dry_run --fold-map-out /tmp/opencode/vesuvius_folds_dry_run/fold_map.json --dry-run",
            "Validates the leave-one-segment-out fold map layout without overwriting it.",
            ["scripts/build_segment_fold_map.py"],
        ),
        command_item(
            "Full-tile self-test",
            ".venv/bin/python scripts/infer_full_tile.py --self-test",
            "Runs the lightweight stitched-tile inference self-test before using full-tile outputs.",
            ["scripts/infer_full_tile.py"],
        ),
        command_item(
            "Residual 2.5D smoke command",
            ".venv/bin/python run_experiment.py --config configs/residual_25d_torch_unet_cpu.yaml",
            "CPU smoke run for the residual 2.5D torch U-Net candidate.",
            ["run_experiment.py", "configs/residual_25d_torch_unet_cpu.yaml"],
        ),
        command_item(
            "Robust TTA config note",
            ".venv/bin/python run_experiment.py --config configs/robust_tta_seed_ensemble.yaml",
            "Review the robust TTA/seed ensemble config and budget before running; it is a champion candidate, not a quick dry-run.",
            ["run_experiment.py", "configs/robust_tta_seed_ensemble.yaml"],
            kind="config-note",
        ),
        command_item(
            "Data expansion polite command",
            ".venv/bin/python scripts/prepare_vesuvius_segment_npz.py --all-labeled --catalog-source public-directory --output-root data/real_cross_folds_v3 --skip-existing --max-new-segments 1 --request-delay-sec 10 --segment-delay-sec 60 --level 1 --patch-size 64 --train-samples 768 --positive-fraction 0.15 --negative-max-positive-rate 0.001 --z-offsets=-4,0,4 --val-tiled --val-stride 64 --val-samples 0",
            "Adds at most one new labeled segment with request delays so catalog/data access stays polite.",
            ["scripts/prepare_vesuvius_segment_npz.py"],
        ),
    ]
    champion_names = [
        "robust_multisegment_dice035_expanded.yaml",
        "residual_25d_torch_unet_cpu.yaml",
        "robust_tta_seed_ensemble.yaml",
        "next_best_moves_robust_template.yaml",
    ]
    return {
        "features": commands,
        "champion_configs": [
            {"name": name, "path": f"configs/{name}", "available": (project_root / "configs" / name).exists()}
            for name in champion_names
        ],
        "warnings": [
            "Ignore archived/synthetic artifacts when judging current champions; prefer live experiments/runs plus real prepared data.",
            "Use .venv/bin/python from the Vesuvius AutoResearch project root so torch/numpy/catalog dependencies match the prepared data.",
        ],
    }


def _scrolls_artifact_files(artifact_dir: str | None, limit: int = 8) -> list[dict]:
    if not artifact_dir:
        return []
    root = Path(artifact_dir).expanduser()
    if not root.exists() or not root.is_dir():
        return []
    files: list[dict] = []
    try:
        for path in sorted((p for p in root.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True):
            stat = path.stat()
            files.append({
                "name": path.name,
                "path": str(path),
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
                "kind": path.suffix.lstrip(".") or "file",
            })
            if len(files) >= limit:
                break
    except Exception:
        return files
    return files


def _scrolls_artifact_preview(project_root: Path, artifact_path: str) -> dict:
    runs_root = (project_root / "experiments" / "runs").resolve()
    path = Path(artifact_path or "").expanduser().resolve()
    if runs_root not in path.parents:
        raise ValueError("Artifact must be under experiments/runs")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError("Artifact not found")
    stat = path.stat()
    suffix = path.suffix.lower()
    out = {
        "name": path.name,
        "path": str(path),
        "size_bytes": stat.st_size,
        "modified_at": stat.st_mtime,
        "kind": suffix.lstrip(".") or "file",
        "preview": None,
        "truncated": False,
    }
    if suffix == ".json":
        try:
            out["preview"] = json.loads(path.read_text(errors="replace"))
            return out
        except Exception as exc:
            out["preview_error"] = str(exc)
    if suffix in {".txt", ".log", ".md", ".yaml", ".yml", ".csv"} or path.name in {"config", "metrics"}:
        max_chars = 24000
        text = path.read_text(errors="replace")
        out["preview"] = text[:max_chars]
        out["truncated"] = len(text) > max_chars
        return out
    out["preview_error"] = "Preview unavailable for binary or unsupported artifact type"
    return out


def _scrolls_get_nested(obj: dict, path: tuple[str, ...], default=None):
    cur = obj
    for part in path:
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _scrolls_json_key(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        return str(value)


def _scrolls_flatten_config(obj: Any, prefix: str = "", out: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    if out is None:
        out = {}
    if isinstance(obj, dict):
        if not obj and prefix:
            out[prefix] = {}
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            _scrolls_flatten_config(value, path, out)
    elif isinstance(obj, list):
        out[prefix] = obj
    elif prefix:
        out[prefix] = obj
    return out


def _scrolls_config_diff(before: Optional[dict], after: Optional[dict], limit: int = 32) -> list[dict]:
    left = _scrolls_flatten_config(before or {})
    right = _scrolls_flatten_config(after or {})
    diffs: list[dict] = []
    for path in sorted(set(left) | set(right)):
        before_value = left.get(path)
        after_value = right.get(path)
        if _scrolls_json_key(before_value) == _scrolls_json_key(after_value):
            continue
        diffs.append({"path": path, "before": before_value, "after": after_value})
        if len(diffs) >= limit:
            break
    return diffs


def _scrolls_run_validation_setup(run: dict) -> dict:
    cfg = run.get("config", {}) if isinstance(run.get("config"), dict) else {}
    setup = cfg.get("validation_setup") if isinstance(cfg.get("validation_setup"), dict) else {}
    resolved = cfg.get("resolved_data", {}) if isinstance(cfg.get("resolved_data"), dict) else {}
    train_meta = resolved.get("train", {}) if isinstance(resolved.get("train"), dict) else {}
    val_meta = resolved.get("val", {}) if isinstance(resolved.get("val"), dict) else {}
    train_data = train_meta.get("metadata", {}) if isinstance(train_meta.get("metadata"), dict) else {}
    val_data = val_meta.get("metadata", {}) if isinstance(val_meta.get("metadata"), dict) else {}
    train_scroll = str(setup.get("train_scroll_id") or train_data.get("scroll_id") or _scrolls_get_nested(cfg, ("dataset", "train_scroll_id"), "?"))
    val_scroll = str(setup.get("val_scroll_id") or val_data.get("scroll_id") or _scrolls_get_nested(cfg, ("dataset", "val_scroll_id"), "?"))
    train_segment = str(setup.get("train_segment_id") or train_data.get("segment_id") or "?")
    val_segment = str(setup.get("val_segment_id") or val_data.get("segment_id") or "?")
    mode = str(setup.get("mode") or _scrolls_get_nested(cfg, ("dataset", "validation_mode"), "unknown"))
    if mode == "unknown":
        if train_scroll != "?" and val_scroll != "?" and train_scroll != val_scroll:
            mode = "cross-scroll"
        elif train_segment != "?" and val_segment != "?" and train_segment != val_segment:
            mode = "cross-segment"
        elif train_segment != "?" and val_segment != "?":
            mode = "spatial-same-segment"
    warning = setup.get("warning")
    if not warning and mode not in {"cross-scroll", "cross-segment"}:
        warning = "Validation is not cross-segment/cross-scroll."
    return {
        "mode": mode,
        "warning": warning,
        "train_scroll_id": train_scroll,
        "val_scroll_id": val_scroll,
        "train_segment_id": train_segment,
        "val_segment_id": val_segment,
    }


def _scrolls_hypotheses(runs_chronological: list[dict], limit: int = 12) -> list[dict]:
    projected: list[dict] = []
    previous: Optional[dict] = None
    for run in runs_chronological:
        diff = _scrolls_config_diff(previous.get("config") if previous else None, run.get("config"), limit=16)
        reason = _scrolls_get_nested(run.get("config", {}), ("autoresearch", "parent_reason"), None)
        if reason is None:
            reason = _scrolls_get_nested(run.get("config", {}), ("autoresearch", "hypothesis"), None)
        delta = None
        improved = None
        status = "inconclusive"
        if previous is not None:
            delta = run["main_metric"] - previous["main_metric"]
            metric_name = _scrolls_get_nested(run.get("config", {}), ("evaluation", "main_metric"), "val_loss")
            direction = 1 if "loss" in str(metric_name).lower() else -1
            improved = direction * delta < 0
            if direction * delta < -1e-12:
                status = "improved"
            elif direction * delta > 1e-12:
                status = "regressed"
        projected.append({
            "run_id": run["run_id"],
            "timestamp": run["timestamp"],
            "reason": str(reason) if reason is not None else None,
            "changed_paths": [item["path"] for item in diff],
            "metric": run["main_metric"],
            "previous_metric": previous["main_metric"] if previous else None,
            "metric_delta_vs_previous": delta,
            "improved_vs_previous": improved,
            "status": status,
        })
        previous = run
    return list(reversed(projected))[:limit]


def _scrolls_experiments(project_root: Path) -> dict:
    db_path = project_root / "experiments" / "experiments.db"
    empty = {
        "count": 0,
        "best": None,
        "latest": None,
        "recent": [],
        "metric_trends": [],
        "validation_matrix": [],
        "config_diffs": {"latest_vs_previous": [], "latest_vs_best": [], "latest_vs_baseline": []},
        "hypotheses": [],
    }
    if not db_path.exists():
        return empty
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            count = conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
            rows = conn.execute("SELECT run_id,timestamp,config_json,main_metric,secondary_metrics_json,artifact_dir FROM experiments ORDER BY timestamp DESC LIMIT 500").fetchall()
            best_row = conn.execute("SELECT run_id,timestamp,config_json,main_metric,secondary_metrics_json,artifact_dir FROM experiments ORDER BY main_metric ASC LIMIT 1").fetchone()
        finally:
            conn.close()
        def row_to_run(row, include_artifacts: bool = True):
            run = {
                "run_id": row["run_id"],
                "timestamp": row["timestamp"],
                "main_metric": float(row["main_metric"]),
                "metrics": json.loads(row["secondary_metrics_json"] or "{}"),
                "config": json.loads(row["config_json"] or "{}"),
                "artifact_dir": row["artifact_dir"],
            }
            run["validation_setup"] = _scrolls_run_validation_setup(run)
            if include_artifacts:
                run["artifacts"] = _scrolls_artifact_files(row["artifact_dir"])
            return run
        runs = [row_to_run(r) for r in rows]
        best = row_to_run(best_row) if best_row else None
        if runs:
            baseline_mode = _scrolls_get_nested(_scrolls_read_yaml_json(project_root / "configs" / "baseline.yaml"), ("dataset", "validation_mode"), None)
            def best_key(run: dict):
                metric_name = _scrolls_get_nested(run.get("config", {}), ("evaluation", "main_metric"), "val_loss")
                direction = 1 if "loss" in str(metric_name).lower() else -1
                return direction * float(run.get("main_metric", 0.0))
            comparable_runs = [r for r in runs if not baseline_mode or _scrolls_get_nested(r.get("config", {}), ("dataset", "validation_mode"), None) == baseline_mode]
            best = sorted(comparable_runs or runs, key=best_key)[0]
        chronological = list(reversed(runs))[-30:]
        metric_trends = [{
            "run_id": r["run_id"],
            "timestamp": r["timestamp"],
            "main_metric": r["main_metric"],
            "val_loss": r["metrics"].get("val_loss"),
            "val_f1": r["metrics"].get("val_f1"),
            "precision": r["metrics"].get("precision"),
            "recall": r["metrics"].get("recall"),
        } for r in chronological]
        matrix: dict[tuple[str, str], dict] = {}
        for r in runs:
            setup = r.get("validation_setup", {})
            key = (
                str(setup.get("train_segment_id") or setup.get("train_scroll_id") or "?"),
                str(setup.get("val_segment_id") or setup.get("val_scroll_id") or "?"),
            )
            prev = matrix.get(key)
            metric_name = _scrolls_get_nested(r.get("config", {}), ("evaluation", "main_metric"), "val_loss")
            direction = 1 if "loss" in str(metric_name).lower() else -1
            is_better = prev is None or direction * r["main_metric"] < direction * prev["best_main_metric"]
            if is_better:
                matrix[key] = {
                    "train_scroll_id": setup.get("train_scroll_id"),
                    "val_scroll_id": setup.get("val_scroll_id"),
                    "train_segment_id": setup.get("train_segment_id"),
                    "val_segment_id": setup.get("val_segment_id"),
                    "validation_mode": setup.get("mode"),
                    "best_run_id": r["run_id"],
                    "best_main_metric": r["main_metric"],
                    "best_val_f1": r["metrics"].get("val_f1"),
                    "run_count": 1 if prev is None else prev["run_count"] + 1,
                    "latest_timestamp": r["timestamp"],
                }
            else:
                prev["run_count"] += 1
                prev["latest_timestamp"] = max(str(prev.get("latest_timestamp", "")), str(r["timestamp"]))
        latest = runs[0] if runs else None
        previous = runs[1] if len(runs) > 1 else None
        baseline = chronological[0] if chronological else None
        return {
            "count": int(count),
            "best": best,
            "latest": latest,
            "recent": runs[:500],
            "metric_trends": metric_trends,
            "validation_matrix": sorted(matrix.values(), key=lambda x: (x["train_scroll_id"], x["val_scroll_id"])),
            "config_diffs": {
                "latest_vs_previous": _scrolls_config_diff(previous.get("config") if previous else None, latest.get("config") if latest else None),
                "latest_vs_best": _scrolls_config_diff(best.get("config") if best else None, latest.get("config") if latest else None),
                "latest_vs_baseline": _scrolls_config_diff(baseline.get("config") if baseline else None, latest.get("config") if latest else None),
            },
            "hypotheses": _scrolls_hypotheses(chronological),
        }
    except Exception as exc:
        out = dict(empty)
        out["error"] = str(exc)
        return out


def _scrolls_progress_tracker(project_root: Path, data_summary: dict, experiments: dict, console: dict) -> dict:
    recent = experiments.get("recent", []) or []
    latest = experiments.get("latest") or (recent[0] if recent else None)
    latest_setup = latest.get("validation_setup", {}) if isinstance(latest, dict) else {}
    latest_mode = latest_setup.get("mode") or _scrolls_get_nested(latest.get("config", {}) if latest else {}, ("dataset", "validation_mode"), "unknown")
    latest_train = latest_setup.get("train_segment_id") or latest_setup.get("train_scroll_id")
    latest_val = latest_setup.get("val_segment_id") or latest_setup.get("val_scroll_id")

    def metric_value(run: dict) -> Optional[float]:
        if not isinstance(run, dict):
            return None
        metrics = run.get("metrics", {}) if isinstance(run.get("metrics"), dict) else {}
        value = metrics.get("val_f1", run.get("main_metric"))
        try:
            return float(value)
        except Exception:
            return None

    def is_real_run(run: dict) -> bool:
        try:
            text = json.dumps(run.get("config", {}), sort_keys=True).lower()
        except Exception:
            text = str(run.get("config", {})).lower()
        return not any(marker in text for marker in ("synthetic", "fake", "fallback"))

    def same_scope(run: dict) -> bool:
        setup = run.get("validation_setup", {}) if isinstance(run.get("validation_setup"), dict) else {}
        mode = setup.get("mode") or _scrolls_get_nested(run.get("config", {}), ("dataset", "validation_mode"), "unknown")
        train = setup.get("train_segment_id") or setup.get("train_scroll_id")
        val = setup.get("val_segment_id") or setup.get("val_scroll_id")
        if latest_mode and mode != latest_mode:
            return False
        if latest_train and train and train != latest_train:
            return False
        if latest_val and val and val != latest_val:
            return False
        return True

    comparable_desc = [r for r in recent if is_real_run(r) and same_scope(r) and metric_value(r) is not None]
    comparable = list(reversed(comparable_desc))
    baseline = comparable[0] if comparable else None
    best = max(comparable, key=lambda r: metric_value(r) or float("-inf"), default=None)
    latest_comparable = comparable[-1] if comparable else latest
    values = [metric_value(r) for r in comparable if metric_value(r) is not None]
    latest_value = metric_value(latest_comparable) if latest_comparable else None
    best_value = metric_value(best) if best else None
    baseline_value = metric_value(baseline) if baseline else None
    gain = (best_value - baseline_value) if best_value is not None and baseline_value is not None else None

    def ap_value(run: dict) -> Optional[float]:
        metrics = run.get("metrics", {}) if isinstance(run, dict) and isinstance(run.get("metrics"), dict) else {}
        try:
            return float(metrics.get("average_precision"))
        except Exception:
            return None

    def model_name(run: dict) -> Optional[str]:
        metrics = run.get("metrics", {}) if isinstance(run, dict) and isinstance(run.get("metrics"), dict) else {}
        value = metrics.get("model_name") or _scrolls_get_nested(run.get("config", {}) if isinstance(run, dict) else {}, ("model", "name"), None)
        return str(value) if value else None

    def model_family(run: dict) -> str:
        name = (model_name(run) or "unknown").lower()
        metrics = run.get("metrics", {}) if isinstance(run, dict) and isinstance(run.get("metrics"), dict) else {}
        if "torch" in name or metrics.get("torch_version") or metrics.get("device"):
            return "pytorch"
        if "numpy" in name:
            return "numpy"
        return "other"

    ap_runs = [r for r in comparable if ap_value(r) is not None]
    best_ap_run = max(ap_runs, key=lambda r: ap_value(r) or float("-inf"), default=None)
    baseline_ap = ap_value(baseline) if baseline else None
    latest_ap = ap_value(latest_comparable) if latest_comparable else None
    best_ap = ap_value(best_ap_run) if best_ap_run else None
    ap_gain = (best_ap - baseline_ap) if best_ap is not None and baseline_ap is not None else None
    family_counts: dict[str, int] = {}
    for run in comparable:
        family = model_family(run)
        family_counts[family] = family_counts.get(family, 0) + 1
    pytorch_runs = [r for r in comparable if model_family(r) == "pytorch"]
    best_pytorch_f1_run = max(pytorch_runs, key=lambda r: metric_value(r) or float("-inf"), default=None)
    best_pytorch_ap_run = max((r for r in pytorch_runs if ap_value(r) is not None), key=lambda r: ap_value(r) or float("-inf"), default=None)

    window = values[-8:]
    trend = "needs_more_evidence"
    trend_detail = "Need at least five comparable real runs."
    if len(window) >= 5:
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)
        stdev = variance ** 0.5
        first_half = window[:len(window) // 2]
        second_half = window[len(window) // 2:]
        first_mean = sum(first_half) / len(first_half)
        second_mean = sum(second_half) / len(second_half)
        delta = second_mean - first_mean
        noisy = stdev > 0.05 or (abs(mean) > 1e-12 and stdev / abs(mean) > 0.5)
        if noisy:
            trend = "noisy"
        elif delta > 0.02 and (abs(first_mean) < 1e-12 or delta / abs(first_mean) > 0.10):
            trend = "improving"
        elif delta < -0.02 and (abs(first_mean) < 1e-12 or abs(delta) / abs(first_mean) > 0.10):
            trend = "regressing"
        else:
            trend = "flat"
        trend_detail = f"Last {len(window)} comparable runs: mean {mean:.4f}, spread {stdev:.4f}, recent-window delta {delta:+.4f}."

    hypotheses = experiments.get("hypotheses", []) or []
    judged = [h for h in hypotheses if h.get("status") in {"improved", "regressed"}]
    improved = [h for h in judged if h.get("status") == "improved"]
    yield_rate = (len(improved) / len(judged)) if judged else None

    latest_metrics = latest_comparable.get("metrics", {}) if isinstance(latest_comparable, dict) and isinstance(latest_comparable.get("metrics"), dict) else {}
    precision = latest_metrics.get("precision")
    recall = latest_metrics.get("recall")
    pred_pos = latest_metrics.get("pred_positive_rate")
    val_pos = latest_metrics.get("val_positive_rate")
    sanity_warnings = []
    try:
        if float(precision) <= 0 or float(recall) <= 0:
            sanity_warnings.append("zero precision or recall")
    except Exception:
        sanity_warnings.append("precision/recall unavailable")
    try:
        ratio = float(pred_pos) / max(float(val_pos), 1e-12)
        if ratio > 4 or ratio < 0.25:
            sanity_warnings.append(f"prediction rate is {ratio:.1f}x validation ink rate")
    except Exception:
        pass
    sanity_status = "warning" if sanity_warnings else "ok"

    validation_ok = latest_mode in {"cross-segment", "cross-scroll"}
    data_items = _scrolls_prepared_datasets(project_root)
    has_real_data = any("synthetic" not in json.dumps(item.get("metadata", {}), default=str).lower() for item in data_items)
    has_artifacts = bool((latest_comparable or {}).get("artifacts"))
    cron_installed = bool((console.get("cron") or {}).get("installed"))
    lock_active = bool(console.get("lock_active"))

    milestones = [
        {"id": "real_data", "label": "Real labeled data", "state": "done" if has_real_data else "blocked", "detail": f"{len(data_items)} prepared metadata records"},
        {"id": "heldout", "label": "Held-out validation", "state": "done" if validation_ok else "warning", "detail": str(latest_mode or "unknown")},
        {"id": "baseline", "label": "Baseline established", "state": "done" if baseline else "pending", "detail": baseline.get("run_id") if baseline else "no comparable baseline run"},
        {"id": "experiments", "label": "Comparable runs", "state": "active" if comparable else "pending", "detail": f"{len(comparable)} runs on current scope"},
        {"id": "best_score", "label": "Best score found", "state": "done" if best else "pending", "detail": f"{model_name(best) or 'unknown'} · F1 {best_value:.4f}" if best_value is not None else "no score yet"},
        {"id": "sanity", "label": "Prediction sanity", "state": sanity_status, "detail": "; ".join(sanity_warnings) if sanity_warnings else "precision/recall nonzero"},
        {"id": "artifacts", "label": "Artifacts inspectable", "state": "done" if has_artifacts else "warning", "detail": "latest run artifacts available" if has_artifacts else "no artifacts listed"},
        {"id": "fallback", "label": "Cron fallback", "state": "done" if cron_installed else "warning", "detail": "installed" if cron_installed else "missing"},
    ]
    # This percent is scientific progress, not setup readiness. A +0.02 absolute
    # F1 lift is a meaningful early target for a focused pair; exceeding it
    # simply caps the bar while the raw gain remains visible.
    progress_target = 0.02
    progress_percent = 0
    if gain is not None:
        progress_percent = round(max(0.0, min(1.0, gain / progress_target)) * 100)
    foundation_weights = {"done": 1.0, "active": 0.75, "warning": 0.45, "pending": 0.15, "blocked": 0.0}
    foundation_readiness = round(100 * sum(foundation_weights.get(m["state"], 0) for m in milestones) / max(len(milestones), 1))
    gain_text = f"{gain:+.4f} F1" if gain is not None else "unknown gain"

    if lock_active:
        status = "running"
        label = "Research step running"
        next_action = "Watch the live console until a new run appears."
    elif not has_real_data:
        status = "blocked"
        label = "Needs real prepared data"
        next_action = "Prepare real labeled train/validation data before running more experiments."
    elif not validation_ok:
        status = "warning"
        label = "Validation is not trustworthy yet"
        next_action = "Use cross-segment or cross-scroll validation before judging progress."
    elif trend == "improving":
        status = "improving"
        label = f"Improving: {gain_text} vs baseline"
        next_action = "Exploit the latest winning changes with one focused follow-up."
    elif trend == "regressing":
        status = "regressing"
        label = f"Regressing recently: {gain_text} vs baseline"
        next_action = "Compare latest against best and backtrack the last change."
    elif trend == "noisy":
        status = "noisy"
        label = f"Noisy: {gain_text} vs baseline"
        next_action = "Repeat or narrow the experiment before trusting the direction."
    else:
        status = "flat"
        label = f"Flat/plateaued: {gain_text} vs baseline"
        next_action = "Do not just run forever; change one important variable or test a new focused validation pair."

    return {
        "summary": {
            "status": status,
            "label": label,
            "percent": progress_percent,
            "progress_target": progress_target,
            "foundation_readiness": foundation_readiness,
            "current_step": trend_detail,
            "next_action": next_action,
        },
        "scorecard": {
            "metric": "val_f1",
            "best": best_value,
            "baseline": baseline_value,
            "gain_vs_baseline": gain,
            "relative_gain_vs_baseline": (gain / baseline_value) if gain is not None and baseline_value not in (None, 0) else None,
            "latest": latest_value,
            "trend": trend,
            "best_average_precision": best_ap,
            "baseline_average_precision": baseline_ap,
            "latest_average_precision": latest_ap,
            "average_precision_gain": ap_gain,
            "best_average_precision_run_id": best_ap_run.get("run_id") if best_ap_run else None,
            "model_family_mix": family_counts,
            "best_model_name": model_name(best),
            "best_model_family": model_family(best) if best else None,
            "best_pytorch_f1": metric_value(best_pytorch_f1_run) if best_pytorch_f1_run else None,
            "best_pytorch_f1_run_id": best_pytorch_f1_run.get("run_id") if best_pytorch_f1_run else None,
            "best_pytorch_ap": ap_value(best_pytorch_ap_run) if best_pytorch_ap_run else None,
            "best_pytorch_ap_run_id": best_pytorch_ap_run.get("run_id") if best_pytorch_ap_run else None,
            "comparable_run_count": len(comparable),
            "best_run_id": best.get("run_id") if best else None,
            "latest_run_id": latest_comparable.get("run_id") if latest_comparable else None,
            "hypothesis_yield": yield_rate,
            "hypothesis_counts": {"improved": len(improved), "judged": len(judged)},
        },
        "sanity": {"status": sanity_status, "warnings": sanity_warnings, "precision": precision, "recall": recall, "pred_positive_rate": pred_pos, "val_positive_rate": val_pos},
        "signals": {"lock_active": lock_active, "cron_installed": cron_installed, "process_count": len(console.get("processes") or []), "validation_mode": latest_mode, "train": latest_train, "val": latest_val},
        "milestones": milestones,
    }


def _scrolls_cron_status(project_root: Path) -> dict:
    needle = f"cd {project_root}"
    try:
        proc = subprocess.run(["crontab", "-l"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        lines = proc.stdout.splitlines() if proc.returncode == 0 else []
        line = next((ln for ln in lines if needle in ln and "autoresearch.py" in ln), None)
        return {"installed": line is not None, "line": line}
    except Exception as exc:
        return {"installed": False, "line": None, "error": str(exc)}


def _scrolls_running_processes(project_root: Path, limit: int = 8) -> list[dict]:
    try:
        proc = subprocess.run(["ps", "-eo", "pid=,etimes=,command="], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    root_text = str(project_root)
    processes = []
    for line in proc.stdout.splitlines():
        raw = line.strip()
        if not raw or ("autoresearch.py" not in raw and "run_experiment.py" not in raw):
            continue
        if root_text not in raw and "vesuvius-autoresearch" not in raw:
            continue
        parts = raw.split(None, 2)
        if len(parts) < 3:
            continue
        pid, etimes, command = parts
        processes.append({
            "pid": pid,
            "age_seconds": int(etimes) if str(etimes).isdigit() else None,
            "command": command[:1000],
        })
        if len(processes) >= limit:
            break
    return processes


def _scrolls_improvement_loop_status() -> dict:
    try:
        mesh = get_self_improvement_cron_mesh()
    except Exception as exc:
        return {"available": False, "error": str(exc)}
    primary = None
    for job in mesh.get("self_improvement_jobs", []) or []:
        if job.get("id") == mesh.get("primary_job_id"):
            primary = job
            break
    if primary is None and mesh.get("self_improvement_jobs"):
        primary = mesh.get("self_improvement_jobs", [])[0]
    return {
        "available": True,
        "ok": bool(mesh.get("ok")),
        "primary_job": primary or {},
        "blockers": mesh.get("blockers", []) or [],
        "job_count": mesh.get("job_count", 0),
        "active_legacy_count": mesh.get("active_legacy_count", 0),
    }


def _scrolls_console_status(project_root: Path, lines: int = 160) -> dict:
    log_path = project_root / "logs" / "autoresearch.log"
    stat = None
    try:
        if log_path.exists():
            st = log_path.stat()
            stat = {"modified_at": st.st_mtime, "size_bytes": st.st_size}
    except Exception:
        stat = None
    return {
        "project_root": str(project_root),
        "lock_active": _scrolls_lock_active(project_root),
        "cron": _scrolls_cron_status(project_root),
        "processes": _scrolls_running_processes(project_root),
        "logs": {"path": str(log_path), "lines": _scrolls_tail(log_path, lines), "stat": stat},
        "improvement_loop": _scrolls_improvement_loop_status(),
        "timed_loop": _scrolls_timed_loop_status(),
        "generated_at": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
    }


def _scrolls_timed_loop_status() -> dict:
    with _SCROLLS_LOOP_LOCK:
        state = dict(_SCROLLS_LOOP_STATE)
    if state.get("deadline_at"):
        try:
            deadline = datetime.datetime.fromisoformat(str(state["deadline_at"]).replace("Z", "+00:00"))
            remaining = max(0.0, (deadline - datetime.datetime.now(datetime.timezone.utc)).total_seconds())
        except Exception:
            remaining = 0.0
    else:
        remaining = 0.0
    state["remaining_seconds"] = remaining
    return state


def _scrolls_set_loop_state(**updates) -> None:
    with _SCROLLS_LOOP_LOCK:
        _SCROLLS_LOOP_STATE.update(updates)


def _scrolls_append_loop_log(project_root: Path, message: str) -> None:
    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with (logs_dir / "autoresearch.log").open("a", encoding="utf-8") as fh:
        fh.write(f"\n[{stamp}] timed-loop: {message}\n")


def _scrolls_timed_loop_worker(project_root: Path, duration_minutes: int) -> None:
    started = datetime.datetime.now(datetime.timezone.utc)
    deadline = started + datetime.timedelta(minutes=duration_minutes)
    _SCROLLS_LOOP_STOP.clear()
    _scrolls_set_loop_state(
        active=True,
        started_at=started.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        deadline_at=deadline.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        duration_minutes=duration_minutes,
        iterations=0,
        current_pid=None,
        last_returncode=None,
        last_error=None,
        status="running",
    )
    _scrolls_append_loop_log(project_root, f"started supervised autonomous loop for {duration_minutes} minute(s)")
    try:
        while not _SCROLLS_LOOP_STOP.is_set() and datetime.datetime.now(datetime.timezone.utc) < deadline:
            if _scrolls_lock_active(project_root):
                _scrolls_set_loop_state(status="waiting_for_current_run")
                time.sleep(5)
                continue
            remaining = (deadline - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
            if remaining <= 0:
                break
            logs_dir = project_root / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            log_path = logs_dir / "autoresearch.log"
            _scrolls_append_loop_log(project_root, "starting autoresearch iteration")
            with log_path.open("ab") as log_fh:
                proc = subprocess.Popen([_scrolls_python(project_root), "autoresearch.py"], cwd=str(project_root), stdout=log_fh, stderr=subprocess.STDOUT, start_new_session=True)
                _scrolls_set_loop_state(status="iteration_running", current_pid=proc.pid)
                returncode = proc.wait()
            with _SCROLLS_LOOP_LOCK:
                iterations = int(_SCROLLS_LOOP_STATE.get("iterations") or 0) + 1
            _scrolls_set_loop_state(iterations=iterations, current_pid=None, last_returncode=returncode, status="running")
            _scrolls_append_loop_log(project_root, f"finished iteration {iterations} with returncode {returncode}")
            if returncode != 0:
                _scrolls_set_loop_state(last_error=f"autoresearch.py exited {returncode}")
                time.sleep(10)
            else:
                time.sleep(2)
    except Exception as exc:
        _scrolls_set_loop_state(last_error=str(exc), status="error")
        _scrolls_append_loop_log(project_root, f"error: {exc}")
    finally:
        stopped = _SCROLLS_LOOP_STOP.is_set()
        _scrolls_set_loop_state(active=False, current_pid=None, status="stopped" if stopped else "complete")
        _scrolls_append_loop_log(project_root, "stopped by operator" if stopped else "time budget complete")


async def get_scrolls_research_endpoint(request):
    project_root = _SCROLLS_PROJECT_ROOT
    console = _scrolls_console_status(project_root, lines=100)
    data_summary = _scrolls_data_summary(project_root)
    experiments = _scrolls_experiments(project_root)
    return JSONResponse({
        "project_root": str(project_root),
        "exists": project_root.exists(),
        "data_summary": data_summary,
        "prepared_datasets": _scrolls_prepared_datasets(project_root),
        "configs": _scrolls_configs(project_root),
        "autoresearch_inventory": _scrolls_autoresearch_inventory(project_root),
        "experiments": experiments,
        "progress_tracker": _scrolls_progress_tracker(project_root, data_summary, experiments, console),
        "cron": console["cron"],
        "logs": console["logs"],
        "processes": console["processes"],
        "improvement_loop": console["improvement_loop"],
        "timed_loop": console["timed_loop"],
        "lock_active": console["lock_active"],
    })


async def get_scrolls_console_endpoint(request):
    return JSONResponse(_scrolls_console_status(_SCROLLS_PROJECT_ROOT))


async def get_scrolls_loop_status_endpoint(request):
    return JSONResponse(_scrolls_timed_loop_status())


async def get_scrolls_artifact_endpoint(request):
    try:
        return JSONResponse(_scrolls_artifact_preview(_SCROLLS_PROJECT_ROOT, request.query_params.get("path", "")))
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


def _scrolls_spawn(command: list[str], project_root: Path):
    if not project_root.exists():
        return JSONResponse({"error": f"Scrolls project not found: {project_root}"}, status_code=404)
    if _scrolls_lock_active(project_root):
        return JSONResponse({"error": "AutoResearch is already running"}, status_code=409)
    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "autoresearch.log"
    with log_path.open("ab") as log_fh:
        proc = subprocess.Popen(command, cwd=str(project_root), stdout=log_fh, stderr=subprocess.STDOUT, start_new_session=True)
    return JSONResponse({"ok": True, "pid": proc.pid, "command": command, "log_path": str(log_path)})


async def trigger_scrolls_autoresearch_endpoint(request):
    return _scrolls_spawn([_scrolls_python(_SCROLLS_PROJECT_ROOT), "autoresearch.py"], _SCROLLS_PROJECT_ROOT)


async def start_scrolls_timed_loop_endpoint(request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        minutes = int(body.get("minutes", 15))
    except Exception:
        minutes = 15
    minutes = max(1, min(minutes, 240))
    with _SCROLLS_LOOP_LOCK:
        active = bool(_SCROLLS_LOOP_STATE.get("active"))
    if active:
        return JSONResponse({"error": "Timed AutoResearch loop is already active", "timed_loop": _scrolls_timed_loop_status()}, status_code=409)
    if not _SCROLLS_PROJECT_ROOT.exists():
        return JSONResponse({"error": f"Scrolls project not found: {_SCROLLS_PROJECT_ROOT}"}, status_code=404)
    thread = threading.Thread(target=_scrolls_timed_loop_worker, args=(_SCROLLS_PROJECT_ROOT, minutes), daemon=True)
    thread.start()
    time.sleep(0.05)
    return JSONResponse({"ok": True, "timed_loop": _scrolls_timed_loop_status()})


async def stop_scrolls_timed_loop_endpoint(request):
    _SCROLLS_LOOP_STOP.set()
    _scrolls_set_loop_state(status="stopping")
    _scrolls_append_loop_log(_SCROLLS_PROJECT_ROOT, "stop requested; current iteration will finish before exit")
    return JSONResponse({"ok": True, "timed_loop": _scrolls_timed_loop_status()})


async def run_scrolls_experiment_endpoint(request):
    try:
        body = await request.json()
        config_name = _scrolls_safe_config_name(body.get("config", ""))
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    config_path = _SCROLLS_PROJECT_ROOT / "configs" / config_name
    if not config_path.exists():
        return JSONResponse({"error": f"Config not found: {config_name}"}, status_code=404)
    return _scrolls_spawn([_scrolls_python(_SCROLLS_PROJECT_ROOT), "run_experiment.py", "--config", str(config_path)], _SCROLLS_PROJECT_ROOT)


def _truncate_update_output(text: str, limit: int = 12000) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit // 2] + "\n... output truncated ...\n" + text[-limit // 2 :]


def _run_dashboard_update_command(args: list[str], cwd: Path, timeout: int = 120) -> dict:
    started = time.time()
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": " ".join(args),
            "returncode": proc.returncode,
            "stdout": _truncate_update_output(proc.stdout),
            "stderr": _truncate_update_output(proc.stderr),
            "duration_seconds": round(time.time() - started, 3),
        }
    except FileNotFoundError as exc:
        return {
            "command": " ".join(args),
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc),
            "duration_seconds": round(time.time() - started, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": " ".join(args),
            "returncode": 124,
            "stdout": _truncate_update_output(exc.stdout or ""),
            "stderr": _truncate_update_output(exc.stderr or f"Timed out after {timeout}s"),
            "duration_seconds": round(time.time() - started, 3),
        }


def _dashboard_auto_update(allow_dirty: bool = False, install_dependencies: bool = True) -> tuple[int, dict]:
    root = DASHBOARD_REPO_ROOT
    if not root.exists():
        return 404, {"ok": False, "error": f"Dashboard directory not found: {root}"}
    if not (root / ".git").exists():
        return 400, {"ok": False, "error": f"Dashboard directory is not a git checkout: {root}"}

    steps: list[dict] = []

    def run(args: list[str], timeout: int = 120) -> dict:
        result = _run_dashboard_update_command(args, root, timeout=timeout)
        steps.append(result)
        return result

    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], timeout=15)
    if branch["returncode"] != 0:
        return 500, {"ok": False, "error": "Could not read dashboard git branch", "root": str(root), "steps": steps}

    before = run(["git", "rev-parse", "HEAD"], timeout=15)
    if before["returncode"] != 0:
        return 500, {"ok": False, "error": "Could not read current dashboard commit", "root": str(root), "steps": steps}

    status = run(["git", "status", "--porcelain"], timeout=15)
    if status["returncode"] != 0:
        return 500, {"ok": False, "error": "Could not check dashboard working tree status", "root": str(root), "steps": steps}
    dirty_files = [line for line in status["stdout"].splitlines() if line.strip()]
    if dirty_files and not allow_dirty:
        return 409, {
            "ok": False,
            "error": "Dashboard has local changes; refusing to auto-update until they are committed, stashed, or discarded.",
            "root": str(root),
            "branch": branch["stdout"].strip(),
            "dirty_files": dirty_files[:100],
            "steps": steps,
        }

    fetch = run(["git", "fetch", "--prune", "origin"], timeout=60)
    if fetch["returncode"] != 0:
        return 502, {"ok": False, "error": "Could not fetch dashboard updates from origin", "root": str(root), "steps": steps}

    pull = run(["git", "pull", "--ff-only"], timeout=120)
    if pull["returncode"] != 0:
        return 409, {
            "ok": False,
            "error": "Fast-forward update failed; manual merge/rebase is required.",
            "root": str(root),
            "steps": steps,
        }

    dependency_step = None
    requirements = root / "requirements.txt"
    if install_dependencies and requirements.exists():
        dependency_step = run([sys.executable, "-m", "pip", "install", "-r", str(requirements)], timeout=240)
        if dependency_step["returncode"] != 0:
            return 500, {
                "ok": False,
                "error": "Dashboard code updated, but dependency installation failed.",
                "root": str(root),
                "steps": steps,
                "restart_required": True,
            }

    after = run(["git", "rev-parse", "HEAD"], timeout=15)
    if after["returncode"] != 0:
        return 500, {"ok": False, "error": "Update finished but could not read new commit", "root": str(root), "steps": steps}

    before_commit = before["stdout"].strip()
    after_commit = after["stdout"].strip()
    updated = before_commit != after_commit
    return 200, {
        "ok": True,
        "root": str(root),
        "branch": branch["stdout"].strip(),
        "before": before_commit,
        "after": after_commit,
        "updated": updated,
        "restart_required": updated,
        "dependencies_installed": bool(dependency_step and dependency_step["returncode"] == 0),
        "message": "Dashboard updated. Restart the dashboard process, then reload the page." if updated else "Dashboard is already up to date.",
        "steps": steps,
    }


async def dashboard_auto_update_endpoint(request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    allow_dirty = bool(body.get("allow_dirty", False)) if isinstance(body, dict) else False
    install_dependencies = bool(body.get("install_dependencies", True)) if isinstance(body, dict) else True
    status_code, payload = await asyncio.to_thread(_dashboard_auto_update, allow_dirty, install_dependencies)
    return JSONResponse(payload, status_code=status_code)



def _sanitize_dashboard_chat_identity_token(value: str | None, fallback: str, max_len: int = 32) -> str:
    token = re.sub(r"[^A-Za-z0-9_`^{}\[\]|.-]", "", (value or "").strip())[:max_len]
    if not token or not re.match(r"^[A-Za-z_`^{}\[\]|]", token):
        token = fallback[:max_len]
    return token


def _dashboard_chat_runtime_config() -> dict[str, Any]:
    effective_config = get_config()
    cfg = (effective_config.get("dashboard_chat") or {}) if isinstance(effective_config, dict) else {}
    hosts_value = os.getenv("DASHBOARD_CHAT_IRC_HOSTS") or cfg.get("hosts") or DASHBOARD_CHAT_IRC_HOSTS
    if isinstance(hosts_value, str):
        hosts = [host.strip() for host in hosts_value.split(",") if host.strip()]
    elif isinstance(hosts_value, list):
        hosts = [str(host).strip() for host in hosts_value if str(host).strip()]
    else:
        hosts = DASHBOARD_CHAT_IRC_HOSTS
    port = int(os.getenv("DASHBOARD_CHAT_IRC_PORT") or cfg.get("port") or DASHBOARD_CHAT_IRC_PORT)
    tls_raw = os.getenv("DASHBOARD_CHAT_IRC_TLS")
    tls = DASHBOARD_CHAT_IRC_TLS if tls_raw is None else tls_raw.lower() not in {"0", "false", "no", "off"}
    if tls_raw is None and "tls" in cfg:
        tls = bool(cfg.get("tls"))
    return {
        "hosts": hosts or DASHBOARD_CHAT_IRC_HOSTS,
        "port": port,
        "tls": tls,
        "channel": DASHBOARD_CHAT_CHANNEL,
        "channel_key": os.getenv("DASHBOARD_CHAT_CHANNEL_KEY") or cfg.get("channel_key") or DASHBOARD_CHAT_CHANNEL_KEY,
        "default_nick_prefix": _sanitize_dashboard_chat_identity_token(
            cfg.get("default_nick_prefix"), DASHBOARD_CHAT_DEFAULT_NICK_PREFIX, 18
        ),
        "ident": _sanitize_dashboard_chat_identity_token(
            cfg.get("ident"), DASHBOARD_CHAT_DEFAULT_IDENT, 16
        ),
        "realname": str(cfg.get("realname") or DASHBOARD_CHAT_DEFAULT_REALNAME).replace("\r", " ").replace("\n", " ")[:64],
    }


def _sanitize_dashboard_chat_nick(value: str | None, prefix: str | None = None) -> str:
    nick = re.sub(r"[^A-Za-z0-9_`^{}\[\]|-]", "", (value or "").strip())[:24]
    if not nick or not re.match(r"^[A-Za-z_`^{}\[\]|-]", nick):
        safe_prefix = _sanitize_dashboard_chat_identity_token(prefix, DASHBOARD_CHAT_DEFAULT_NICK_PREFIX, 18)
        nick = safe_prefix + uuid.uuid4().hex[:6]
    return nick


def _dashboard_chat_user_command(nick: str, config: dict[str, Any] | None = None) -> str:
    cfg = config or _dashboard_chat_runtime_config()
    ident = _sanitize_dashboard_chat_identity_token(cfg.get("ident"), DASHBOARD_CHAT_DEFAULT_IDENT, 16)
    realname = str(cfg.get("realname") or DASHBOARD_CHAT_DEFAULT_REALNAME).replace("\r", " ").replace("\n", " ")[:64]
    return f"USER {ident} 0 * :{realname}"


def _dashboard_chat_truncate_message(value: str | None) -> str:
    message = (value or "").replace("\r", " ").replace("\n", " ").strip()
    return message[:DASHBOARD_CHAT_MAX_MESSAGE_CHARS]


def _sanitize_dashboard_chat_pm_target(value: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9_`^{}\[\]|-]", "", (value or "").strip())[:24]


def _parse_irc_prefix(line: str) -> tuple[str, str, str]:
    prefix = ""
    command = ""
    rest = line
    if rest.startswith(":"):
        prefix, _, rest = rest[1:].partition(" ")
    command, _, rest = rest.partition(" ")
    return prefix, command.upper(), rest


def _parse_irc_message(line: str, current_nick: str | None = None) -> dict[str, Any] | None:
    prefix, command, rest = _parse_irc_prefix(line)
    nick = prefix.split("!", 1)[0] if prefix else "server"
    if command == "PRIVMSG":
        target, _, body = rest.partition(" :")
        if target == DASHBOARD_CHAT_CHANNEL:
            return {"type": "message", "scope": "channel", "nick": nick, "text": body}
        payload = {"type": "message", "scope": "pm", "nick": nick, "target": target, "text": body}
        if current_nick and nick == current_nick:
            payload["self"] = True
        return payload
    if command == "NOTICE":
        _target, _, body = rest.partition(" :")
        return {"type": "notice", "nick": nick, "text": body or rest}
    if command == "JOIN":
        channel = rest.lstrip(":").strip()
        if channel == DASHBOARD_CHAT_CHANNEL:
            return {"type": "presence", "action": "join", "nick": nick}
    if command == "PART":
        channel = rest.split(" ", 1)[0]
        if channel == DASHBOARD_CHAT_CHANNEL:
            return {"type": "presence", "action": "part", "nick": nick}
    if command == "QUIT":
        return {"type": "presence", "action": "quit", "nick": nick}
    if command == "NICK":
        new_nick = rest.lstrip(":").strip()
        if new_nick:
            return {"type": "presence", "action": "nick", "nick": nick, "new_nick": new_nick}
    if command == "353":
        _before, _, names = rest.partition(" :")
        return {"type": "names", "names": [name.lstrip("@+%&~") for name in names.split() if name]}
    if command == "433":
        return {"type": "error", "text": "Nickname is already in use. Pick another nick and reconnect."}
    if command in {"471", "473", "474", "475"}:
        return {"type": "error", "text": "Unable to join #hermesdashboard with the dashboard channel key."}
    return None


def _dashboard_chat_status_payload() -> dict[str, Any]:
    cfg = _dashboard_chat_runtime_config()
    return {
        "channel": cfg["channel"],
        "hosts": cfg["hosts"],
        "port": cfg["port"],
        "tls": cfg["tls"],
        "default_nick_prefix": cfg["default_nick_prefix"],
        "ident": cfg["ident"],
        "realname": cfg["realname"],
        "channel_key_configured": bool(cfg["channel_key"]),
        "jail": "channel-only plus PMs to users present in #hermesdashboard; arbitrary JOIN/RAW commands are blocked by the dashboard proxy",
    }


async def dashboard_chat_status_endpoint(request):
    return JSONResponse(_dashboard_chat_status_payload())


async def dashboard_chat_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    chat_cfg = _dashboard_chat_runtime_config()
    nick = _sanitize_dashboard_chat_nick(
        websocket.query_params.get("nick") if hasattr(websocket, "query_params") else None,
        chat_cfg["default_nick_prefix"],
    )
    reader = writer = None
    connected_host = None

    async def send_client(payload: dict[str, Any]) -> None:
        try:
            await websocket.send_text(json.dumps(payload))
        except Exception:
            pass

    async def send_irc(command: str) -> None:
        if writer is None:
            return
        writer.write((command + "\r\n").encode("utf-8", "ignore"))
        await writer.drain()

    try:
        last_error = None
        for host in chat_cfg["hosts"]:
            try:
                reader, writer = await asyncio.open_connection(
                    host,
                    chat_cfg["port"],
                    ssl=chat_cfg["tls"],
                )
                connected_host = host
                break
            except Exception as exc:
                last_error = exc
        if reader is None or writer is None:
            await send_client({"type": "error", "text": f"IRC connection failed: {last_error}"})
            await websocket.close()
            return

        await send_client({"type": "status", "state": "connecting", "nick": nick, "channel": chat_cfg["channel"], "host": connected_host})
        await send_irc(f"NICK {nick}")
        await send_irc(_dashboard_chat_user_command(nick, chat_cfg))

        registered = False
        join_sent = False
        joined = False
        allowed_pm_targets: set[str] = set()

        async def send_join_once() -> None:
            nonlocal join_sent
            if join_sent:
                return
            join_sent = True
            if chat_cfg["channel_key"]:
                await send_irc(f"JOIN {chat_cfg['channel']} {chat_cfg['channel_key']}")
            else:
                await send_irc(f"JOIN {chat_cfg['channel']}")
            await send_client({"type": "status", "state": "joining", "nick": nick, "channel": chat_cfg["channel"], "host": connected_host})

        async def mark_joined() -> None:
            nonlocal joined
            if joined:
                return
            joined = True
            await send_client({"type": "status", "state": "joined", "nick": nick, "channel": chat_cfg["channel"], "host": connected_host, "text": f"Joined {chat_cfg['channel']}."})

        async def irc_to_ws() -> None:
            nonlocal registered, nick
            while True:
                raw = await reader.readline()
                if not raw:
                    await send_client({"type": "status", "state": "disconnected", "text": "IRC server closed the connection."})
                    break
                line = raw.decode("utf-8", "ignore").rstrip("\r\n")
                if line.startswith("PING "):
                    await send_irc("PONG " + line.split(" ", 1)[1])
                    continue
                prefix, command, rest = _parse_irc_prefix(line)
                if command == "001":
                    registered = True
                    # 001 RPL_WELCOME means the NICK/USER registration handshake is complete.
                    # Only now JOIN the keyed channel; do not pretend the browser joined until
                    # the server sends our JOIN echo or end-of-NAMES (366).
                    parts = rest.split(" ", 1)
                    if parts and parts[0]:
                        nick = parts[0]
                    await send_client({"type": "status", "state": "registered", "nick": nick, "channel": chat_cfg["channel"], "host": connected_host})
                    await send_join_once()
                    continue
                if command in {"376", "422"} and registered:
                    await send_join_once()
                if command == "366" and chat_cfg["channel"] in rest:
                    await mark_joined()
                parsed = _parse_irc_message(line, current_nick=nick)
                if parsed:
                    if parsed.get("type") == "names":
                        allowed_pm_targets.clear()
                        allowed_pm_targets.update(
                            target for target in (_sanitize_dashboard_chat_pm_target(name) for name in parsed.get("names", []))
                            if target and target != nick
                        )
                    elif parsed.get("type") == "presence":
                        action = parsed.get("action")
                        parsed_nick = _sanitize_dashboard_chat_pm_target(parsed.get("nick"))
                        if action == "join":
                            if parsed_nick == nick:
                                await mark_joined()
                            elif parsed_nick:
                                allowed_pm_targets.add(parsed_nick)
                        elif action in {"part", "quit"} and parsed_nick:
                            allowed_pm_targets.discard(parsed_nick)
                        elif action == "nick" and parsed_nick:
                            new_target = _sanitize_dashboard_chat_pm_target(parsed.get("new_nick"))
                            allowed_pm_targets.discard(parsed_nick)
                            if parsed_nick == nick and new_target:
                                nick = new_target
                                await send_client({"type": "status", "state": "nick", "nick": nick})
                            elif new_target:
                                allowed_pm_targets.add(new_target)
                    await send_client(parsed)

        async def ws_to_irc() -> None:
            nonlocal nick
            while True:
                text = await websocket.receive_text()
                try:
                    data = json.loads(text)
                except Exception:
                    data = {"type": "say", "text": text}
                kind = data.get("type")
                if kind == "say":
                    message = _dashboard_chat_truncate_message(data.get("text"))
                    if message:
                        if not joined:
                            await send_client({"type": "error", "text": "Still joining IRC; wait for the server-confirmed #hermesdashboard join."})
                            continue
                        await send_irc(f"PRIVMSG {chat_cfg['channel']} :{message}")
                        # Most IRCds do not echo a channel PRIVMSG back to its sender, so
                        # provide a local echo after writing the IRC command successfully.
                        await send_client({"type": "message", "scope": "channel", "nick": nick, "text": message, "self": True})
                elif kind == "selfpm":
                    message = _dashboard_chat_truncate_message(data.get("text"))
                    if message:
                        if not registered:
                            await send_client({"type": "error", "text": "Still registering with IRC; try again in a moment."})
                            continue
                        await send_irc(f"PRIVMSG {nick} :{message}")
                        await send_client({"type": "message", "scope": "pm", "nick": nick, "target": nick, "text": message, "self": True})
                elif kind == "pm":
                    message = _dashboard_chat_truncate_message(data.get("text"))
                    target = _sanitize_dashboard_chat_pm_target(data.get("target"))
                    if message and target:
                        if not joined:
                            await send_client({"type": "error", "text": "Join #hermesdashboard before sending private messages."})
                            continue
                        if target != nick and target not in allowed_pm_targets:
                            await send_client({"type": "error", "text": "PM target must be your own nick or a user currently visible in #hermesdashboard."})
                            continue
                        await send_irc(f"PRIVMSG {target} :{message}")
                        await send_client({"type": "message", "scope": "pm", "nick": nick, "target": target, "text": message, "self": True})
                elif kind == "nick":
                    new_nick = _sanitize_dashboard_chat_nick(data.get("nick"))
                    nick = new_nick
                    await send_irc(f"NICK {new_nick}")
                    await send_client({"type": "status", "state": "nick", "nick": new_nick})
                elif kind == "ping":
                    await send_client({"type": "pong"})
                else:
                    await send_client({"type": "error", "text": "Unsupported command. Dashboard chat is jailed to #hermesdashboard and self-PM only."})

        tasks = [asyncio.create_task(irc_to_ws()), asyncio.create_task(ws_to_irc())]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            task.result()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        await send_client({"type": "error", "text": str(exc)})
    finally:
        if writer is not None:
            try:
                await send_irc(f"PART {chat_cfg['channel']} :Hermes Dashboard disconnect")
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

routes = [
    Route("/", homepage),
    # Campaigns is implemented as a hash-routed dashboard panel (#dnd), but
    # users/bookmarks can land on path-style URLs after navigation or refresh.
    # Serve the SPA shell for those aliases so the browser can load the panel
    # instead of returning a route-level 404 before frontend code runs.
    Route("/dnd", homepage),
    Route("/dnd/", homepage),
    Route("/dnd/popout", homepage),
    Route("/campaigns", homepage),
    Route("/campaigns/", homepage),
    Route("/chat", chat_stream, methods=["POST"]),
    Route("/api/dashboard-state/{key}", get_dashboard_state),
    Route("/api/dashboard-state/{key}", set_dashboard_state, methods=["PUT"]),
    Route("/api/dashboard-state/{key}", delete_dashboard_state, methods=["DELETE"]),
    Route("/api/dashboard/update", dashboard_auto_update_endpoint, methods=["POST"]),
    Route("/api/dashboard-chat/status", dashboard_chat_status_endpoint),
    Route("/health", health),
    Route("/api/status", get_status),
    Route("/api/config", get_config_endpoint),
    Route("/api/settings", get_settings),
    Route("/api/config", update_config, methods=["POST"]),
    Route("/api/models", get_models),
    Route("/api/personalities", get_personalities),
    Route("/api/personality", set_personality, methods=["POST"]),
    Route("/api/model", set_model, methods=["POST"]),
    Route("/api/agent-observability", get_agent_observability_endpoint),
    Route("/api/sessions", get_sessions),
    Route("/api/sessions/search", search_sessions),
    Route("/api/sessions/sources", get_session_sources),
    Route(
        "/api/sessions/backfill-summaries",
        backfill_session_summaries_endpoint,
        methods=["POST"],
    ),
    Route(
        "/api/sessions/{session_id}/summary",
        regenerate_session_summary_endpoint,
        methods=["POST"],
    ),
    Route("/api/sessions/{session_id}", get_session),
    Route("/api/sessions/{session_id}/files", get_session_files),
    Route("/api/sessions/{session_id}/tokens", get_session_tokens),
    Route("/api/sessions/{session_id}/stream", session_stream),
    Route(
        "/api/sessions/{session_id}/interrupt",
        interrupt_session,
        methods=["POST"],
    ),
    Route("/api/sessions/{session_id}", delete_session, methods=["DELETE"]),
    Route("/api/message-board", get_message_board_posts_endpoint),
    Route("/api/message-board", create_message_board_post_endpoint, methods=["POST"]),
    Route(
        "/api/message-board/{post_id}/messages",
        create_message_board_message_endpoint,
        methods=["POST"],
    ),
    Route("/api/message-board/{post_id}", get_message_board_post_endpoint),
    Route("/api/files/content", get_file_content),
    Route("/api/memory", get_memory),
    Route("/api/memory", update_memory, methods=["POST"]),
    Route("/api/skills", get_skills),
    Route("/api/skills/toggle", toggle_skill, methods=["POST"]),
    Route("/api/skills/{skill_id}/content", get_skill_content),
    Route("/api/games", get_games_endpoint),
    Route("/api/games/{game_id}/content", get_game_content_endpoint),
    Route("/api/pokemon/restart", restart_pokemon_endpoint, methods=["POST"]),
    Route("/api/diagnostics/context", diagnostics_context_endpoint),
    Route("/api/dnd/campaigns", dnd_campaigns_endpoint, methods=["GET", "POST"]),
    Route("/api/dnd/schemas", dnd_schemas_endpoint),
    Route("/api/dnd/campaigns/{campaign_id}", dnd_campaign_detail_endpoint),
    Route("/api/dnd/campaigns/{campaign_id}/players", create_dnd_player_endpoint, methods=["POST"]),
    Route("/api/dnd/campaigns/{campaign_id}/characters", dnd_characters_endpoint, methods=["GET", "POST"]),
    Route("/api/dnd/campaigns/{campaign_id}/characters/generate", dnd_character_generate_endpoint, methods=["POST"]),
    Route("/api/dnd/campaigns/{campaign_id}/world/entities", dnd_world_entities_endpoint, methods=["GET", "POST"]),
    Route("/api/dnd/campaigns/{campaign_id}/world/generate", dnd_world_generate_endpoint, methods=["POST"]),
    Route("/api/dnd/campaigns/{campaign_id}/turns/auto", dnd_auto_turn_endpoint, methods=["POST"]),
    Route("/api/dnd/campaigns/{campaign_id}/turns/auto/jobs", dnd_auto_turn_job_start_endpoint, methods=["POST"]),
    Route("/api/dnd/campaigns/{campaign_id}/turns/auto/jobs/{job_id}", dnd_auto_turn_job_status_endpoint),
    Route("/api/dnd/campaigns/{campaign_id}/scene", dnd_campaign_scene_endpoint, methods=["PATCH", "POST"]),
    Route("/api/dnd/campaigns/{campaign_id}/dice", dnd_dice_roll_endpoint, methods=["POST"]),
    Route("/api/dnd/campaigns/{campaign_id}/events", dnd_campaign_events_endpoint, methods=["GET", "POST"]),
    Route("/doom/", doom_watch_proxy_endpoint, methods=["GET", "POST"]),
    Route("/doom/{path:path}", doom_watch_proxy_endpoint, methods=["GET", "POST"]),
    Route("/minihack/", minihack_watch_proxy_endpoint, methods=["GET", "POST"]),
    Route("/minihack/{path:path}", minihack_watch_proxy_endpoint, methods=["GET", "POST"]),
    Route("/pokemon/chat", chat_stream, methods=["POST"]),
    Route("/pokemon/api/diagnostics/context", diagnostics_context_endpoint),
    Route("/pokemon/", pokemon_proxy_endpoint, methods=["GET", "POST"]),
    Route("/pokemon/{path:path}", pokemon_proxy_endpoint, methods=["GET", "POST"]),
    Route("/api/self-improvement", get_self_improvement_endpoint),
    Route("/api/autonomous-development", get_autonomous_development_endpoint),
    Route("/api/scrolls/research", get_scrolls_research_endpoint),
    Route("/api/scrolls/console", get_scrolls_console_endpoint),
    Route("/api/scrolls/loop/status", get_scrolls_loop_status_endpoint),
    Route("/api/scrolls/artifact", get_scrolls_artifact_endpoint),
    Route("/api/scrolls/autoresearch/trigger", trigger_scrolls_autoresearch_endpoint, methods=["POST"]),
    Route("/api/scrolls/autoresearch/loop/start", start_scrolls_timed_loop_endpoint, methods=["POST"]),
    Route("/api/scrolls/autoresearch/loop/stop", stop_scrolls_timed_loop_endpoint, methods=["POST"]),
    Route("/api/scrolls/experiments/run", run_scrolls_experiment_endpoint, methods=["POST"]),
    Route("/api/autonomous-development/pipelines", create_autonomous_development_pipeline_endpoint, methods=["POST"]),
    Route("/api/autonomous-development/pipelines/{pipeline_id}", update_autonomous_development_pipeline_endpoint, methods=["PATCH"]),
    Route("/api/autonomous-development/pipelines/{pipeline_id}/control", control_autonomous_development_pipeline_endpoint, methods=["POST"]),
    Route("/api/self-improvement/runs", get_self_improvement_runs_endpoint),
    Route("/api/self-improvement/candidates", get_self_improvement_candidates_endpoint),
    Route("/api/self-improvement/candidates", create_self_improvement_candidate_endpoint, methods=["POST"]),
    Route("/api/self-improvement/candidates/select", select_self_improvement_candidate_endpoint, methods=["POST"]),
    Route("/api/self-improvement/control", control_self_improvement_endpoint, methods=["POST"]),
    Route("/api/cron", get_cron_jobs),
    Route("/api/cron", create_cron_job, methods=["POST"]),
    Route("/api/cron/schedule", get_cron_schedule),
    Route("/api/cron/{job_id}", update_cron_job, methods=["PATCH"]),
    Route("/api/cron/{job_id}", delete_cron_job, methods=["DELETE"]),
    Route("/api/cron/{job_id}/pause", pause_cron_job, methods=["POST"]),
    Route("/api/cron/{job_id}/resume", resume_cron_job, methods=["POST"]),
    Route("/api/cron/{job_id}/run", run_cron_job, methods=["POST"]),
    Route("/api/secrets", get_secrets),
    Route("/api/secrets", set_secret, methods=["POST"]),
    Route("/api/secrets/{key}", delete_secret, methods=["DELETE"]),
    Route("/api/graph", get_graph_data),
]

if WebSocketRoute is not None:
    routes.insert(-1, WebSocketRoute("/api/dashboard-chat/ws", dashboard_chat_websocket_endpoint, name="dashboard_chat_ws"))
    routes.insert(-1, WebSocketRoute("/pokemon/ws", pokemon_websocket_proxy_endpoint, name="pokemon_ws"))
    routes.insert(-1, WebSocketRoute("/pokemon/watch/ws", pokemon_websocket_proxy_endpoint, name="pokemon_watch_ws"))

app = Starlette(routes=routes, lifespan=_lifespan)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=DASHBOARD_PORT)
