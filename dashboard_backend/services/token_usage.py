"""Token usage aggregation service for the Hermes Dashboard.

This module owns read-only token usage projections. Route handlers remain wired in
``app.py`` for compatibility while the monolith is decomposed.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

TOKEN_USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
)


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
        columns.add(str(row[1]))
    return columns


def _parse_dashboard_timestamp(value: object) -> Optional[datetime.datetime]:
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.datetime.fromisoformat(text)
        except ValueError:
            try:
                parsed = datetime.datetime.fromtimestamp(float(text), datetime.timezone.utc)
            except Exception:
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _empty_token_usage_window(label: str, *, start: float | None = None, end: float | None = None, source: str = "api_calls") -> dict:
    window = {
        "label": label,
        "start": start,
        "end": end,
        "source": source,
        "call_count": 0,
        "session_count": 0,
    }
    for field in TOKEN_USAGE_FIELDS:
        window[field] = 0
    window["total_tokens"] = 0
    return window


def _token_usage_total(row: dict) -> int:
    return int(sum(int(row.get(field) or 0) for field in TOKEN_USAGE_FIELDS))


def _window_from_row(label: str, row: sqlite3.Row | dict | None, *, start: float | None = None, end: float | None = None, source: str = "api_calls") -> dict:
    window = _empty_token_usage_window(label, start=start, end=end, source=source)
    if not row:
        return window
    data = dict(row)
    for field in TOKEN_USAGE_FIELDS:
        window[field] = int(data.get(field) or 0)
    window["total_tokens"] = _token_usage_total(window)
    window["call_count"] = int(data.get("call_count") or 0)
    window["session_count"] = int(data.get("session_count") or 0)
    return window


def _aggregate_token_usage_api_calls(conn: sqlite3.Connection, label: str, *, start: float | None = None, end: float | None = None, session_id: str | None = None) -> dict:
    if not _sqlite_table_exists(conn, "api_calls"):
        return _empty_token_usage_window(label, start=start, end=end, source="api_calls")
    columns = _sqlite_table_columns(conn, "api_calls")
    missing = {"start_time", *TOKEN_USAGE_FIELDS} - columns
    if missing:
        return _empty_token_usage_window(label, start=start, end=end, source="api_calls")
    conditions = []
    params: list[Any] = []
    if session_id:
        conditions.append("session_id = ?")
        params.append(session_id)
    if start is not None:
        conditions.append("start_time >= ?")
        params.append(start)
    if end is not None:
        conditions.append("start_time <= ?")
        params.append(end)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    field_sql = ", ".join(f"COALESCE(SUM({field}), 0) AS {field}" for field in TOKEN_USAGE_FIELDS)
    row = conn.execute(
        f"SELECT {field_sql}, COUNT(*) AS call_count FROM api_calls {where}",
        params,
    ).fetchone()
    return _window_from_row(label, row, start=start, end=end, source="api_calls")


def _aggregate_token_usage_sessions(conn: sqlite3.Connection, label: str, *, start: float | None = None, end: float | None = None, session_id: str | None = None) -> dict:
    window = _empty_token_usage_window(label, start=start, end=end, source="sessions")
    if not _sqlite_table_exists(conn, "sessions"):
        return window
    columns = _sqlite_table_columns(conn, "sessions")
    if not set(TOKEN_USAGE_FIELDS).issubset(columns):
        return window
    select_columns = ["id", *TOKEN_USAGE_FIELDS]
    if "started_at" in columns:
        select_columns.append("started_at")
    conditions = []
    params: list[Any] = []
    if session_id:
        conditions.append("id = ?")
        params.append(session_id)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(f"SELECT {', '.join(select_columns)} FROM sessions {where}", params).fetchall()
    for row in rows:
        data = dict(row)
        if not session_id and (start is not None or end is not None):
            parsed = _parse_dashboard_timestamp(data.get("started_at"))
            if parsed is None:
                continue
            timestamp = parsed.timestamp()
            if start is not None and timestamp < start:
                continue
            if end is not None and timestamp > end:
                continue
        window["session_count"] += 1
        for field in TOKEN_USAGE_FIELDS:
            window[field] += int(data.get(field) or 0)
    window["total_tokens"] = _token_usage_total(window)
    return window


CONTEXT_BREAKDOWN_FIELDS = (
    "system_prompt_tokens",
    "developer_prompt_tokens",
    "tool_schema_tokens",
    "memory_tokens",
    "conversation_history_tokens",
    "tool_result_tokens",
    "current_user_message_tokens",
)


def _empty_context_gauge(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "model": None,
        "context_used": None,
        "context_max": None,
        "percent": None,
        "breakdown": {},
        "source": "none",
        "stale": True,
    }


def _read_context_length_cache(path: Path) -> dict[str, int]:
    lengths: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return lengths
    in_section = False
    for line in lines:
        if not line.strip() or line.strip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            in_section = line.rstrip().rstrip(":").strip() == "context_lengths"
            continue
        if not in_section or ":" not in line:
            continue
        key, _, value = line.strip().rpartition(":")
        key = key.strip().strip("'\"")
        value = value.strip().strip("'\"")
        try:
            lengths[key] = int(float(value))
        except (TypeError, ValueError):
            continue
    return lengths


def _lookup_context_max(hermes_home: Path, model: str | None, base_url: str | None) -> int | None:
    if not model:
        return None
    cache_path = hermes_home / "context_length_cache.yaml"
    lengths = _read_context_length_cache(cache_path) if cache_path.exists() else {}
    if lengths:
        candidates = []
        if base_url:
            candidates.append(f"{model}@{base_url}")
            candidates.append(f"{model}@{base_url.rstrip('/')}/")
        candidates.append(model)
        for candidate in candidates:
            if candidate in lengths:
                return lengths[candidate]
        for key, value in lengths.items():
            if key == model or key.startswith(f"{model}@"):
                return value
    dev_cache_path = hermes_home / "models_dev_cache.json"
    if dev_cache_path.exists():
        try:
            data = json.loads(dev_cache_path.read_text(encoding="utf-8"))
        except Exception:
            data = None
        if isinstance(data, dict):
            for provider in data.values():
                models = provider.get("models") if isinstance(provider, dict) else None
                if not isinstance(models, dict):
                    continue
                entry = models.get(model)
                if not isinstance(entry, dict):
                    for model_id, candidate in models.items():
                        if isinstance(model_id, str) and model_id.startswith(model) and isinstance(candidate, dict):
                            entry = candidate
                            break
                if not isinstance(entry, dict):
                    continue
                limit = entry.get("limit")
                if isinstance(limit, dict):
                    context = limit.get("context")
                    if isinstance(context, (int, float)) and context > 0:
                        return int(context)
    return None


def get_session_context_gauge(*, hermes_home: Path, session_id: str) -> dict:
    """Return context-window gauge data for a single session.

    Prefers the latest prompt_budgets row for per-category input token breakdown;
    falls back to the latest api_calls row (input + cache read/write). Context max
    comes from context_length_cache.yaml, then models_dev_cache.json. Never raises;
    returns a stale payload when no data is available.
    """
    gauge = _empty_context_gauge(str(session_id))
    db_path = hermes_home / "state.db"
    if not db_path.exists():
        return gauge
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        model: str | None = None
        base_url: str | None = None
        session_row = None
        if _sqlite_table_exists(conn, "sessions"):
            session_columns = _sqlite_table_columns(conn, "sessions")
            select_columns = [column for column in ("model", "model_config") if column in session_columns]
            if select_columns:
                session_row = conn.execute(
                    f"SELECT {', '.join(select_columns)} FROM sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()
        if _sqlite_table_exists(conn, "prompt_budgets"):
            budget_columns = _sqlite_table_columns(conn, "prompt_budgets")
            wanted = {"session_id", "total_input_tokens", *CONTEXT_BREAKDOWN_FIELDS}
            if wanted.issubset(budget_columns):
                order_column = "timestamp" if "timestamp" in budget_columns else "rowid"
                budget_row = conn.execute(
                    f"SELECT * FROM prompt_budgets WHERE session_id = ? ORDER BY {order_column} DESC, rowid DESC LIMIT 1",
                    (session_id,),
                ).fetchone()
                if budget_row:
                    data = dict(budget_row)
                    breakdown = {field: int(data.get(field) or 0) for field in CONTEXT_BREAKDOWN_FIELDS}
                    gauge["breakdown"] = breakdown
                    gauge["context_used"] = int(data.get("total_input_tokens") or 0)
                    gauge["source"] = "prompt_budgets"
                    gauge["stale"] = False
        if _sqlite_table_exists(conn, "api_calls"):
            api_columns = _sqlite_table_columns(conn, "api_calls")
            if "session_id" in api_columns:
                select_columns = [column for column in ("model", "input_tokens", "cache_read_tokens", "cache_write_tokens", "start_time") if column in api_columns]
                if select_columns:
                    order_column = "start_time" if "start_time" in api_columns else "rowid"
                    api_row = conn.execute(
                        f"SELECT {', '.join(select_columns)} FROM api_calls WHERE session_id = ? ORDER BY {order_column} DESC, rowid DESC LIMIT 1",
                        (session_id,),
                    ).fetchone()
                    if api_row:
                        api_data = dict(api_row)
                        model = api_data.get("model") or model
                        if gauge["stale"]:
                            used = sum(int(api_data.get(field) or 0) for field in ("input_tokens", "cache_read_tokens", "cache_write_tokens"))
                            gauge["context_used"] = used
                            gauge["source"] = "api_calls"
                            gauge["stale"] = False
        if session_row is not None:
            session_data = dict(session_row)
            if not model:
                model = session_data.get("model") or None
            raw_config = session_data.get("model_config")
            if raw_config:
                try:
                    config = json.loads(raw_config) if isinstance(raw_config, str) else raw_config
                except Exception:
                    config = None
                if isinstance(config, dict):
                    candidate = config.get("base_url") or config.get("api_base")
                    if isinstance(candidate, str) and candidate.strip():
                        base_url = candidate.strip()
        gauge["model"] = model
        gauge["context_max"] = _lookup_context_max(hermes_home, model, base_url)
        if gauge["context_used"] is not None and gauge["context_max"]:
            gauge["percent"] = round(100.0 * gauge["context_used"] / gauge["context_max"], 2)
        return gauge
    except Exception:
        return gauge
    finally:
        conn.close()


def get_token_usage_summary(*, hermes_home: Path, now: datetime.datetime | None = None, current_session_id: str | None = None) -> dict:
    """Return consumed-token totals for dashboard top-bar windows.

    Source-of-truth vocabulary:
    - consumed tokens = input + output + cache read + cache write + reasoning tokens.
    - day/month are UTC calendar windows; week is ISO week starting Monday UTC.
    - api_calls is preferred for time-windowed totals; sessions is only a current-session fallback.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    now = now.astimezone(datetime.timezone.utc)
    generated_at = now.isoformat().replace("+00:00", "Z")
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - datetime.timedelta(days=day_start.weekday())
    month_start = day_start.replace(day=1)
    end = now.timestamp()
    windows = {
        "current_session": _empty_token_usage_window("Current session", source="none"),
        "current_day": _empty_token_usage_window("Current day", start=day_start.timestamp(), end=end),
        "current_week": _empty_token_usage_window("Current week", start=week_start.timestamp(), end=end),
        "current_month": _empty_token_usage_window("Current month", start=month_start.timestamp(), end=end),
        "overall": _empty_token_usage_window("Overall"),
    }
    db_path = hermes_home / "state.db"
    payload = {
        "metric": "consumed_tokens",
        "source_preference": "api_calls",
        "available": False,
        "generated_at": generated_at,
        "current_session_id": current_session_id or "",
        "windows": windows,
        "context": None,
        "warnings": [],
    }
    if current_session_id:
        payload["context"] = get_session_context_gauge(hermes_home=hermes_home, session_id=current_session_id)
    if not db_path.exists():
        payload["warnings"].append("state.db not found")
        return payload
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _sqlite_table_exists(conn, "api_calls"):
            payload["warnings"].append("api_calls table not found")
            if current_session_id:
                windows["current_session"] = _aggregate_token_usage_sessions(conn, "Current session", session_id=current_session_id)
            windows["current_day"] = _aggregate_token_usage_sessions(conn, "Current day", start=day_start.timestamp(), end=end)
            windows["current_week"] = _aggregate_token_usage_sessions(conn, "Current week", start=week_start.timestamp(), end=end)
            windows["current_month"] = _aggregate_token_usage_sessions(conn, "Current month", start=month_start.timestamp(), end=end)
            windows["overall"] = _aggregate_token_usage_sessions(conn, "Overall")
            payload["available"] = _sqlite_table_exists(conn, "sessions")
            return payload
        if current_session_id:
            current = _aggregate_token_usage_api_calls(conn, "Current session", session_id=current_session_id)
            if current["call_count"] == 0 and current["total_tokens"] == 0:
                current = _aggregate_token_usage_sessions(conn, "Current session", session_id=current_session_id)
            windows["current_session"] = current
        windows["current_day"] = _aggregate_token_usage_api_calls(conn, "Current day", start=day_start.timestamp(), end=end)
        windows["current_week"] = _aggregate_token_usage_api_calls(conn, "Current week", start=week_start.timestamp(), end=end)
        windows["current_month"] = _aggregate_token_usage_api_calls(conn, "Current month", start=month_start.timestamp(), end=end)
        windows["overall"] = _aggregate_token_usage_api_calls(conn, "Overall")
        if windows["overall"]["total_tokens"] == 0:
            session_overall = _aggregate_token_usage_sessions(conn, "Overall")
            if session_overall["total_tokens"] > 0:
                payload["warnings"].append("api_calls token totals are empty; using session aggregates")
                if current_session_id:
                    windows["current_session"] = _aggregate_token_usage_sessions(conn, "Current session", session_id=current_session_id)
                windows["current_day"] = _aggregate_token_usage_sessions(conn, "Current day", start=day_start.timestamp(), end=end)
                windows["current_week"] = _aggregate_token_usage_sessions(conn, "Current week", start=week_start.timestamp(), end=end)
                windows["current_month"] = _aggregate_token_usage_sessions(conn, "Current month", start=month_start.timestamp(), end=end)
                windows["overall"] = session_overall
        payload["available"] = True
        return payload
    except Exception as exc:
        payload["warnings"].append(str(exc))
        return payload
    finally:
        conn.close()
