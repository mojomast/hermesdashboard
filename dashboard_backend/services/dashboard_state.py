"""Persistence helpers for browser dashboard state.

This module is dependency-injected on purpose: tests and legacy callers still
monkeypatch ``app.DASHBOARD_STATE_DB_PATH`` / ``app.DASHBOARD_STATE_LOCK``.
The app.py compatibility wrappers pass those live values in, avoiding hidden
state drift while moving the SQLite implementation out of the monolith.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable


def dashboard_state_connect(db_path: Path) -> sqlite3.Connection:
    """Open the dashboard-state DB and ensure its schema exists."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
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


def validate_dashboard_state_key(key: str, allowed_keys: Iterable[str]) -> str:
    """Normalize and validate a dashboard-state key."""
    normalized = str(key or "").strip()
    if normalized not in set(allowed_keys):
        raise ValueError(f"Unsupported dashboard state key: {normalized}")
    return normalized


def load_dashboard_state(
    key: str,
    *,
    db_path: Path,
    lock: threading.Lock,
    allowed_keys: Iterable[str],
) -> tuple[bool, Any]:
    """Load a JSON state payload by key.

    Returns ``(False, None)`` when the key is absent or the stored JSON is
    corrupt, preserving the legacy app.py behavior.
    """
    key = validate_dashboard_state_key(key, allowed_keys)
    with lock:
        conn = dashboard_state_connect(db_path)
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


def save_dashboard_state(
    key: str,
    value: Any,
    *,
    db_path: Path,
    lock: threading.Lock,
    allowed_keys: Iterable[str],
) -> None:
    """Persist a JSON state payload by key."""
    key = validate_dashboard_state_key(key, allowed_keys)
    value_json = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with lock:
        conn = dashboard_state_connect(db_path)
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


def delete_dashboard_state(
    key: str,
    *,
    db_path: Path,
    lock: threading.Lock,
    allowed_keys: Iterable[str],
) -> None:
    """Delete a dashboard-state payload by key if present."""
    key = validate_dashboard_state_key(key, allowed_keys)
    with lock:
        conn = dashboard_state_connect(db_path)
        try:
            conn.execute("DELETE FROM dashboard_state WHERE key = ?", (key,))
            conn.commit()
        finally:
            conn.close()
