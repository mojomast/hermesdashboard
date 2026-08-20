import asyncio

from tests.test_games_tab import _install_framework_stubs

_install_framework_stubs()

import app as dashboard_app
from tests.dashboard_sources import DASHBOARD_JS, dashboard_template


class DummyRequest:
    def __init__(self, payload=None, path_params=None):
        self._payload = payload or {}
        self.path_params = path_params or {}

    async def json(self):
        return self._payload


def _json_response_payload(response):
    body = getattr(response, "body", b"")
    if isinstance(body, bytes):
        import json

        return json.loads(body.decode("utf-8"))
    return getattr(response, "content", {})


def test_parallel_arena_tab_is_registered_with_panel_and_router():
    html = dashboard_template()
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert 'data-panel="parallel-arena"' in html
    assert 'id="parallel-arena-panel"' in html
    assert 'id="parallel-arena-task"' in html
    assert 'id="parallel-arena-execution-mode"' in html
    assert 'value="local_worker"' in html
    assert "loadParallelArena()" in js
    assert "{ id: 'parallel-arena', label: 'Parallel Arena', locked: true }" in js
    assert "function getLockedDashboardTabIds()" in js
    assert "'/api/parallel-arena'" in js
    assert "'/api/parallel-arena/provider-advisor'" in js
    assert "Provider Choice Autopilot" in js
    assert "refreshParallelArenaProviderAdvisor" in js
    assert "parallel-arena-provider-advisor" in html
    assert "execution_mode: executionMode" in js
    assert "current.execution_mode" in js
    assert "current.run_dir || current.artifact_dir" in js
    assert "renderParallelArenaArtifactButtons" in js
    assert "openParallelArenaArtifact" in js
    assert "/api/parallel-arena/runs/${encodeURIComponent(runId)}/artifacts/" in js
    assert 'parallel-arena' in js.split('const validPanels =', 1)[1].split(';', 1)[0]


def test_parallel_arena_routes_are_registered():
    paths = {getattr(route, "path", None) for route in dashboard_app.routes}

    assert "/api/parallel-arena" in paths
    assert "/api/parallel-arena/provider-advisor" in paths
    assert "/api/parallel-arena/runs" in paths
    assert "/api/parallel-arena/runs/{run_id}" in paths
    assert "/api/parallel-arena/runs/{run_id}/artifacts/{lane_id}/{artifact_name}" in paths
    assert "/api/parallel-arena/runs/{run_id}/impact-plan/{artifact_name}" in paths
    assert "/api/parallel-arena/runs/{run_id}/cancel" in paths


def test_parallel_arena_provider_advisor_is_secret_safe_and_task_aware(monkeypatch):
    monkeypatch.delenv("PARALLEL_ARENA_ALLOW_PROVIDER_SPEND", raising=False)
    advisor = dashboard_app.build_parallel_arena_provider_advisor(
        "Build a dashboard code feature with tests quickly and cheaply",
        execution_mode="local_worker",
        lane_count=5,
        config={"model": {"provider": "anthropic", "default": "claude-test"}},
        env={"ANTHROPIC_API_KEY": "secret-value"},
    )

    assert advisor["schema_version"] == "parallel_arena.provider_advisor.v1"
    assert advisor["recommended_provider"] == "local_worker"
    assert advisor["launch_policy"]["secret_values_returned"] is False
    assert advisor["spend_enabled"] is False
    anthropic = next(item for item in advisor["candidates"] if item["provider"] == "anthropic")
    assert anthropic["configured"] is True
    assert "secret-value" not in str(advisor)
    assert any("provider spend gate is off" in reason for reason in anthropic["reasons"])


