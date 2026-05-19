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


def _write_jobs(hermes_home: Path, jobs: list[dict]) -> None:
    path = hermes_home / "cron" / "jobs.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")


def test_autonomous_development_registry_seeds_active_self_improvement_and_inactive_legacy_pipelines(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", hermes_home)
    _write_jobs(hermes_home, [
        {"id": "build", "name": "autonomous-build", "enabled": False, "state": "paused", "schedule": {"kind": "interval", "minutes": 240}},
        {"id": "curate", "name": "project-curation-tournament", "enabled": False, "state": "paused", "script": "project-curation-tournament.py", "schedule_display": "every 60m"},
        {"id": "self-build", "name": "self-improvement-loop", "enabled": True, "state": "scheduled", "script": "self-improvement-loop.py", "schedule_display": "every 120m"},
        {"id": "self-research", "name": "self-improvement-research-queue", "enabled": True, "state": "scheduled", "script": "self-improvement-research-queue.py"},
        {"id": "self-tournament", "name": "self-improvement-feature-tournament", "enabled": True, "state": "scheduled", "script": "self-improvement-feature-tournament.py"},
    ])

    status = dashboard_app.get_autonomous_development_status()

    by_id = {pipeline["id"]: pipeline for pipeline in status["pipelines"]}
    assert status["count"] == 3
    assert by_id["self-improvement"]["active"] is True
    assert by_id["self-improvement"]["jobs_summary"]["active"] == 3
    assert by_id["legacy-software-development"]["active"] is False
    assert by_id["legacy-software-development"]["activation_mode"] == "manual"
    assert set(by_id["legacy-software-development"]["job_names"]) >= {"autonomous-research", "autonomous-build", "tournament-build"}
    assert by_id["legacy-project-curation"]["active"] is False
    assert by_id["legacy-project-curation"]["job_names"] == ["project-curation-tournament"]
    assert (hermes_home / "autonomous-development" / "pipelines.json").exists()


def test_autonomous_development_can_create_pipeline_update_specs_and_control_linked_jobs(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", hermes_home)
    _write_jobs(hermes_home, [{"id": "research", "name": "custom-research", "enabled": False, "state": "paused"}])

    created = dashboard_app.create_autonomous_development_pipeline({
        "name": "Custom Pipeline",
        "description": "Runs a custom autonomous development workflow",
        "job_names": ["custom-research"],
        "schedule": "every 90m",
        "research_specification": "Find grounded candidates with novelty checks.",
        "tournament_specification": "Debate queued candidates and select one winner.",
        "build_specification": "Build only selected candidates with tests.",
        "safety_policy": "No GitHub push without explicit approval.",
    })

    assert created["pipeline"]["id"].startswith("pipeline_")
    assert created["pipeline"]["active"] is False
    assert created["pipeline"]["specifications"]["research"] == "Find grounded candidates with novelty checks."

    updated = dashboard_app.update_autonomous_development_pipeline(created["pipeline"]["id"], {
        "tournament_specification": "Use champion/judge tournament with diversity scoring.",
        "enabled": True,
        "schedule": "every 45m",
    })
    assert updated["pipeline"]["specifications"]["tournament"] == "Use champion/judge tournament with diversity scoring."
    nested = dashboard_app.update_autonomous_development_pipeline(created["pipeline"]["id"], {
        "specifications": {"research": "Nested research update", "safety": "Nested safety update"},
    })
    assert nested["pipeline"]["specifications"]["research"] == "Nested research update"
    assert nested["pipeline"]["specifications"]["safety"] == "Nested safety update"
    assert nested["pipeline"]["specifications"]["tournament"] == "Use champion/judge tournament with diversity scoring."
    assert updated["pipeline"]["desired_enabled"] is True
    assert updated["pipeline"]["schedule"] == "every 45m"

    control = dashboard_app.apply_autonomous_development_pipeline_control(created["pipeline"]["id"], "enable", actor="test")
    jobs = json.loads((hermes_home / "cron" / "jobs.json").read_text())["jobs"]
    assert control["success"] is True
    assert jobs[0]["enabled"] is True
    assert jobs[0]["state"] == "scheduled"
    assert jobs[0]["schedule_display"] == "every 45m"

    disabled = dashboard_app.apply_autonomous_development_pipeline_control(created["pipeline"]["id"], "disable", actor="test")
    jobs = json.loads((hermes_home / "cron" / "jobs.json").read_text())["jobs"]
    assert disabled["success"] is True
    assert jobs[0]["enabled"] is False
    assert jobs[0]["state"] == "paused"


def test_autonomous_development_api_routes_and_template_are_wired(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", hermes_home)
    _write_jobs(hermes_home, [])

    response = asyncio.run(dashboard_app.get_autonomous_development_endpoint(FakeRequest()))
    payload = _decode(response)

    assert response.status_code == 200
    assert set(payload) >= {"pipelines", "count", "registry_path", "audit"}
    route_paths = [getattr(route, "path", getattr(route, "path_format", None)) or (route.args[0] if getattr(route, "args", None) else None) for route in dashboard_app.routes]
    assert "/api/autonomous-development" in route_paths
    assert "/api/autonomous-development/pipelines" in route_paths
    assert "/api/autonomous-development/pipelines/{pipeline_id}" in route_paths
    assert "/api/autonomous-development/pipelines/{pipeline_id}/control" in route_paths

    html = (Path(dashboard_app.__file__).parent / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'data-panel="autonomous-development"' in html
    assert 'id="autonomous-development-panel"' in html
    assert "loadAutonomousDevelopment()" in html
    assert 'id="autonomous-development-pipelines"' in html
    assert 'id="autonomous-development-form"' in html
