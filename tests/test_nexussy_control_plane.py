from pathlib import Path

from .dashboard_sources import dashboard_source, dashboard_template

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
SOURCE = dashboard_source()
HTML = dashboard_template()


def test_nexussy_backend_routes_are_wired():
    expected = [
        'Route("/api/nexussy", get_nexussy_endpoint)',
        'Route("/api/nexussy/health", nexussy_health_endpoint)',
        'Route("/api/nexussy/config", nexussy_config_endpoint)',
        'Route("/api/nexussy/tools", nexussy_tools_endpoint)',
        'Route("/api/nexussy/sidecar/start", nexussy_start_sidecar_endpoint, methods=["POST"])',
        'Route("/api/nexussy/sessions", nexussy_sessions_endpoint)',
        'Route("/api/nexussy/pipelines", nexussy_start_pipeline_endpoint, methods=["POST"])',
        'Route("/api/nexussy/runs/{run_id}/status", nexussy_run_status_endpoint)',
        'Route("/api/nexussy/runs/{run_id}/events", nexussy_run_events_endpoint)',
        'Route("/api/nexussy/runs/{run_id}/artifacts", nexussy_run_artifacts_endpoint)',
        'Route("/api/nexussy/artifacts/{kind}", nexussy_artifact_content_endpoint)',
        'Route("/api/nexussy/sessions/{session_id}/interview-answer", nexussy_interview_answer_endpoint, methods=["POST"])',
        'Route("/api/nexussy/runs/{run_id}/control", nexussy_run_control_endpoint, methods=["POST"])',
        'Route("/api/nexussy/runs/{run_id}/inject", nexussy_inject_endpoint, methods=["POST"])',
        'Route("/api/nexussy/runs/{run_id}/steer", nexussy_steer_endpoint, methods=["POST"])',
        'Route("/api/nexussy/runs/{run_id}/workers", nexussy_workers_endpoint)',
    ]
    for route in expected:
        assert route in APP


def test_nexussy_frontend_tab_router_and_panel_are_wired():
    assert 'data-panel="nexussy"' in HTML
    assert 'id="nexussy-panel"' in HTML
    assert "{ id: 'nexussy', label: 'Nexussy'" in SOURCE
    assert "case 'nexussy': loadNexussy(); break;" in SOURCE
    assert "'self-improvement','autonomous-development','nexussy','scrolls'" in SOURCE
    assert "nexussy:'Nexussy'" in SOURCE


def test_nexussy_frontend_calls_control_plane_endpoints():
    for endpoint in [
        '/api/nexussy',
        '/api/nexussy/sidecar/start',
        '/api/nexussy/pipelines',
        '/api/nexussy/runs/${encodeURIComponent(ids.runId)}/control',
        '/api/nexussy/runs/${encodeURIComponent(ids.runId)}/steer',
        '/api/nexussy/runs/${encodeURIComponent(ids.runId)}/inject',
        '/api/nexussy/sessions/${encodeURIComponent(ids.sessionId)}/interview-answer',
        '/api/nexussy/artifacts/${encodeURIComponent(kind)}',
    ]:
        assert endpoint in SOURCE


def test_nexussy_launch_defaults_to_full_stage_model_override():
    assert 'NEXUSSY_DEFAULT_STAGE_MODEL = os.getenv(' in APP
    assert '"openrouter/openai/gpt-4o-mini"' in APP
    assert 'return {stage: model for stage in NEXUSSY_STAGES}' in APP
    assert 'data.get("auto_model_override", True)' in APP
    assert 'model_guard' in APP
