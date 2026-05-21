import asyncio
import datetime
import importlib.util
import json
import os
import re
import sys
import sqlite3
import threading
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import httpx
import yaml
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.templating import Jinja2Templates
from starlette.responses import JSONResponse, PlainTextResponse
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
        content = str(msg.get("content") or "")
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
            content = str(msg.get("content", "") or "")
            preview.append(
                {
                    "role": role,
                    "content": content[:120],
                    "len": len(content),
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
POKEMON_SERVER_URL = os.getenv("HERMES_POKEMON_SERVER_URL", "http://127.0.0.1:9879")


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
        content_type_header = request.headers.get("content-type")
        if content_type_header:
            headers["content-type"] = content_type_header
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
                }
            )
            if len(runs) >= limit:
                break
    return {"runs": runs, "count": len(runs)}


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
    risk_value = str(candidate.get("risk") or "medium").lower()
    risk_penalty = {"low": 0.5, "medium": 1.5, "high": 3.0}.get(risk_value, 1.5)
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


def get_self_improvement_status() -> dict:
    cron_mesh = get_self_improvement_cron_mesh()
    drift = get_self_improvement_drift_status()
    return {
        "ledger": get_self_improvement_ledger(),
        "queue": list_self_improvement_candidates(),
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


routes = [
    Route("/", homepage),
    Route("/chat", chat_stream, methods=["POST"]),
    Route("/health", health),
    Route("/api/status", get_status),
    Route("/api/config", get_config_endpoint),
    Route("/api/settings", get_settings),
    Route("/api/config", update_config, methods=["POST"]),
    Route("/api/models", get_models),
    Route("/api/personalities", get_personalities),
    Route("/api/personality", set_personality, methods=["POST"]),
    Route("/api/model", set_model, methods=["POST"]),
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
    Route("/doom/", doom_watch_proxy_endpoint, methods=["GET", "POST"]),
    Route("/doom/{path:path}", doom_watch_proxy_endpoint, methods=["GET", "POST"]),
    Route("/pokemon/", pokemon_proxy_endpoint, methods=["GET", "POST"]),
    Route("/pokemon/{path:path}", pokemon_proxy_endpoint, methods=["GET", "POST"]),
    Route("/api/self-improvement", get_self_improvement_endpoint),
    Route("/api/autonomous-development", get_autonomous_development_endpoint),
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

app = Starlette(routes=routes, lifespan=_lifespan)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=DASHBOARD_PORT)
