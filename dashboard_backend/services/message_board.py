"""SQLite-backed message-board service for the Hermes Dashboard.

This module owns durable message-board post/message persistence. Route handlers and
Hermes reply generation remain in ``app.py`` during the refactor so public route
paths and monkeypatch-sensitive app symbols keep their compatibility behavior.
"""

from __future__ import annotations

import datetime
import sqlite3
import uuid
from pathlib import Path
from typing import Optional


def _message_board_db_path(hermes_home: Path) -> Path:
    return hermes_home / "dashboard_message_board.sqlite3"


def _message_board_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _message_board_connection(hermes_home: Path) -> sqlite3.Connection:
    db_path = _message_board_db_path(hermes_home)
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


def get_message_board_post(post_id: str, *, hermes_home: Path) -> Optional[dict]:
    with _message_board_connection(hermes_home) as conn:
        return _load_message_board_post(conn, post_id)


def list_message_board_posts(limit: int = 50, *, hermes_home: Path) -> list[dict]:
    with _message_board_connection(hermes_home) as conn:
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


def add_message_board_reply(
    post_id: str,
    content: str,
    author: str = "Hermes",
    role: str = "assistant",
    *,
    hermes_home: Path,
) -> dict:
    content = str(content or "").strip()
    if not content:
        raise ValueError("Reply content is required")
    if role not in {"assistant", "user"}:
        raise ValueError("Reply role must be assistant or user")
    now = _message_board_now()
    with _message_board_connection(hermes_home) as conn:
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


def add_message_board_user_message(
    post_id: str,
    content: str,
    author: str = "mojo",
    *,
    hermes_home: Path,
) -> dict:
    return add_message_board_reply(post_id, content, author=author, role="user", hermes_home=hermes_home)


def create_message_board_post(
    title: str,
    body: str,
    author: str = "mojo",
    agent_reply: Optional[str] = None,
    *,
    hermes_home: Path,
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
    with _message_board_connection(hermes_home) as conn:
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
        return add_message_board_reply(post_id, agent_reply, author="Hermes", role="assistant", hermes_home=hermes_home)
    loaded = get_message_board_post(post_id, hermes_home=hermes_home)
    if not loaded:
        raise RuntimeError("Created message board post could not be loaded")
    return loaded
