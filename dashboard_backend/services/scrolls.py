"""Read-only Scrolls/Vesuvius dashboard service helpers.

The public HTTP route wrappers still live in ``app.py`` for compatibility with
existing tests and monkeypatch seams. This module owns bounded-context service
logic for Scrolls state projections that can be delegated without importing the
Starlette app.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any


class ScrollsSnapshotUnavailable(RuntimeError):
    """Raised when the standalone Scrolls snapshot implementation is unavailable."""


def build_scrolls_snapshot(project_root: Path) -> dict[str, Any]:
    """Return the standalone Scrolls snapshot state projection.

    ``/api/scrolls/snapshot`` is a read-only state projection route. The
    canonical snapshot builder lives with the Vesuvius AutoResearch project, so
    this helper injects the project root at call time and delegates to
    ``research_dashboard.snapshot.build_snapshot``. Mutable/configurable state
    stays outside the service and is passed in by the route wrapper.
    """

    root = Path(project_root).expanduser()
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)

    try:
        snapshot_module = importlib.import_module("research_dashboard.snapshot")
        build_snapshot = getattr(snapshot_module, "build_snapshot")
    except Exception as exc:
        raise ScrollsSnapshotUnavailable(str(exc)) from exc

    snapshot = build_snapshot(root)
    if not isinstance(snapshot, dict):
        raise RuntimeError("research_dashboard.snapshot.build_snapshot did not return an object")
    return snapshot