def test_parallel_arena_provider_advisor_endpoint_and_run_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "PARALLEL_ARENA_RUNS_DIR", tmp_path)
    monkeypatch.delenv("PARALLEL_ARENA_ALLOW_PROVIDER_SPEND", raising=False)

    response = asyncio.run(
        dashboard_app.get_parallel_arena_provider_advisor_endpoint(
            DummyRequest({"task": "Research and implement a tested dashboard feature", "max_lanes": 3, "execution_mode": "local_worker"})
        )
    )
    payload = _json_response_payload(response)
    assert payload["ok"] is True
    assert payload["advisor"]["recommended_provider"]
    assert payload["advisor"]["candidates"]

    run = dashboard_app.create_parallel_arena_run(
        "Research and implement a tested dashboard feature",
        ["planner", "implementer"],
        max_lanes=2,
        execution_mode="simulated",
    )
    assert run["provider_advisor"]["schema_version"] == "parallel_arena.provider_advisor.v1"
    saved = dashboard_app._parallel_arena_read_run(tmp_path / f"{run['run_id']}.json")
    assert saved["provider_advisor"]["recommended_provider"] == run["provider_advisor"]["recommended_provider"]
    assert dashboard_app.get_parallel_arena_status()["runs"][0]["provider_advisor"]["adapter_status"]


def test_parallel_arena_provider_autopilot_frontend_controls_are_wired():
    html = dashboard_template()
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert "Advise Provider" in html
    assert 'id="parallel-arena-provider-advisor"' in html
    assert "function buildParallelArenaProviderAdvisor" not in js  # backend owns scoring
    assert "function renderParallelArenaProviderAdvisor" in js
    assert "function refreshParallelArenaProviderAdvisor" in js
    assert "collectParallelArenaLaunchInput" in js
    assert "current.provider_advisor" in js
    assert "Provider Autopilot" in js


def test_parallel_arena_endpoint_creates_structured_local_run(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "PARALLEL_ARENA_RUNS_DIR", tmp_path)

    response = asyncio.run(
        dashboard_app.create_parallel_arena_run_endpoint(
            DummyRequest(
                {
                    "task": "Build a dashboard feature and verify it with tests",
                    "strategies": ["planner-researcher", "implementation-first", "critic-reviewer"],
                    "max_lanes": 3,
                    "execution_mode": "simulated",
                }
            )
        )
    )
    payload = _json_response_payload(response)

    assert payload["ok"] is True
    run = payload["run"]
    assert run["status"] == "completed"
    assert run["execution_mode"] == "simulated"
    assert run["artifact_dir"] == run["run_dir"]
    assert run["lane_count"] == 3
    assert len(run["lanes"]) == 3
    assert all(lane["execution_mode"] == "simulated" for lane in run["lanes"])
    assert all(lane["artifacts"].get("artifact_paths") for lane in run["lanes"])
    assert run["synthesis"]["winner_lane_id"]
    assert (tmp_path / f"{run['run_id']}.json").exists()
    assert (tmp_path / run["run_id"]).is_dir()
    assert run["impact_plan"]["schema_version"] == "parallel_arena.impact_plan.v1"
    assert run["impact_plan"]["candidate_files"]
    assert run["impact_plan"]["verification_commands"]
    assert (tmp_path / run["run_id"] / "impact_plan" / "impact_plan.json").exists()
    assert (tmp_path / run["run_id"] / "impact_plan" / "IMPACT_PLAN.md").exists()

    status_payload = dashboard_app.get_parallel_arena_status()
    assert "local_worker" in status_payload["execution_modes"]
    assert status_payload["current"]["run_id"] == run["run_id"]
    assert status_payload["runs"][0]["lane_count"] == 3
    assert status_payload["runs"][0]["artifact_dir"] == run["artifact_dir"]


