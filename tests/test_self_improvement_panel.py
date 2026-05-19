import asyncio
import json
import sys
import types
from pathlib import Path


def _install_framework_stubs() -> None:
    if "starlette.applications" not in sys.modules:
        starlette = types.ModuleType("starlette")
        applications = types.ModuleType("starlette.applications")
        routing = types.ModuleType("starlette.routing")
        templating = types.ModuleType("starlette.templating")
        responses = types.ModuleType("starlette.responses")

        class Starlette:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        class Route:
            def __init__(self, path, endpoint, **kwargs):
                self.path = path
                self.endpoint = endpoint
                self.kwargs = kwargs

        class Jinja2Templates:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

            def TemplateResponse(self, *args, **kwargs):
                return None

        class _Response:
            def __init__(self, content=None, status_code=200):
                self.status_code = status_code
                if isinstance(content, (dict, list)):
                    self.body = json.dumps(content).encode("utf-8")
                elif isinstance(content, bytes):
                    self.body = content
                else:
                    self.body = str(content or "").encode("utf-8")

        class JSONResponse(_Response):
            pass

        class PlainTextResponse(_Response):
            pass

        applications.Starlette = Starlette
        routing.Route = Route
        templating.Jinja2Templates = Jinja2Templates
        responses.JSONResponse = JSONResponse
        responses.PlainTextResponse = PlainTextResponse

        sys.modules["starlette"] = starlette
        sys.modules["starlette.applications"] = applications
        sys.modules["starlette.routing"] = routing
        sys.modules["starlette.templating"] = templating
        sys.modules["starlette.responses"] = responses

    if "sse_starlette.sse" not in sys.modules:
        sse_starlette = types.ModuleType("sse_starlette")
        sse_module = types.ModuleType("sse_starlette.sse")

        class EventSourceResponse:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        sse_module.EventSourceResponse = EventSourceResponse
        sys.modules["sse_starlette"] = sse_starlette
        sys.modules["sse_starlette.sse"] = sse_module


_install_framework_stubs()

import app as dashboard_app


class FakeRequest:
    def __init__(self, payload=None, path_params=None):
        self.payload = payload or {}
        self.path_params = path_params or {}

    async def body(self):
        return json.dumps(self.payload).encode("utf-8")


def _decode(response):
    return json.loads(response.body.decode("utf-8"))


def test_self_improvement_run_ledger_scores_and_links_artifacts(tmp_path, monkeypatch):
    root = tmp_path / "self-improvement"
    run_dir = root / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "decision.json").write_text(json.dumps({
        "run_id": "run-1",
        "trigger_source": "cron",
        "selected_layer": "dashboard_control_surface",
        "candidate": "Add ledger",
        "started_at": "2026-05-15T01:00:00Z",
    }), encoding="utf-8")
    (run_dir / "validation.json").write_text(json.dumps({
        "status": "passed",
        "commands": [{"command": "pytest tests", "exit_code": 0}],
    }), encoding="utf-8")
    (run_dir / "changes.md").write_text("Improved the dashboard ledger.", encoding="utf-8")
    monkeypatch.setattr(dashboard_app, "SELF_IMPROVEMENT_HOME", root)

    ledger = dashboard_app.get_self_improvement_ledger()

    assert ledger["runs"][0]["run_id"] == "run-1"
    assert ledger["runs"][0]["outcome"] == "verified_useful_change"
    assert ledger["runs"][0]["outcome_score"] == 1.0
    assert "validation.json" in ledger["runs"][0]["artifacts"]
    assert ledger["runs"][0]["verification_commands"] == ["pytest tests"]


