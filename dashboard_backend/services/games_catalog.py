"""Read-only Games tab catalog service.

The Games tab discovers Hermes gaming skills and projects their frontmatter into
a dashboard catalog. Process control, emulator proxies, and watch-server routes
remain owned by ``app.py`` for now; this module only owns filesystem catalog
projection logic and accepts app-owned paths at call time.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


def parse_game_skill_frontmatter(skill_md: Path) -> dict[str, Any]:
    """Return YAML frontmatter from a game SKILL.md file, tolerating plain markdown."""

    try:
        content = Path(skill_md).read_text(encoding="utf-8")
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


def categorize_game_skill(tags: list[str], description: str) -> str:
    """Classify a gaming skill for the dashboard catalog projection."""

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


def get_games_catalog(*, hermes_home: Path) -> dict[str, Any]:
    """Discover gaming-related Hermes skills for the dashboard Games tab."""

    gaming_dir = Path(hermes_home) / "skills" / "gaming"
    games: list[dict[str, Any]] = []
    if gaming_dir.exists():
        for item in sorted(gaming_dir.iterdir(), key=lambda p: p.name.lower()):
            if not item.is_dir() or item.name.startswith("."):
                continue
            skill_md = item / "SKILL.md"
            meta = parse_game_skill_frontmatter(skill_md) if skill_md.exists() else {}
            name = str(meta.get("name") or item.name)
            description = str(meta.get("description") or "")
            tags = meta.get("tags") or []
            if isinstance(tags, str):
                tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
            tags = [str(tag) for tag in tags]
            dashboard_meta = meta.get("dashboard") if isinstance(meta.get("dashboard"), dict) else {}
            game: dict[str, Any] = {
                "id": item.name,
                "name": name.replace("-", " ").replace("_", " ").title(),
                "description": description,
                "tags": tags,
                "category": categorize_game_skill(tags, description),
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