def test_parallel_arena_endpoint_accepts_local_worker_mode_and_persists_lane_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "PARALLEL_ARENA_RUNS_DIR", tmp_path)

    response = asyncio.run(
        dashboard_app.create_parallel_arena_run_endpoint(
            DummyRequest(
                {
                    "task": "Run actual local workers and persist lane artifacts",
                    "strategies": ["worker-implementer", "worker-critic"],
                    "max_lanes": 2,
                    "execution_mode": "local_worker",
                }
            )
        )
    )
    payload = _json_response_payload(response)

    assert payload["ok"] is True
    run = payload["run"]
    assert run["execution_mode"] == "local_worker"
    assert run["status"] == "completed"
    assert run["completed_lanes"] == 2
    assert (tmp_path / run["run_id"]).is_dir()
    for lane in run["lanes"]:
        assert lane["execution_mode"] == "local_worker"
        assert lane["status"] == "completed"
        artifact_paths = lane["artifacts"]["artifact_paths"]
        manifest_names = {item["name"] for item in lane["artifact_manifest"]}
        assert (tmp_path / run["run_id"] / lane["lane_id"] / "input.json").exists()
        assert (tmp_path / run["run_id"] / lane["lane_id"] / "result.json").exists()
        assert (tmp_path / run["run_id"] / lane["lane_id"] / "lane_proposal.md").exists()
        assert (tmp_path / run["run_id"] / lane["lane_id"] / "scorecard.json").exists()
        assert artifact_paths["worker_artifact"].endswith("worker_artifact.json")
        assert {"input", "result", "worker-artifact", "lane-proposal", "scorecard"}.issubset(manifest_names)


def test_parallel_arena_artifact_endpoint_returns_safe_browsable_content(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "PARALLEL_ARENA_RUNS_DIR", tmp_path)
    run = dashboard_app.create_parallel_arena_run(
        "Produce browsable lane artifacts for arena inspection",
        ["artifact-reviewer"],
        max_lanes=1,
        execution_mode="local_worker",
    )
    lane = run["lanes"][0]

    response = asyncio.run(
        dashboard_app.get_parallel_arena_artifact_endpoint(
            DummyRequest(path_params={"run_id": run["run_id"], "lane_id": lane["lane_id"], "artifact_name": "lane-proposal"})
        )
    )
    payload = _json_response_payload(response)

    assert payload["ok"] is True
    assert payload["artifact"]["kind"] == "markdown"
    assert payload["artifact"]["file_name"] == "lane_proposal.md"
    assert "Parallel Arena Lane Proposal" in payload["content"]
    assert "path" not in payload["artifact"]

    scorecard_response = asyncio.run(
        dashboard_app.get_parallel_arena_artifact_endpoint(
            DummyRequest(path_params={"run_id": run["run_id"], "lane_id": lane["lane_id"], "artifact_name": "scorecard"})
        )
    )
    scorecard_payload = _json_response_payload(scorecard_response)
    assert scorecard_payload["json"]["rubric"]["artifact_backed"] is True



def test_parallel_arena_skill_forge_promotes_winner_to_reviewable_skill_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "PARALLEL_ARENA_RUNS_DIR", tmp_path)
    run = dashboard_app.create_parallel_arena_run(
        "Create a reusable workflow from the winning lane",
        ["skill-forge-implementer", "critic-reviewer"],
        max_lanes=2,
        execution_mode="local_worker",
    )

    response = asyncio.run(
        dashboard_app.forge_parallel_arena_winner_skill_endpoint(
            DummyRequest(path_params={"run_id": run["run_id"]})
        )
    )
    payload = _json_response_payload(response)

    assert payload["ok"] is True
    promotion = payload["promotion"]
    assert promotion["status"] == "drafted"
    assert promotion["promotion_ready"] is True
    assert promotion["source_lane_id"] == run["synthesis"]["winner_lane_id"]
    assert promotion["skill_name"].startswith("arena-")
    artifact_names = {item["name"] for item in promotion["artifacts"]}
    assert {"skill-draft", "test-plan", "promotion-manifest"}.issubset(artifact_names)
    assert "path" not in promotion["artifacts"][0]

    forge_dir = tmp_path / run["run_id"] / "skill_forge" / promotion["skill_name"]
    assert (forge_dir / "SKILL.md").exists()
    assert (forge_dir / "TEST_PLAN.md").exists()
    assert "## Promotion Checklist" in (forge_dir / "SKILL.md").read_text(encoding="utf-8")

    saved = dashboard_app._parallel_arena_read_run(tmp_path / f"{run['run_id']}.json")
    assert saved["skill_forge"]["skill_name"] == promotion["skill_name"]


