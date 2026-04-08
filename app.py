import asyncio
import json
import os
import sys
import sqlite3
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

from hermes_constants import display_hermes_home, get_hermes_home
from hermes_state import SessionDB
from agent.session_summarizer import backfill_session_summaries, refresh_session_summary
from hermes_cli.config import (
    DEFAULT_CONFIG,
    OPTIONAL_ENV_VARS,
    load_config as load_hermes_config,
    load_env as load_hermes_env,
    save_config as save_hermes_config,
    save_env_value,
)
from hermes_cli.skin_engine import list_skins
from hermes_cli.tools_config import (
    CONFIGURABLE_TOOLSETS,
    PLATFORMS,
    _get_platform_tools,
)

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
                func = tc.get("function", {}) if isinstance(tc, dict) else {}
                assistant_tool_calls[tc.get("id", "")] = {
                    "name": func.get("name", ""),
                    "arguments": func.get("arguments", ""),
                    "session_id": session_label,
                    "timestamp": item.get("timestamp"),
                }
        elif item.get("role") == "tool":
            call = assistant_tool_calls.get(item.get("tool_call_id", ""), {})
            tool_name = call.get("name") or item.get("tool_name") or "tool"
            output = _safe_json_loads(item.get("content"))
            if tool_name == "skill_manage":
                skill_events.append(
                    {
                        "session_id": session_label,
                        "timestamp": item.get("timestamp"),
                        "request": _safe_json_loads(call.get("arguments", ""))
                        or call.get("arguments")
                        or "",
                        "result": output or item.get("content") or "",
                    }
                )
            elif tool_name == "session_search":
                session_search_events.append(
                    {
                        "session_id": session_label,
                        "timestamp": item.get("timestamp"),
                        "request": _safe_json_loads(call.get("arguments", ""))
                        or call.get("arguments")
                        or "",
                        "result": output or item.get("content") or "",
                    }
                )

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
                    func = tc.get("function", {}) if isinstance(tc, dict) else {}
                    assistant_calls[tc.get("id", "")] = {
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
            }
        )

    return {
        "background_reviews": background_reviews,
        "skill_events": skill_events,
        "session_search_events": session_search_events,
    }


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

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
        )
        if not cursor.fetchone():
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
        sessions = [dict(row) for row in cursor.fetchall()]
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

    session_row = conn.execute(
        """
        SELECT id, title, summary, source, model, started_at, ended_at,
               parent_session_id, message_count, tool_call_count,
               input_tokens, output_tokens, estimated_cost_usd
        FROM sessions
        WHERE id = ?
    """,
        (session_id,),
    ).fetchone()
    if not session_row:
        conn.close()
        return JSONResponse({"error": "Session not found"}, status_code=404)

    cursor = conn.execute(
        """
        SELECT role, content, timestamp, tool_call_id, tool_calls, tool_name
        FROM messages
        WHERE session_id = ?
        ORDER BY timestamp
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
        messages.append(item)
    activity = _session_activity_payload(conn, session_id)
    conn.close()

    return JSONResponse({**dict(session_row), "messages": messages, **activity})


async def backfill_session_summaries_endpoint(request):
    try:
        body = await request.body()
        data = json.loads(body) if body else {}
    except Exception:
        data = {}

    limit = max(1, min(int(data.get("limit", 50) or 50), 500))
    force = bool(data.get("force", False))
    db = SessionDB(HERMES_HOME / "state.db")
    try:
        result = backfill_session_summaries(db, limit=limit, force=force)
        return JSONResponse({"success": True, **result})
    finally:
        db.close()


async def regenerate_session_summary_endpoint(request):
    session_id = request.path_params["session_id"]
    db = SessionDB(HERMES_HOME / "state.db")
    try:
        summary = refresh_session_summary(db, session_id)
        if not summary:
            return JSONResponse(
                {"success": False, "error": "Failed to generate summary"},
                status_code=500,
            )
        return JSONResponse({"success": True, "summary": summary})
    finally:
        db.close()


def _dashboard_allowed_roots() -> list[Path]:
    roots: list[Path] = []
    env_root = os.getenv("HERMES_WRITE_SAFE_ROOT", "").strip()
    if env_root:
        roots.append(Path(env_root).expanduser().resolve())
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

    save_env_value(key, value)

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

        # Check sessions table exists
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
        )
        if not cur.fetchone():
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

        for s in sessions:
            sid = f"session:{s['id']}"
            _add_node(
                sid,
                s["title"] or s["id"][:8],
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

            if since_ts is not None:
                msgs = conn.execute(
                    """SELECT session_id, tool_calls
                       FROM messages
                       WHERE tool_calls IS NOT NULL AND tool_calls != ''
                         AND session_id IN (SELECT id FROM sessions WHERE started_at >= ?)""",
                    (since_ts,),
                ).fetchall()
            else:
                msgs = conn.execute(
                    """SELECT session_id, tool_calls
                       FROM messages
                       WHERE tool_calls IS NOT NULL AND tool_calls != ''"""
                ).fetchall()

            for msg in msgs:
                session_id = msg["session_id"]
                sid = f"session:{session_id}"
                tc_data = _safe_json_loads(msg["tool_calls"])
                if not isinstance(tc_data, list):
                    continue

                for tc in tc_data:
                    if not isinstance(tc, dict):
                        continue
                    func = tc.get("function", {})
                    tool_name = func.get("name", "")
                    if not tool_name:
                        continue

                    # Tool node
                    tool_id = f"tool:{tool_name}"
                    tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

                    # Session → tool edge
                    edges.append(
                        {
                            "source": sid,
                            "target": tool_id,
                            "type": "used_tool",
                        }
                    )

                    # Extract file paths from tool arguments
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

            if skills_dir.exists():
                for category_dir in sorted(skills_dir.iterdir()):
                    if not category_dir.is_dir() or category_dir.name.startswith("."):
                        continue
                    for skill_dir in sorted(category_dir.iterdir()):
                        if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                            continue

                        skill_id_str = skill_dir.name
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
    Route("/api/secrets", get_secrets),
    Route("/api/secrets", set_secret, methods=["POST"]),
    Route("/api/secrets/{key}", delete_secret, methods=["DELETE"]),
    Route("/api/graph", get_graph_data),
]

app = Starlette(routes=routes)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=DASHBOARD_PORT)