def test_evidence_gated_queue_accepts_valid_and_rejects_out_of_scope(tmp_path, monkeypatch):
    root = tmp_path / "self-improvement"
    monkeypatch.setattr(dashboard_app, "SELF_IMPROVEMENT_HOME", root)

    valid = dashboard_app.add_self_improvement_candidate({
        "title": "Show self-improvement status in dashboard",
        "allowed_layer": "dashboard_control_surface",
        "evidence_source": "User asked for cockpit visibility",
        "expected_measurable_benefit": "User can see last run outcome",
        "risk": "low",
        "verification_clarity": 5,
        "expected_impact": 5,
        "implementation_size": 2,
        "evidence_strength": 5,
    })
    invalid = dashboard_app.add_self_improvement_candidate({
        "title": "Create a new random GitHub project",
        "allowed_layer": "standalone_project",
        "evidence_source": "none",
        "expected_measurable_benefit": "fun",
        "risk": "high",
    })
    selection = dashboard_app.select_self_improvement_candidate()

    assert valid["accepted"] is True
    assert invalid["accepted"] is False
    assert "outside allowed layers" in invalid["candidate"]["explanation"]
    assert selection["decision"] == "build"
    assert selection["candidate"]["id"] == valid["candidate"]["id"]


def test_empty_queue_selection_pauses_with_explanation(tmp_path, monkeypatch):
    root = tmp_path / "self-improvement"
    monkeypatch.setattr(dashboard_app, "SELF_IMPROVEMENT_HOME", root)

    selection = dashboard_app.select_self_improvement_candidate()

    assert selection["decision"] == "pause"
    assert "No queued candidate" in selection["explanation"]


def test_jsonl_feature_queue_is_primary_dashboard_queue(tmp_path, monkeypatch):
    root = tmp_path / "self-improvement"
    root.mkdir()
    monkeypatch.setattr(dashboard_app, "SELF_IMPROVEMENT_HOME", root)
    jsonl_candidate = {
        "id": "jsonl-1",
        "title": "Bridge live queue",
        "problem": "Dashboard cannot see the active JSONL queue",
        "target_layer": "dashboard_control_surface",
        "status": "selected",
        "usefulness_score": 9,
        "testability_score": 8,
        "novelty_score": 7,
        "selection_reason": "Expose live cron queue state",
    }
    legacy_candidate = {
        "id": "legacy-1",
        "title": "Legacy fallback",
        "allowed_layer": "tooling",
        "status": "queued",
        "score": 5,
        "explanation": "Existing dashboard-only candidate",
    }
    (root / "feature-candidates.jsonl").write_text(json.dumps(jsonl_candidate) + "\n", encoding="utf-8")
    (root / "queue.json").write_text(json.dumps({"candidates": [legacy_candidate]}), encoding="utf-8")

    listed = dashboard_app.list_self_improvement_candidates()

    assert listed["count"] == 2
    assert listed["source_counts"] == {"feature-candidates.jsonl": 1, "queue.json": 1}
    assert listed["status_counts"] == {"selected": 1, "queued": 1}
    assert listed["target_layer_counts"] == {"dashboard_control_surface": 1, "tooling": 1}
    assert listed["backlog_gate"]["ok"] is True
    assert listed["backlog_gate"]["queued_count"] == 0
    assert listed["backlog_gate"]["selected_count"] == 1
    assert listed["backlog_gate"]["action"] == "add_candidates"
    by_id = {candidate["id"]: candidate for candidate in listed["candidates"]}
    assert by_id["jsonl-1"]["allowed_layer"] == "dashboard_control_surface"
    assert by_id["jsonl-1"]["queue_source"] == "feature-candidates.jsonl"
    assert by_id["jsonl-1"]["score"] == 8.0
    assert by_id["jsonl-1"]["explanation"] == "Expose live cron queue state"
    assert by_id["legacy-1"]["queue_source"] == "queue.json"


def test_dashboard_candidate_writes_to_jsonl_queue(tmp_path, monkeypatch):
    root = tmp_path / "self-improvement"
    monkeypatch.setattr(dashboard_app, "SELF_IMPROVEMENT_HOME", root)

    result = dashboard_app.add_self_improvement_candidate({
        "title": "Add control surface evidence",
        "allowed_layer": "dashboard_control_surface",
        "evidence_source": "Operator cannot see build candidates",
        "expected_measurable_benefit": "Dashboard shows the same backlog as cron",
        "risk": "low",
        "verification_clarity": 5,
        "expected_impact": 5,
        "implementation_size": 2,
        "evidence_strength": 5,
    })

    assert result["accepted"] is True
    queue_path = root / "feature-candidates.jsonl"
    assert queue_path.exists()
    rows = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["title"] == "Add control surface evidence"
    assert rows[0]["target_layer"] == "dashboard_control_surface"
    assert rows[0]["problem"] == "Operator cannot see build candidates"
    assert not (root / "queue.json").exists()