def test_parallel_arena_skill_forge_artifact_endpoint_is_safe_and_browsable(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "PARALLEL_ARENA_RUNS_DIR", tmp_path)
    run = dashboard_app.create_parallel_arena_run(
        "Forge browsable promotion artifacts",
        ["skill-forge-implementer"],
        max_lanes=1,
        execution_mode="local_worker",
    )
    dashboard_app.forge_parallel_arena_winner_skill(run)
    dashboard_app._parallel_arena_write_run(run)

    response = asyncio.run(
        dashboard_app.get_parallel_arena_skill_forge_artifact_endpoint(
            DummyRequest(path_params={"run_id": run["run_id"], "artifact_name": "skill-draft"})
        )
    )
    payload = _json_response_payload(response)

    assert payload["ok"] is True
    assert payload["artifact"]["kind"] == "markdown"
    assert payload["artifact"]["file_name"] == "SKILL.md"
    assert "## Capability Intent" in payload["content"]
    assert "path" not in payload["artifact"]


def test_parallel_arena_skill_forge_routes_and_frontend_controls_are_wired():
    paths = {getattr(route, "path", None) for route in dashboard_app.routes}
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert "/api/parallel-arena/runs/{run_id}/skill-forge" in paths
    assert "/api/parallel-arena/runs/{run_id}/skill-forge/{artifact_name}" in paths
    assert "function renderParallelArenaSkillForge" in js
    assert "forgeParallelArenaWinnerSkill" in js
    assert "openParallelArenaSkillForgeArtifact" in js
    assert "Forge Winner Skill Draft" in js

def test_parallel_arena_mission_plan_compiles_winner_to_replayable_campaign_dag(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "PARALLEL_ARENA_RUNS_DIR", tmp_path)
    run = dashboard_app.create_parallel_arena_run(
        "Turn an arena winner into an executable mission DAG",
        ["mission-planner", "critic-reviewer"],
        max_lanes=2,
        execution_mode="local_worker",
    )

    response = asyncio.run(
        dashboard_app.build_parallel_arena_mission_plan_endpoint(
            DummyRequest(path_params={"run_id": run["run_id"]})
        )
    )
    payload = _json_response_payload(response)

    assert payload["ok"] is True
    mission = payload["mission_plan"]
    assert mission["schema_version"] == "parallel_arena.mission_plan.v1"
    assert mission["status"] == "drafted"
    assert mission["source_lane_id"] == run["synthesis"]["winner_lane_id"]
    assert len(mission["nodes"]) >= 5
    assert {"from": "intake", "to": "impact-map"} in mission["edges"]
    assert mission["execution_policy"]["provider_spend"] == "operator opt-in"
    assert "MISSION_BRIEF.md" in mission["replay_command_hint"]
    assert "path" not in mission["artifacts"][0]

    plan_dir = tmp_path / run["run_id"] / "mission_plan"
    assert (plan_dir / "mission_plan.json").exists()
    assert (plan_dir / "MISSION_BRIEF.md").exists()
    saved = dashboard_app._parallel_arena_read_run(tmp_path / f"{run['run_id']}.json")
    assert saved["mission_plan"]["source_lane_id"] == mission["source_lane_id"]


def test_parallel_arena_mission_plan_artifact_endpoint_is_safe_and_browsable(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "PARALLEL_ARENA_RUNS_DIR", tmp_path)
    run = dashboard_app.create_parallel_arena_run(
        "Browse mission DAG artifacts safely",
        ["mission-planner"],
        max_lanes=1,
        execution_mode="local_worker",
    )
    dashboard_app.build_parallel_arena_mission_plan(run)
    dashboard_app._parallel_arena_write_run(run)

    response = asyncio.run(
        dashboard_app.get_parallel_arena_mission_plan_artifact_endpoint(
            DummyRequest(path_params={"run_id": run["run_id"], "artifact_name": "mission-plan"})
        )
    )
    payload = _json_response_payload(response)

    assert payload["ok"] is True
    assert payload["artifact"]["kind"] == "json"
    assert payload["artifact"]["file_name"] == "mission_plan.json"
    assert payload["json"]["nodes"][0]["id"] == "intake"
    assert "path" not in payload["artifact"]


