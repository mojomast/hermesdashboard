import asyncio
import json
import os
import sys
import sqlite3
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Optional

import httpx
import yaml
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.templating import Jinja2Templates
from starlette.responses import JSONResponse, PlainTextResponse
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
API_KEY = os.getenv(
    "API_SERVER_KEY", "hermes-dashboard-secret-9e4349ef052042545dd435d3330a2287"
)
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8081"))

templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates")
)


ACTIVE_RUN_TTL_SECONDS = 1800
ACTIVE_RUNS: dict[str, dict] = {}
_STARTUP_METADATA_BACKFILL_STARTED = False

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


async def _run_chat_stream(
    run_id: str, messages: list, session_id: Optional[str]
) -> None:
    state = ACTIVE_RUNS[run_id]
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    if session_id:
        headers["X-Hermes-Session-Id"] = session_id
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=30.0, read=None, write=300.0, pool=30.0)
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
                if not state.get("session_id"):
                    sid = response.headers.get("X-Hermes-Session-Id", "").strip()
                    if sid:
                        state["session_id"] = sid
                async for line in response.aiter_lines():
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
                    for payload in _normalize_sse_payload(parsed):
                        event = {"data": json.dumps(payload)}
                        state["events"].append(event)
    except Exception as exc:
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
        messages = data.get("messages", [])
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
        state["task"] = asyncio.create_task(
            _run_chat_stream(run_id, messages, session_id)
        )

    async def generate():
        sent = int(data.get("event_offset") or 0)
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
            await asyncio.sleep(0.1)

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
    Route("/api/sessions/{session_id}", delete_session, methods=["DELETE"]),
    Route("/api/files/content", get_file_content),
    Route("/api/memory", get_memory),
    Route("/api/memory", update_memory, methods=["POST"]),
    Route("/api/skills", get_skills),
    Route("/api/skills/toggle", toggle_skill, methods=["POST"]),
    Route("/api/skills/{skill_id}/content", get_skill_content),
    Route("/api/cron", get_cron_jobs),
    Route("/api/cron", create_cron_job, methods=["POST"]),
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

app = Starlette(routes=routes, on_startup=[_run_startup_session_metadata_backfill])

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=DASHBOARD_PORT)
