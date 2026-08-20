from pathlib import Path

import app as dashboard_app


ROOT = Path(__file__).resolve().parents[1]


def test_static_route_is_registered_for_extracted_assets():
    static_route = next((route for route in dashboard_app.routes if getattr(route, "path", "").startswith("/static")), None)

    assert static_route is not None
    assert (ROOT / "static" / "js" / "dashboard.js").is_file()
    assert (ROOT / "static" / "css" / "dashboard.css").is_file()


def test_docker_assets_define_dashboard_container_runtime():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    runner = (ROOT / "run-dashboard-docker.sh").read_text(encoding="utf-8")

    assert "FROM python:3.11-slim" in dockerfile
    assert "uvicorn" in dockerfile
    assert "hermesdashboard:" in compose
    assert "host.docker.internal" in compose
    assert 'DASHBOARD_RUNNING_IN_DOCKER: "true"' in compose
    assert '"${HERMES_HOME:-$HOME/.hermes}:/hermes-home"' in compose
    assert '"${HERMES_AGENT_PATH:-$HOME/.hermes/hermes-agent}:/hermes-agent:ro"' in compose
    assert "docker compose" in runner
    assert "DOCKER_HERMES_API" in runner