def test_parallel_arena_mission_plan_routes_and_frontend_controls_are_wired():
    paths = {getattr(route, "path", None) for route in dashboard_app.routes}
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert "/api/parallel-arena/runs/{run_id}/mission-plan" in paths
    assert "/api/parallel-arena/runs/{run_id}/mission-plan/{artifact_name}" in paths
    assert "function renderParallelArenaMissionPlan" in js
    assert "buildParallelArenaMissionPlan" in js
    assert "openParallelArenaMissionPlanArtifact" in js
    assert "Build Mission DAG" in js
    assert "Mission Control DAG" in js



def test_parallel_arena_workflow_replay_exports_executable_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "PARALLEL_ARENA_RUNS_DIR", tmp_path)
    run = dashboard_app.create_parallel_arena_run(
        "Replay a winning lane as a deterministic workflow",
        ["workflow-planner", "critic-reviewer"],
        max_lanes=2,
        execution_mode="local_worker",
    )

    response = asyncio.run(
        dashboard_app.export_parallel_arena_workflow_replay_endpoint(
            DummyRequest(path_params={"run_id": run["run_id"]})
        )
    )
    payload = _json_response_payload(response)

    assert payload["ok"] is True
    replay = payload["workflow_replay"]
    assert replay["schema_version"] == "parallel_arena.workflow_replay.v1"
    assert replay["status"] == "ready"
    assert replay["source_lane_id"] == run["synthesis"]["winner_lane_id"]
    assert replay["nodes"][0]["status"] == "ready"
    assert replay["nodes"][1]["status"] == "blocked"
    assert "list_nodes" in replay["operator_commands"]
    assert "path" not in replay["artifacts"][0]

    replay_dir = tmp_path / run["run_id"] / "workflow_replay"
    assert (replay_dir / "workflow_replay.json").exists()
    assert (replay_dir / "replay_driver.py").exists()
    assert (replay_dir / "README.md").exists()
    assert "--next" in (replay_dir / "replay_driver.py").read_text(encoding="utf-8")
    saved = dashboard_app._parallel_arena_read_run(tmp_path / f"{run['run_id']}.json")
    assert saved["workflow_replay"]["schema_version"] == "parallel_arena.workflow_replay.v1"


def test_parallel_arena_workflow_replay_artifact_endpoint_is_safe_and_browsable(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "PARALLEL_ARENA_RUNS_DIR", tmp_path)
    run = dashboard_app.create_parallel_arena_run(
        "Browse workflow replay artifacts safely",
        ["workflow-planner"],
        max_lanes=1,
        execution_mode="local_worker",
    )
    dashboard_app.export_parallel_arena_workflow_replay(run)
    dashboard_app._parallel_arena_write_run(run)

    response = asyncio.run(
        dashboard_app.get_parallel_arena_workflow_replay_artifact_endpoint(
            DummyRequest(path_params={"run_id": run["run_id"], "artifact_name": "workflow-replay"})
        )
    )
    payload = _json_response_payload(response)

    assert payload["ok"] is True
    assert payload["artifact"]["kind"] == "json"
    assert payload["artifact"]["file_name"] == "workflow_replay.json"
    assert payload["json"]["nodes"][0]["id"] == "intake"
    assert "path" not in payload["artifact"]


def test_parallel_arena_workflow_replay_routes_and_frontend_controls_are_wired():
    paths = {getattr(route, "path", None) for route in dashboard_app.routes}
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert "/api/parallel-arena/runs/{run_id}/workflow-replay" in paths
    assert "/api/parallel-arena/runs/{run_id}/workflow-replay/{artifact_name}" in paths
    assert "function renderParallelArenaWorkflowReplay" in js
    assert "exportParallelArenaWorkflowReplay" in js
    assert "openParallelArenaWorkflowReplayArtifact" in js
    assert "Export Replay Bundle" in js
    assert "Workflow Replay Studio" in js


