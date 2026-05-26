import subprocess
from pathlib import Path

import app as dashboard_app


def _completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_dashboard_auto_update_route_is_registered():
    route = next((route for route in dashboard_app.routes if getattr(route, "path", "") == "/api/dashboard/update"), None)

    assert route is not None
    assert getattr(route, "endpoint", None) is dashboard_app.dashboard_auto_update_endpoint
    assert "POST" in getattr(route, "methods", getattr(route, "kwargs", {}).get("methods", []))


def test_dashboard_auto_update_refuses_dirty_worktree(tmp_path, monkeypatch):
    repo = tmp_path / "dashboard"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setattr(dashboard_app, "DASHBOARD_REPO_ROOT", repo)

    commands = []

    def fake_run(args, **kwargs):
        commands.append(tuple(args))
        if args[:3] == ["git", "rev-parse", "--abbrev-ref"]:
            return _completed("main\n")
        if args == ["git", "rev-parse", "HEAD"]:
            return _completed("abc123\n")
        if args == ["git", "status", "--porcelain"]:
            return _completed(" M templates/index.html\n")
        raise AssertionError(f"unexpected command after dirty status: {args}")

    monkeypatch.setattr(dashboard_app.subprocess, "run", fake_run)

    status_code, payload = dashboard_app._dashboard_auto_update()

    assert status_code == 409
    assert payload["ok"] is False
    assert "local changes" in payload["error"]
    assert payload["dirty_files"] == [" M templates/index.html"]
    assert ("git", "fetch", "--prune", "origin") not in commands


def test_dashboard_auto_update_fetches_pulls_and_reports_restart(tmp_path, monkeypatch):
    repo = tmp_path / "dashboard"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setattr(dashboard_app, "DASHBOARD_REPO_ROOT", repo)

    rev_parse_head_calls = 0
    commands = []

    def fake_run(args, **kwargs):
        nonlocal rev_parse_head_calls
        commands.append(tuple(args))
        if args[:3] == ["git", "rev-parse", "--abbrev-ref"]:
            return _completed("main\n")
        if args == ["git", "rev-parse", "HEAD"]:
            rev_parse_head_calls += 1
            return _completed("aaa111\n" if rev_parse_head_calls == 1 else "bbb222\n")
        if args == ["git", "status", "--porcelain"]:
            return _completed("")
        if args == ["git", "fetch", "--prune", "origin"]:
            return _completed("", "From origin\n")
        if args == ["git", "pull", "--ff-only"]:
            return _completed("Updating aaa111..bbb222\n")
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(dashboard_app.subprocess, "run", fake_run)

    status_code, payload = dashboard_app._dashboard_auto_update(install_dependencies=False)

    assert status_code == 200
    assert payload["ok"] is True
    assert payload["updated"] is True
    assert payload["restart_required"] is True
    assert payload["before"] == "aaa111"
    assert payload["after"] == "bbb222"
    assert ("git", "fetch", "--prune", "origin") in commands
    assert ("git", "pull", "--ff-only") in commands
