import asyncio
import json
import sys
from pathlib import Path

import pytest

import app as dashboard_app
from dashboard_backend.services.scrolls import ScrollsSnapshotUnavailable, build_scrolls_snapshot


class FakeRequest:
    query_params = {}


def _decode(response):
    return json.loads(response.body.decode("utf-8"))


def _clear_fake_research_dashboard_modules():
    for name in list(sys.modules):
        if name == "research_dashboard" or name.startswith("research_dashboard."):
            sys.modules.pop(name, None)


def test_build_scrolls_snapshot_delegates_to_research_dashboard(tmp_path, monkeypatch):
    _clear_fake_research_dashboard_modules()
    monkeypatch.syspath_prepend(str(tmp_path))
    pkg = tmp_path / "research_dashboard"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "snapshot.py").write_text(
        "def build_snapshot(project_root):\n"
        "    return {'schema_version': 7, 'project': {'root': str(project_root)}, 'progress': {'ok': True}}\n",
        encoding="utf-8",
    )

    try:
        payload = build_scrolls_snapshot(tmp_path)
    finally:
        _clear_fake_research_dashboard_modules()

    assert payload["schema_version"] == 7
    assert payload["project"]["root"] == str(tmp_path)
    assert payload["progress"]["ok"] is True


def test_build_scrolls_snapshot_requires_object_payload(tmp_path, monkeypatch):
    _clear_fake_research_dashboard_modules()
    monkeypatch.syspath_prepend(str(tmp_path))
    pkg = tmp_path / "research_dashboard"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "snapshot.py").write_text(
        "def build_snapshot(project_root):\n"
        "    return ['not', 'an', 'object']\n",
        encoding="utf-8",
    )

    try:
        with pytest.raises(RuntimeError, match="did not return an object"):
            build_scrolls_snapshot(tmp_path)
    finally:
        _clear_fake_research_dashboard_modules()


def test_scrolls_snapshot_endpoint_success_and_route_are_wired(monkeypatch):
    def fake_snapshot(project_root: Path):
        return {"schema_version": 1, "project": {"root": str(project_root)}, "progress": {"ok": True}}

    monkeypatch.setattr(dashboard_app, "_build_scrolls_snapshot_impl", fake_snapshot)

    response = asyncio.run(dashboard_app.get_scrolls_snapshot_endpoint(FakeRequest()))
    payload = _decode(response)

    assert response.status_code == 200
    assert payload["schema_version"] == 1
    assert payload["project"]["root"] == str(dashboard_app._SCROLLS_PROJECT_ROOT)
    assert any(getattr(route, "path", None) == "/api/scrolls/snapshot" for route in dashboard_app.routes)


def test_scrolls_snapshot_endpoint_reports_unavailable(monkeypatch):
    def fake_unavailable(project_root: Path):
        raise ScrollsSnapshotUnavailable("no snapshot module")

    monkeypatch.setattr(dashboard_app, "_build_scrolls_snapshot_impl", fake_unavailable)

    response = asyncio.run(dashboard_app.get_scrolls_snapshot_endpoint(FakeRequest()))
    payload = _decode(response)

    assert response.status_code == 503
    assert payload["error"] == "research_dashboard not available"
    assert payload["detail"] == "no snapshot module"


def test_scrolls_snapshot_endpoint_reports_build_failure(monkeypatch):
    def fake_failure(project_root: Path):
        raise RuntimeError("snapshot failed")

    monkeypatch.setattr(dashboard_app, "_build_scrolls_snapshot_impl", fake_failure)

    response = asyncio.run(dashboard_app.get_scrolls_snapshot_endpoint(FakeRequest()))
    payload = _decode(response)

    assert response.status_code == 500
    assert payload["error"] == "snapshot failed"