def test_parallel_arena_impact_plan_is_built_and_browsable(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "PARALLEL_ARENA_RUNS_DIR", tmp_path)
    run = dashboard_app.create_parallel_arena_run(
        "Add Parallel Arena dashboard tests and static JavaScript rendering",
        ["impact-planner"],
        max_lanes=1,
        execution_mode="simulated",
    )

    impact = run["impact_plan"]
    assert impact["status"] == "ready"
    assert impact["terms"]
    assert any(item["path"] == "tests/test_parallel_arena_panel.py" for item in impact["candidate_files"] + impact["candidate_tests"])
    assert any("pytest" in command for command in impact["verification_commands"])
    artifact_names = {item["name"] for item in impact["artifacts"]}
    assert {"impact-plan", "impact-brief"}.issubset(artifact_names)

    response = asyncio.run(
        dashboard_app.get_parallel_arena_impact_plan_artifact_endpoint(
            DummyRequest(path_params={"run_id": run["run_id"], "artifact_name": "impact-plan"})
        )
    )
    payload = _json_response_payload(response)

    assert payload["ok"] is True
    assert payload["artifact"]["kind"] == "json"
    assert payload["json"]["schema_version"] == "parallel_arena.impact_plan.v1"
    assert "path" not in payload["artifact"]


def test_parallel_arena_impact_plan_frontend_controls_are_wired():
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert "function renderParallelArenaImpactPlan" in js
    assert "openParallelArenaImpactPlanArtifact" in js
    assert "Semantic Patch Impact Plan" in js
    assert "/api/parallel-arena/runs/${encodeURIComponent(runId)}/impact-plan/" in js
    assert "renderParallelArenaImpactPlan(current)" in js


def test_parallel_arena_canary_harness_exports_privacy_safe_promotion_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "PARALLEL_ARENA_RUNS_DIR", tmp_path)
    run = dashboard_app.create_parallel_arena_run(
        "Gate a replay workflow before using it as a training episode",
        ["canary-builder", "critic-reviewer"],
        max_lanes=2,
        execution_mode="local_worker",
    )
    dashboard_app.export_parallel_arena_workflow_replay(run)
    dashboard_app._parallel_arena_write_run(run)

    response = asyncio.run(
        dashboard_app.build_parallel_arena_canary_harness_endpoint(
            DummyRequest(path_params={"run_id": run["run_id"]})
        )
    )
    payload = _json_response_payload(response)

    assert payload["ok"] is True
    canary = payload["canary_harness"]
    assert canary["schema_version"] == "parallel_arena.canary_harness.v1"
    assert canary["status"] == "ready"
    assert canary["source_lane_id"] == run["synthesis"]["winner_lane_id"]
    assert canary["privacy"]["raw_prompts"] is False
    assert canary["privacy"]["launch_prompt_hashes_only"] is True
    assert {"schema-present", "node-chain-ready", "privacy-safe"}.issubset(set(canary["promotion_gate"]["required_passes"]))
    assert all("launch_prompt" not in node for node in canary["nodes"])
    assert all(node["launch_prompt_sha256"] for node in canary["nodes"])
    assert "path" not in canary["artifacts"][0]

    canary_dir = tmp_path / run["run_id"] / "canary_harness"
    assert (canary_dir / "canary_suite.json").exists()
    assert (canary_dir / "canary_driver.py").exists()
    assert "--json" in (canary_dir / "canary_driver.py").read_text(encoding="utf-8")
    saved = dashboard_app._parallel_arena_read_run(tmp_path / f"{run['run_id']}.json")
    assert saved["canary_harness"]["schema_version"] == "parallel_arena.canary_harness.v1"