def test_dashboard_accepts_live_jsonl_shaped_candidate_submission(tmp_path, monkeypatch):
    root = tmp_path / "self-improvement"
    monkeypatch.setattr(dashboard_app, "SELF_IMPROVEMENT_HOME", root)

    result = dashboard_app.add_self_improvement_candidate({
        "title": "JSONL intake parity",
        "target_layer": "dashboard_control_surface",
        "problem": "Dashboard rejects the same candidate shape produced by research cron",
        "proposed_solution": "Normalize JSONL fields before policy scoring and persistence",
        "evidence": [
            "feature-candidates.jsonl rows use target_layer/problem/proposed_solution/evidence",
            "dashboard submissions should pass the same strict helper as cron research",
        ],
        "risk": "low",
        "usefulness_score": 8,
        "testability_score": 9,
        "novelty_score": 6,
    })

    assert result["accepted"] is True
    candidate = result["candidate"]
    assert candidate["allowed_layer"] == "dashboard_control_surface"
    assert candidate["evidence_source"] == "feature-candidates.jsonl rows use target_layer/problem/proposed_solution/evidence"
    assert candidate["expected_measurable_benefit"] == "Normalize JSONL fields before policy scoring and persistence"
    assert candidate["score"] >= 5
    assert result["queue_result"]["added"] == 1

    duplicate = dashboard_app.add_self_improvement_candidate({
        "title": "JSONL intake parity",
        "target_layer": "dashboard_control_surface",
        "problem": "Dashboard rejects the same candidate shape produced by research cron",
        "proposed_solution": "Normalize JSONL fields before policy scoring and persistence",
        "evidence": [
            "feature-candidates.jsonl rows use target_layer/problem/proposed_solution/evidence",
            "duplicate semantics should match the canonical queue helper",
        ],
        "risk": "low",
        "usefulness_score": 8,
        "testability_score": 9,
        "novelty_score": 6,
    })
    assert duplicate["accepted"] is False
    assert duplicate["queue_result"]["duplicates"] == 1

    rows = [json.loads(line) for line in (root / "feature-candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["source"] == "dashboard"
    assert rows[0]["target_layer"] == "dashboard_control_surface"
    assert rows[0]["problem"] == "Dashboard rejects the same candidate shape produced by research cron"
    assert rows[0]["proposed_solution"] == "Normalize JSONL fields before policy scoring and persistence"


def test_dashboard_candidate_submission_uses_strict_queue_validation(tmp_path, monkeypatch):
    root = tmp_path / "self-improvement"
    monkeypatch.setattr(dashboard_app, "SELF_IMPROVEMENT_HOME", root)

    result = dashboard_app.add_self_improvement_candidate({
        "title": "Invalid queue candidate",
        "target_layer": "not_a_layer",
        "problem": "Dashboard should not bypass strict queue validation",
        "proposed_solution": "",
        "evidence": ["only one evidence string"],
        "risk": "unknown",
        "usefulness_score": 8,
        "testability_score": 9,
        "novelty_score": 6,
    })

    assert result["accepted"] is False
    assert result["candidate"]["status"] == "rejected"
    assert "target_layer must be one of" in result["candidate"]["explanation"]
    assert "proposed_solution must be non-empty" in result["candidate"]["explanation"]
    assert "evidence must contain at least two evidence strings" in result["candidate"]["explanation"]
    queue_path = root / "feature-candidates.jsonl"
    assert not queue_path.exists() or queue_path.read_text(encoding="utf-8") == ""


def test_supervisor_pause_resume_and_confirmed_lock_clear(tmp_path, monkeypatch):
    root = tmp_path / "self-improvement"
    hermes_home = tmp_path / ".hermes"
    cron_dir = hermes_home / "cron"
    cron_dir.mkdir(parents=True)
    jobs_path = cron_dir / "jobs.json"
    jobs_path.write_text(json.dumps({"jobs": [{"id": "self1", "name": "self-improvement-loop", "enabled": True, "state": "scheduled"}]}), encoding="utf-8")
    lock_path = root / "self-improvement.lock.json"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(json.dumps({"run_id": "stale", "created_at": "2000-01-01T00:00:00Z"}), encoding="utf-8")
    monkeypatch.setattr(dashboard_app, "SELF_IMPROVEMENT_HOME", root)
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", hermes_home)

    paused = dashboard_app.apply_self_improvement_control("pause", actor="test")
    assert paused["success"] is True
    assert json.loads(jobs_path.read_text())["jobs"][0]["enabled"] is False

    resumed = dashboard_app.apply_self_improvement_control("resume", actor="test")
    assert resumed["success"] is True
    assert json.loads(jobs_path.read_text())["jobs"][0]["enabled"] is True

    denied = dashboard_app.apply_self_improvement_control("clear_stale_lock", confirm=False, actor="test")
    assert denied["success"] is False
    assert lock_path.exists()

    cleared = dashboard_app.apply_self_improvement_control("clear_stale_lock", confirm=True, actor="test")
    assert cleared["success"] is True
    assert not lock_path.exists()


def test_cron_mesh_and_drift_make_tab_a_self_improvement_hub(tmp_path, monkeypatch):
    root = tmp_path / "self-improvement"
    hermes_home = tmp_path / ".hermes"
    cron_dir = hermes_home / "cron"
    cron_dir.mkdir(parents=True)
    (cron_dir / "jobs.json").write_text(json.dumps({"jobs": [
        {"id": "old", "name": "tournament-build", "enabled": False, "state": "paused", "skills": ["spec-driven-build"]},
        {"id": "self", "name": "self-improvement-loop", "script": "self-improvement-loop.py", "enabled": True, "state": "scheduled", "skills": [
            "self-aug-decision-packet", "self-gap-scout", "self-tool-registry", "self-tool-hygiene", "self-tool-smoke", "hermes-agent", "becomussy", "systematic-debugging"
        ]},
    ]}), encoding="utf-8")
    drift_dir = root / "runs" / "latest"
    drift_dir.mkdir(parents=True)
    (drift_dir / "cron-drift-after.json").write_text(json.dumps({
        "ok": True,
        "scope": "active_jobs",
        "finding_count": 0,
        "inactive_skipped_count": 1,
        "severity_counts": {},
        "findings": [],
    }), encoding="utf-8")
    monkeypatch.setattr(dashboard_app, "SELF_IMPROVEMENT_HOME", root)
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", hermes_home)

    status = dashboard_app.get_self_improvement_status()

    assert status["cron_mesh"]["ok"] is True
    assert status["cron_mesh"]["primary_job_id"] == "self"
    assert status["cron_mesh"]["active_legacy_count"] == 0
    assert status["cron_mesh"]["legacy_jobs"][0]["banned_skills_present"] == ["spec-driven-build"]
    assert status["drift"]["ok"] is True
    assert status["drift"]["scope"] == "active_jobs"
    assert status["policy"]["hub_ok"] is True


def test_self_improvement_api_routes_and_template_are_wired(tmp_path, monkeypatch):
    root = tmp_path / "self-improvement"
    monkeypatch.setattr(dashboard_app, "SELF_IMPROVEMENT_HOME", root)

    response = asyncio.run(dashboard_app.get_self_improvement_endpoint(FakeRequest()))
    payload = _decode(response)

    assert response.status_code == 200
    assert set(payload) >= {"ledger", "queue", "supervisor", "cron_mesh", "drift", "policy"}
    route_paths = [
        getattr(route, "path", getattr(route, "path_format", None))
        or (route.args[0] if getattr(route, "args", None) else None)
        for route in dashboard_app.routes
    ]
    assert "/api/self-improvement" in route_paths
    assert "/api/self-improvement/candidates" in route_paths
    assert "/api/self-improvement/control" in route_paths

    html = (Path(dashboard_app.__file__).parent / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'data-panel="self-improvement"' in html
    assert 'id="self-improvement-panel"' in html
    assert "loadSelfImprovement()" in html
    assert 'id="self-improvement-cron-mesh"' in html
    assert 'id="self-improvement-drift"' in html
    assert "renderSelfImprovementCronMesh" in html
