"""Deployment controls for Hermes's native Kanban dashboard and dispatcher."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable


KANBAN_SERVICE = "hermes-kanban-dashboard.service"
DEFAULT_BOARD_URL = "http://127.0.0.1:9119/kanban"


def _systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", "--user", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _service_state(action: str, service: str = KANBAN_SERVICE) -> bool:
    result = _systemctl(action, service)
    return result.returncode == 0 and result.stdout.strip() in {"active", "enabled"}


def get_kanban_status(
    *,
    get_config: Callable[[], Any],
    agent_path: Path,
    service: str = KANBAN_SERVICE,
) -> dict[str, Any]:
    config = get_config()
    config = config if isinstance(config, dict) else {}
    kanban = config.get("kanban") if isinstance(config.get("kanban"), dict) else {}
    manifest = agent_path / "plugins" / "kanban" / "dashboard" / "manifest.json"
    service_active = _service_state("is-active", service)
    service_enabled = _service_state("is-enabled", service)
    runtime_enabled = bool(kanban.get("enabled", True))
    return {
        "installed": manifest.is_file(),
        "enabled": runtime_enabled and service_active,
        "dispatch_enabled": runtime_enabled,
        "service_active": service_active,
        "service_enabled": service_enabled,
        "board_url": os.getenv("HERMES_KANBAN_PUBLIC_URL", DEFAULT_BOARD_URL).strip() or DEFAULT_BOARD_URL,
        "orchestrator_profile": str(kanban.get("orchestrator_profile") or ""),
        "default_assignee": str(kanban.get("default_assignee") or ""),
        "max_in_progress": kanban.get("max_in_progress"),
        "max_in_progress_per_profile": kanban.get("max_in_progress_per_profile"),
        "auto_decompose": bool(kanban.get("auto_decompose", True)),
        "review_dispatch": bool(kanban.get("review_dispatch", True)),
    }


def set_kanban_enabled(
    enabled: bool,
    *,
    get_config: Callable[[], Any],
    agent_path: Path,
    set_config_value: Callable[[str, str], Any] | None = None,
    service: str = KANBAN_SERVICE,
) -> dict[str, Any]:
    if set_config_value is None:
        from hermes_cli.config import set_config_value as canonical_set_config_value

        set_config_value = canonical_set_config_value

    if enabled:
        service_result = _systemctl("enable", "--now", service)
        if service_result.returncode != 0:
            raise RuntimeError(service_result.stderr.strip() or "Could not start the Kanban dashboard service")
        set_config_value("kanban.enabled", "true")
    else:
        set_config_value("kanban.enabled", "false")
        service_result = _systemctl("disable", "--now", service)
        if service_result.returncode != 0:
            raise RuntimeError(service_result.stderr.strip() or "Could not stop the Kanban dashboard service")

    return get_kanban_status(get_config=get_config, agent_path=agent_path, service=service)