def test_parallel_arena_canary_harness_artifact_endpoint_is_safe_and_browsable(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "PARALLEL_ARENA_RUNS_DIR", tmp_path)
    run = dashboard_app.create_parallel_arena_run(
        "Browse canary harness artifacts safely",
        ["canary-builder"],
        max_lanes=1,
        execution_mode="local_worker",
    )
    dashboard_app.build_parallel_arena_canary_harness(run)
    dashboard_app._parallel_arena_write_run(run)

    response = asyncio.run(
        dashboard_app.get_parallel_arena_canary_harness_artifact_endpoint(
            DummyRequest(path_params={"run_id": run["run_id"], "artifact_name": "canary-suite"})
        )
    )
    payload = _json_response_payload(response)

    assert payload["ok"] is True
    assert payload["artifact"]["kind"] == "json"
    assert payload["artifact"]["file_name"] == "canary_suite.json"
    assert payload["json"]["promotion_gate"]["required_passes"]
    assert "path" not in payload["artifact"]


def test_parallel_arena_canary_harness_routes_and_frontend_controls_are_wired():
    paths = {getattr(route, "path", None) for route in dashboard_app.routes}
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert "/api/parallel-arena/runs/{run_id}/canary-harness" in paths
    assert "/api/parallel-arena/runs/{run_id}/canary-harness/{artifact_name}" in paths
    assert "function renderParallelArenaCanaryHarness" in js
    assert "buildParallelArenaCanaryHarness" in js
    assert "openParallelArenaCanaryHarnessArtifact" in js
    assert "Build Canary Harness" in js
    assert "Training Episode Canary Harness" in js
    assert "renderParallelArenaCanaryHarness(current)" in js



def test_parallel_arena_demo_reel_packages_canary_gated_run_for_showcase(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "PARALLEL_ARENA_RUNS_DIR", tmp_path)
    run = dashboard_app.create_parallel_arena_run(
        "Impress the operator with a full evidence-backed arena demo",
        ["showrunner", "critic-reviewer"],
        max_lanes=2,
        execution_mode="local_worker",
    )
    dashboard_app.build_parallel_arena_canary_harness(run)
    dashboard_app._parallel_arena_write_run(run)

    response = asyncio.run(
        dashboard_app.build_parallel_arena_demo_reel_endpoint(
            DummyRequest(path_params={"run_id": run["run_id"]})
        )
    )
    payload = _json_response_payload(response)

    assert payload["ok"] is True
    demo = payload["demo_reel"]
    assert demo["schema_version"] == "parallel_arena.demo_reel.v1"
    assert demo["status"] == "ready"
    assert demo["source_lane_id"] == run["synthesis"]["winner_lane_id"]
    assert "converted competing lanes" in demo["headline"]
    assert demo["privacy"]["raw_prompts_included"] is False
    assert demo["privacy"]["artifact_paths_exposed_in_api"] is False
    assert any(card["label"] == "Canary checks" and card["value"] >= 3 for card in demo["cards"])
    assert "path" not in demo["artifacts"][0]

    demo_dir = tmp_path / run["run_id"] / "demo_reel"
    assert (demo_dir / "DEMO_REEL.md").exists()
    assert (demo_dir / "demo_reel.json").exists()
    assert "## Why this is cool" in (demo_dir / "DEMO_REEL.md").read_text(encoding="utf-8")
    saved = dashboard_app._parallel_arena_read_run(tmp_path / f"{run['run_id']}.json")
    assert saved["demo_reel"]["schema_version"] == "parallel_arena.demo_reel.v1"


def test_parallel_arena_demo_reel_artifact_endpoint_is_safe_and_browsable(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "PARALLEL_ARENA_RUNS_DIR", tmp_path)
    run = dashboard_app.create_parallel_arena_run(
        "Browse demo reel artifacts safely",
        ["showrunner"],
        max_lanes=1,
        execution_mode="local_worker",
    )
    dashboard_app.build_parallel_arena_demo_reel(run)
    dashboard_app._parallel_arena_write_run(run)

    response = asyncio.run(
        dashboard_app.get_parallel_arena_demo_reel_artifact_endpoint(
            DummyRequest(path_params={"run_id": run["run_id"], "artifact_name": "demo-json"})
        )
    )
    payload = _json_response_payload(response)

    assert payload["ok"] is True
    assert payload["artifact"]["kind"] == "json"
    assert payload["artifact"]["file_name"] == "demo_reel.json"
    assert payload["json"]["schema_version"] == "parallel_arena.demo_reel.v1"
    assert "path" not in payload["artifact"]


def test_parallel_arena_demo_reel_routes_and_frontend_controls_are_wired():
    paths = {getattr(route, "path", None) for route in dashboard_app.routes}
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert "/api/parallel-arena/runs/{run_id}/demo-reel" in paths
    assert "/api/parallel-arena/runs/{run_id}/demo-reel/{artifact_name}" in paths
    assert "function renderParallelArenaDemoReel" in js
    assert "buildParallelArenaDemoReel" in js
    assert "openParallelArenaDemoReelArtifact" in js
    assert "Build Demo Reel" in js
    assert "renderParallelArenaDemoReel(current)" in js



def test_parallel_arena_hermes_cli_adapter_is_registered_and_gated(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "PARALLEL_ARENA_RUNS_DIR", tmp_path)
    monkeypatch.delenv("PARALLEL_ARENA_ALLOW_PROVIDER_SPEND", raising=False)
    monkeypatch.delenv("PARALLEL_ARENA_ENABLE_HERMES_ADAPTER", raising=False)

    run = dashboard_app.create_parallel_arena_run(
        "Use a real model-backed lane only when operator spend gates are enabled",
        ["hermes-reviewer"],
        max_lanes=1,
        execution_mode="hermes_cli",
    )

    assert "hermes_cli" in dashboard_app.get_parallel_arena_status()["execution_modes"]
    assert run["execution_mode"] == "hermes_cli"
    assert run["status"] == "failed"
    lane = run["lanes"][0]
    assert lane["execution_mode"] == "hermes_cli"
    assert lane["status"] == "failed"
    assert lane["artifacts"]["gate_required"] is True
    assert (tmp_path / run["run_id"] / lane["lane_id"] / "hermes_prompt.md").exists()
    assert "PARALLEL_ARENA_ALLOW_PROVIDER_SPEND" in lane["error"]


def test_parallel_arena_hermes_cli_adapter_runs_when_explicitly_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "PARALLEL_ARENA_RUNS_DIR", tmp_path)
    monkeypatch.setenv("PARALLEL_ARENA_ALLOW_PROVIDER_SPEND", "1")
    monkeypatch.setenv("PARALLEL_ARENA_ENABLE_HERMES_ADAPTER", "1")
    monkeypatch.setenv("PARALLEL_ARENA_HERMES_BIN", "hermes-test")

    calls = []

    class Completed:
        returncode = 0
        stdout = "Lane summary\nVerification: python -m pytest -q tests/test_parallel_arena_panel.py\n"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Completed()

    monkeypatch.setattr(dashboard_app.subprocess, "run", fake_run)
    run = dashboard_app.create_parallel_arena_run(
        "Launch actual Hermes model lanes through a gated CLI adapter",
        ["hermes-implementer"],
        max_lanes=1,
        execution_mode="hermes_cli",
    )

    lane = run["lanes"][0]
    assert run["status"] == "completed"
    assert lane["status"] == "completed"
    assert lane["execution_mode"] == "hermes_cli"
    assert lane["score"] >= 60
    assert calls and calls[0][0][:3] == ["hermes-test", "chat", "-q"]
    assert "--toolsets" in calls[0][0]
    assert (tmp_path / run["run_id"] / lane["lane_id"] / "hermes_stdout.md").read_text(encoding="utf-8").startswith("Lane summary")
    manifest_names = {item["name"] for item in lane["artifact_manifest"]}
    assert {"hermes-prompt", "hermes-stdout", "hermes-result"}.issubset(manifest_names)


def test_parallel_arena_hermes_cli_frontend_copy_is_wired():
    html = dashboard_template()
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert 'value="hermes_cli"' in html
    assert "Hermes CLI adapter" in html
    assert "PARALLEL_ARENA_ENABLE_HERMES_ADAPTER" in html
    assert "recommended_execution_mode === 'hermes_cli'" in js
    assert "real model-backed subprocess lane" in js
