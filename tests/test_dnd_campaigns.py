import asyncio
import json
import sys
import types


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
from tests.dashboard_sources import dashboard_source


class FakeRequest:
    def __init__(self, payload=None, path_params=None, query_params=None):
        self._payload = payload
        self.path_params = path_params or {}
        self.query_params = query_params or {}

    async def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _decode(response):
    return json.loads(response.body.decode("utf-8"))


def test_dnd_campaign_helpers_persist_campaign_players_characters_and_dice(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    campaign = dashboard_app.create_dnd_campaign("Mines", description="Starter adventure")
    human = dashboard_app.create_dnd_player(campaign["id"], "Alice", "human")
    subagent = dashboard_app.create_dnd_player(
        campaign["id"], "Goblin", "subagent", agent_prompt="Protect the cave."
    )
    character = dashboard_app.create_dnd_character(
        campaign["id"], human["id"], "Aria", character_sheet={"class": "Wizard"}
    )

    db_path = tmp_path / "dnd" / "campaigns.sqlite3"
    assert db_path.exists()
    assert dashboard_app.roll_dnd_dice("1d20+3", seed="attack") == dashboard_app.roll_dnd_dice("1d20+3", seed="attack")
    assert 4 <= dashboard_app.roll_dnd_dice("1d20+3", seed="attack")["total"] <= 23
    assert 2 <= dashboard_app.roll_dnd_dice("2d6", seed="damage")["total"] <= 12

    campaigns = dashboard_app.list_dnd_campaigns()
    loaded = dashboard_app.get_dnd_campaign(campaign["id"])
    players = dashboard_app.list_dnd_players(campaign["id"])
    characters = dashboard_app.list_dnd_characters(campaign["id"])

    assert campaigns[0]["name"] == "Mines"
    assert loaded["description"] == "Starter adventure"
    assert {p["controller_type"] for p in players} == {"human", "subagent"}
    assert next(p for p in players if p["id"] == subagent["id"])["agent_prompt"] == "Protect the cave."
    assert characters[0]["name"] == character["name"] == "Aria"
    assert characters[0]["character_sheet"] == {"class": "Wizard"}


def test_dnd_campaign_endpoints_and_auto_turn_are_wired(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    async def offline_hermes_json(messages, **kwargs):
        raise RuntimeError("offline in regression test")

    monkeypatch.setattr(dashboard_app, "call_dnd_hermes_json", offline_hermes_json)

    create_response = asyncio.run(
        dashboard_app.dnd_campaigns_endpoint(FakeRequest({"name": "Keep", "description": "A small keep"}))
    )
    campaign = _decode(create_response)["campaign"]
    human_response = asyncio.run(
        dashboard_app.create_dnd_player_endpoint(
            FakeRequest(
                {"name": "Alice", "controller_type": "human"},
                path_params={"campaign_id": campaign["id"]},
            )
        )
    )
    subagent_response = asyncio.run(
        dashboard_app.create_dnd_player_endpoint(
            FakeRequest(
                {"name": "Scout", "controller_type": "subagent", "agent_prompt": "Scout ahead"},
                path_params={"campaign_id": campaign["id"]},
            )
        )
    )
    human = _decode(human_response)["player"]
    subagent = _decode(subagent_response)["player"]

    turn_response = asyncio.run(
        dashboard_app.dnd_auto_turn_endpoint(
            FakeRequest(
                {"human_actions": {human["id"]: "I inspect the door."}},
                path_params={"campaign_id": campaign["id"]},
            )
        )
    )
    payload = _decode(turn_response)
    events_response = asyncio.run(
        dashboard_app.dnd_campaign_events_endpoint(FakeRequest(path_params={"campaign_id": campaign["id"]}))
    )
    detail_response = asyncio.run(
        dashboard_app.dnd_campaign_detail_endpoint(FakeRequest(path_params={"campaign_id": campaign["id"]}))
    )
    paths = [getattr(route, "path", None) for route in dashboard_app.routes]

    assert create_response.status_code == human_response.status_code == subagent_response.status_code == 200
    assert turn_response.status_code == events_response.status_code == detail_response.status_code == 200
    assert payload["turn"]["turn_number"] == 1
    assert payload["campaign"]["turn_number"] == 2
    assert {action["player_id"] for action in payload["actions"]} == {human["id"], subagent["id"]}
    assert next(a for a in payload["actions"] if a["player_id"] == human["id"])["action_text"] == "I inspect the door."
    assert "Scout" in next(a for a in payload["actions"] if a["player_id"] == subagent["id"])["action_text"]
    assert any(event["event_type"] == "dm_narration" for event in payload["events"])
    assert _decode(events_response)["events"][0]["event_type"] == "dm_narration"
    assert _decode(detail_response)["campaign"]["id"] == campaign["id"]
    assert "/api/dnd/campaigns" in paths
    assert "/api/dnd/campaigns/{campaign_id}" in paths
    assert "/api/dnd/campaigns/{campaign_id}/players" in paths
    assert "/api/dnd/campaigns/{campaign_id}/turns/auto" in paths
    assert "/api/dnd/campaigns/{campaign_id}/events" in paths


def test_dnd_endpoints_validate_bad_json_controller_and_missing_campaign(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    bad_json = asyncio.run(dashboard_app.dnd_campaigns_endpoint(FakeRequest(ValueError("bad json"))))
    missing_name = asyncio.run(dashboard_app.dnd_campaigns_endpoint(FakeRequest({"description": "no name"})))
    missing_campaign = asyncio.run(
        dashboard_app.create_dnd_player_endpoint(
            FakeRequest({"name": "Bob", "controller_type": "human"}, path_params={"campaign_id": "missing"})
        )
    )
    campaign = dashboard_app.create_dnd_campaign("Validation")
    invalid_controller = asyncio.run(
        dashboard_app.create_dnd_player_endpoint(
            FakeRequest({"name": "Bot", "controller_type": "robot"}, path_params={"campaign_id": campaign["id"]})
        )
    )

    assert bad_json.status_code == 400
    assert missing_name.status_code == 400
    assert missing_campaign.status_code == 404
    bad_actions = asyncio.run(
        dashboard_app.dnd_auto_turn_endpoint(
            FakeRequest({"human_actions": "not an object"}, path_params={"campaign_id": campaign["id"]})
        )
    )
    other_campaign = dashboard_app.create_dnd_campaign("Other")
    other_player = dashboard_app.create_dnd_player(other_campaign["id"], "Other Alice", "human")

    assert bad_json.status_code == 400
    assert missing_name.status_code == 400
    assert missing_campaign.status_code == 404
    assert invalid_controller.status_code == 400
    assert bad_actions.status_code == 400
    try:
        dashboard_app.create_dnd_character(campaign["id"], other_player["id"], "Wrong Campaign")
    except KeyError as exc:
        assert "Player not found" in str(exc)
    else:
        raise AssertionError("cross-campaign player ownership should be rejected")


def test_dnd_campaign_list_includes_player_count(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)
    campaign = dashboard_app.create_dnd_campaign("Counts")
    dashboard_app.create_dnd_player(campaign["id"], "Human", "human")
    dashboard_app.create_dnd_player(campaign["id"], "Agent", "subagent")

    listed = dashboard_app.list_dnd_campaigns()[0]

    assert listed["player_count"] == 2


def test_dnd_scene_endpoint_updates_current_scene(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)
    campaign = dashboard_app.create_dnd_campaign("Scene", description="The party starts in a tavern.")

    response = asyncio.run(
        dashboard_app.dnd_campaign_scene_endpoint(
            FakeRequest(
                {
                    "current_scene": {
                        "summary": "The party reaches a sealed door.",
                        "location": "Lower Hall",
                        "mood": "tense",
                        "visible_threats": ["goblin sentry"],
                        "open_questions": ["What is behind the door?"],
                    }
                },
                path_params={"campaign_id": campaign["id"]},
            )
        )
    )

    payload = _decode(response)
    loaded = dashboard_app.get_dnd_campaign(campaign["id"])

    assert response.status_code == 200
    assert payload["campaign"]["current_scene"]["summary"] == "The party reaches a sealed door."
    assert payload["campaign"]["current_scene"]["location"] == "Lower Hall"
    assert loaded["current_scene"]["visible_threats"] == ["goblin sentry"]


def test_dnd_dice_endpoint_persists_structured_roll_event(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)
    campaign = dashboard_app.create_dnd_campaign("Dice")

    response = asyncio.run(
        dashboard_app.dnd_dice_roll_endpoint(
            FakeRequest(
                {"expression": "1d20+5", "label": "Stealth check", "actor": "Aria", "seed": "fixed"},
                path_params={"campaign_id": campaign["id"]},
            )
        )
    )

    payload = _decode(response)
    events = dashboard_app.list_dnd_events(campaign["id"])

    assert response.status_code == 200
    assert payload["roll"]["expression"] == "1d20+5"
    assert payload["roll"]["label"] == "Stealth check"
    assert payload["roll"]["actor"] == "Aria"
    assert 6 <= payload["roll"]["total"] <= 25
    assert events[0]["event_type"] == "dice_roll"
    assert "1d20+5" in events[0]["body"]
    assert events[0]["actor"] == "Aria"
    assert events[0]["payload"]["total"] == payload["roll"]["total"]


def test_dnd_events_endpoint_accepts_manual_dm_event(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)
    campaign = dashboard_app.create_dnd_campaign("Manual Events")

    response = asyncio.run(
        dashboard_app.dnd_campaign_events_endpoint(
            FakeRequest(
                {"event_type": "dm_narration", "body": "The door opens.", "actor": "DM"},
                path_params={"campaign_id": campaign["id"]},
            )
        )
    )

    payload = _decode(response)
    events = dashboard_app.list_dnd_events(campaign["id"])

    assert response.status_code == 200
    assert payload["event"]["event_type"] == "dm_narration"
    assert payload["event"]["actor"] == "DM"
    assert payload["event"]["body"] == "The door opens."
    assert events[0]["body"] == "The door opens."


def test_dnd_manual_scene_update_event_updates_current_scene(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)
    campaign = dashboard_app.create_dnd_campaign("Manual Scene")

    response = asyncio.run(
        dashboard_app.dnd_campaign_events_endpoint(
            FakeRequest(
                {"event_type": "scene_update", "body": "The bridge collapses behind the party.", "actor": "DM"},
                path_params={"campaign_id": campaign["id"]},
            )
        )
    )
    payload = _decode(response)
    loaded = dashboard_app.get_dnd_campaign(campaign["id"])

    assert response.status_code == 200
    assert payload["event"]["event_type"] == "scene_update"
    assert loaded["current_scene"]["summary"] == "The bridge collapses behind the party."


def test_dnd_auto_turn_rejects_unknown_or_bad_human_actions(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)
    campaign = dashboard_app.create_dnd_campaign("Validation")
    human = dashboard_app.create_dnd_player(campaign["id"], "Alice", "human")
    subagent = dashboard_app.create_dnd_player(campaign["id"], "Scout", "subagent")

    unknown = asyncio.run(
        dashboard_app.dnd_auto_turn_endpoint(
            FakeRequest({"human_actions": {"missing": "oops"}}, path_params={"campaign_id": campaign["id"]})
        )
    )
    subagent_key = asyncio.run(
        dashboard_app.dnd_auto_turn_endpoint(
            FakeRequest({"human_actions": {subagent["id"]: "I control the bot"}}, path_params={"campaign_id": campaign["id"]})
        )
    )
    non_string = asyncio.run(
        dashboard_app.dnd_auto_turn_endpoint(
            FakeRequest({"human_actions": {human["id"]: {"bad": "object"}}}, path_params={"campaign_id": campaign["id"]})
        )
    )

    assert unknown.status_code == 400
    assert subagent_key.status_code == 400
    assert non_string.status_code == 400


def test_dnd_auto_turn_calls_subagents_concurrently_and_persists_player_action_events(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)
    campaign = dashboard_app.create_dnd_campaign("Live Agents", description="A rune-lit vault")
    scout = dashboard_app.create_dnd_player(campaign["id"], "Scout", "subagent", agent_prompt="Quiet and careful")
    bruiser = dashboard_app.create_dnd_player(campaign["id"], "Bruiser", "subagent", agent_prompt="Bold protector")
    calls = []

    async def fake_hermes_json(messages, **kwargs):
        text = json.dumps(messages)
        calls.append(text)
        if "D&D Dungeon Master" in text:
            return {"narration": "The vault answers their coordinated advance.", "mechanics": []}
        await asyncio.sleep(0.05)
        if "Scout" in text:
            return {"action": "Scout checks the left archway for tripwires.", "intent": "spot traps", "dialogue": "Hold still."}
        return {"action": "Bruiser guards the rear with shield raised.", "intent": "protect the party"}

    monkeypatch.setattr(dashboard_app, "call_dnd_hermes_json", fake_hermes_json)

    async def run_turn():
        started = dashboard_app.time.monotonic()
        response = await dashboard_app.dnd_auto_turn_endpoint(
            FakeRequest({"human_actions": {}}, path_params={"campaign_id": campaign["id"]})
        )
        return response, dashboard_app.time.monotonic() - started

    response, elapsed = asyncio.run(run_turn())
    payload = _decode(response)
    events = dashboard_app.list_dnd_events(campaign["id"])

    assert response.status_code == 200
    assert elapsed < 0.09
    assert len(calls) == 3
    assert {action["action_source"] for action in payload["actions"]} == {"hermes_subagent"}
    assert {action["player_id"] for action in payload["actions"]} == {scout["id"], bruiser["id"]}
    assert any(event["event_type"] == "player_action" and event["actor"] == "Scout" for event in events)
    assert any(event["event_type"] == "player_action" and event["payload"].get("action_source") == "hermes_subagent" for event in events)
    assert any(event["event_type"] == "dm_narration" and "vault answers" in event["body"] for event in events)


def test_dnd_auto_turn_falls_back_per_subagent_when_live_json_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)
    campaign = dashboard_app.create_dnd_campaign("Fallbacks")
    dashboard_app.create_dnd_player(campaign["id"], "Scout", "subagent")
    dashboard_app.create_dnd_player(campaign["id"], "Mage", "subagent")

    async def fake_hermes_json(messages, **kwargs):
        text = json.dumps(messages)
        if "D&D Dungeon Master" in text:
            return {"narration": "The party regroups after a shaky signal.", "mechanics": []}
        player_name = json.loads(messages[1]["content"])["player"]["name"]
        if player_name == "Scout":
            raise ValueError("bad JSON")
        return {"action": "Mage studies the glowing dust.", "intent": "identify magic"}

    monkeypatch.setattr(dashboard_app, "call_dnd_hermes_json", fake_hermes_json)

    response = asyncio.run(
        dashboard_app.dnd_auto_turn_endpoint(FakeRequest({"human_actions": {}}, path_params={"campaign_id": campaign["id"]}))
    )
    payload = _decode(response)

    assert response.status_code == 200
    assert {action["action_source"] for action in payload["actions"]} == {"hermes_subagent", "deterministic_subagent_fallback"}
    fallback = next(action for action in payload["actions"] if action["action_source"] == "deterministic_subagent_fallback")
    assert fallback["status"] == "fallback_used"
    assert fallback["error"] == "bad JSON"
    assert any(event["event_type"] == "subagent_status" and event["payload"].get("status") == "fallback_used" for event in dashboard_app.list_dnd_events(campaign["id"]))


def test_dnd_dm_json_mechanics_roll_and_scene_update_are_applied_server_side(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)
    campaign = dashboard_app.create_dnd_campaign("DM Mechanics")
    human = dashboard_app.create_dnd_player(campaign["id"], "Aria", "human")

    async def fake_hermes_json(messages, **kwargs):
        return {
            "narration": "Aria works the lock while blue runes flare.",
            "mechanics": [
                {"type": "roll", "actor": "Aria", "expression": "1d20+5", "label": "Lockpick check", "total": 999},
                {
                    "type": "scene_update",
                    "current_scene": {
                        "summary": "The vault door is half-open and humming.",
                        "location": "Lower Vault",
                        "mood": "charged",
                        "visible_threats": [],
                        "open_questions": ["What woke the vault?"],
                    },
                },
            ],
        }

    monkeypatch.setattr(dashboard_app, "call_dnd_hermes_json", fake_hermes_json)

    response = asyncio.run(
        dashboard_app.dnd_auto_turn_endpoint(
            FakeRequest({"human_actions": {human["id"]: "I pick the lock."}}, path_params={"campaign_id": campaign["id"]})
        )
    )
    payload = _decode(response)
    events = dashboard_app.list_dnd_events(campaign["id"])
    roll_event = next(event for event in events if event["event_type"] == "dice_roll")

    assert response.status_code == 200
    assert payload["campaign"]["current_scene"]["summary"] == "The vault door is half-open and humming."
    assert roll_event["payload"]["expression"] == "1d20+5"
    assert roll_event["payload"]["total"] != 999
    assert 6 <= roll_event["payload"]["total"] <= 25
    assert any(event["event_type"] == "scene_update" and event["payload"].get("location") == "Lower Vault" for event in events)


def test_dnd_auto_turn_serializes_concurrent_turns_for_one_campaign(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)
    campaign = dashboard_app.create_dnd_campaign("Race Lock")
    human = dashboard_app.create_dnd_player(campaign["id"], "Alice", "human")

    async def fake_hermes_json(messages, **kwargs):
        await asyncio.sleep(0.01)
        return {"narration": "A serialized turn resolves.", "mechanics": []}

    monkeypatch.setattr(dashboard_app, "call_dnd_hermes_json", fake_hermes_json)

    async def run_two_turns():
        first = dashboard_app.dnd_auto_turn_endpoint(
            FakeRequest({"human_actions": {human["id"]: "First action"}}, path_params={"campaign_id": campaign["id"]})
        )
        second = dashboard_app.dnd_auto_turn_endpoint(
            FakeRequest({"human_actions": {human["id"]: "Second action"}}, path_params={"campaign_id": campaign["id"]})
        )
        return await asyncio.gather(first, second)

    responses = asyncio.run(run_two_turns())
    payloads = [_decode(response) for response in responses]

    assert {response.status_code for response in responses} == {200}
    assert sorted(payload["turn"]["turn_number"] for payload in payloads) == [1, 2]
    assert dashboard_app.get_dnd_campaign(campaign["id"])["turn_number"] == 3


def test_dnd_auto_turn_job_progress_reports_live_subagent_stages(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)
    campaign = dashboard_app.create_dnd_campaign("Async Progress")
    dashboard_app.create_dnd_player(campaign["id"], "Scout", "subagent")
    release_subagent = asyncio.Event()

    async def fake_hermes_json(messages, **kwargs):
        text = json.dumps(messages)
        if "D&D Dungeon Master" in text:
            return {"narration": "The live turn resolves.", "mechanics": []}
        await release_subagent.wait()
        return {"action": "Scout studies the tunnel mouth.", "intent": "find danger"}

    monkeypatch.setattr(dashboard_app, "call_dnd_hermes_json", fake_hermes_json)

    async def exercise_job():
        start_response = await dashboard_app.dnd_auto_turn_job_start_endpoint(
            FakeRequest({"human_actions": {}}, path_params={"campaign_id": campaign["id"]})
        )
        start_payload = _decode(start_response)
        job_id = start_payload["job"]["id"]
        await asyncio.sleep(0)
        running_response = await dashboard_app.dnd_auto_turn_job_status_endpoint(
            FakeRequest(path_params={"campaign_id": campaign["id"], "job_id": job_id})
        )
        running_payload = _decode(running_response)
        release_subagent.set()
        completed_payload = None
        for _ in range(50):
            await asyncio.sleep(0.01)
            poll_response = await dashboard_app.dnd_auto_turn_job_status_endpoint(
                FakeRequest(path_params={"campaign_id": campaign["id"], "job_id": job_id})
            )
            completed_payload = _decode(poll_response)
            if completed_payload["job"]["status"] == "completed":
                break
        return start_response, start_payload, running_response, running_payload, completed_payload

    start_response, start_payload, running_response, running_payload, completed_payload = asyncio.run(exercise_job())

    assert start_response.status_code == 202
    assert running_response.status_code == 200
    assert start_payload["job"]["poll_url"] == f"/api/dnd/campaigns/{campaign['id']}/turns/auto/jobs/{start_payload['job']['id']}"
    assert running_payload["job"]["status"] in {"queued", "running"}
    assert any(event["type"] == "subagent_status" and event["status"] == "thinking" for event in running_payload["job"]["events"])
    assert completed_payload["job"]["status"] == "completed"
    assert completed_payload["job"]["progress"]["phase"] == "completed"
    assert completed_payload["job"]["progress"]["percent"] == 100
    statuses = [event.get("status") for event in completed_payload["job"]["events"] if event.get("type") == "subagent_status"]
    assert "thinking" in statuses
    assert "json_received" in statuses
    assert "validated" in statuses
    assert "committed" in statuses
    assert completed_payload["job"]["result"]["turn"]["turn_number"] == 1
    assert completed_payload["job"]["result"]["campaign"]["turn_number"] == 2


def test_dnd_auto_turn_job_start_validates_and_rejects_duplicate_active_job(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)
    campaign = dashboard_app.create_dnd_campaign("Async Validation")
    human = dashboard_app.create_dnd_player(campaign["id"], "Alice", "human")
    subagent = dashboard_app.create_dnd_player(campaign["id"], "Scout", "subagent")
    release_subagent = asyncio.Event()

    async def fake_hermes_json(messages, **kwargs):
        text = json.dumps(messages)
        if "D&D Dungeon Master" in text:
            return {"narration": "Only one live turn resolves.", "mechanics": []}
        await release_subagent.wait()
        return {"action": "Scout waits for the signal.", "intent": "avoid duplicate turns"}

    monkeypatch.setattr(dashboard_app, "call_dnd_hermes_json", fake_hermes_json)

    async def exercise_validation():
        bad_actions = await dashboard_app.dnd_auto_turn_job_start_endpoint(
            FakeRequest({"human_actions": "not an object"}, path_params={"campaign_id": campaign["id"]})
        )
        unknown_player = await dashboard_app.dnd_auto_turn_job_start_endpoint(
            FakeRequest({"human_actions": {"missing": "oops"}}, path_params={"campaign_id": campaign["id"]})
        )
        subagent_action = await dashboard_app.dnd_auto_turn_job_start_endpoint(
            FakeRequest({"human_actions": {subagent["id"]: "I control the bot."}}, path_params={"campaign_id": campaign["id"]})
        )
        non_string = await dashboard_app.dnd_auto_turn_job_start_endpoint(
            FakeRequest({"human_actions": {human["id"]: {"bad": "object"}}}, path_params={"campaign_id": campaign["id"]})
        )
        missing_campaign = await dashboard_app.dnd_auto_turn_job_start_endpoint(
            FakeRequest({"human_actions": {}}, path_params={"campaign_id": "missing"})
        )
        first = await dashboard_app.dnd_auto_turn_job_start_endpoint(
            FakeRequest({"human_actions": {human["id"]: "First action"}}, path_params={"campaign_id": campaign["id"]})
        )
        second = await dashboard_app.dnd_auto_turn_job_start_endpoint(
            FakeRequest({"human_actions": {human["id"]: "Second action"}}, path_params={"campaign_id": campaign["id"]})
        )
        release_subagent.set()
        return bad_actions, unknown_player, subagent_action, non_string, missing_campaign, first, second

    bad_actions, unknown_player, subagent_action, non_string, missing_campaign, first, second = asyncio.run(exercise_validation())
    second_payload = _decode(second)

    assert bad_actions.status_code == 400
    assert unknown_player.status_code == 400
    assert subagent_action.status_code == 400
    assert non_string.status_code == 400
    assert missing_campaign.status_code == 404
    assert first.status_code == 202
    assert second.status_code == 409
    assert second_payload["error"] == "A live turn job is already active for this campaign"
    assert second_payload["job"]["id"] == _decode(first)["job"]["id"]


def test_dnd_frontend_panel_uses_backend_contract():
    html = dashboard_source()

    assert 'data-panel="dnd"' in html
    assert 'id="dnd-panel"' in html
    assert "event.body" in html
    assert "turn_number" in html
    assert "players: dndArrayFromResponse(data, 'players')" in html
    assert "agent_prompt" in html
    assert "human_actions" in html
    assert "dnd-human-action" in html
    assert "'/api/dnd/campaigns" in html or "`/api/dnd/campaigns" in html
    assert 'id="dnd-scene-card"' in html
    assert 'id="dnd-pending-turn"' in html
    assert 'id="dnd-dice-form"' in html
    assert 'id="dnd-dice-expression"' in html
    assert 'id="dnd-dice-label"' in html
    assert 'id="dnd-dice-actor"' in html
    assert 'id="dnd-mechanics-log"' in html
    assert 'id="dnd-event-filter"' in html
    assert 'id="dnd-event-order"' in html
    assert 'id="dnd-manual-event-form"' in html
    assert 'id="dnd-event-type"' in html
    assert 'id="dnd-event-body"' in html
    assert "rollDndDice" in html
    assert "submitDndEvent" in html
    assert "dndSceneSummary" in html
    assert "dndEventClass" in html
    assert "dnd-event-dice" in html
    assert "dnd-event-narration" in html
    assert "dnd-event-scene" in html
    assert "dnd-subagent-status" in html
    assert "dnd-subagent-prompt" in html
    assert "Live autonomous subagents" in html
    assert "player_action" in html
    assert "subagent_status" in html
    assert "action_source" in html
    assert "fallback_used" in html
    paths = [getattr(route, "path", None) for route in dashboard_app.routes]
    assert "/dnd" in paths
    assert "/dnd/" in paths
    assert "/campaigns" in paths
    assert "/campaigns/" in paths
    assert "/api/dnd/campaigns/{campaign_id}/turns/auto/jobs" in paths
    assert "/api/dnd/campaigns/{campaign_id}/turns/auto/jobs/{job_id}" in paths
    assert 'id="dnd-turn-progress"' in html
    assert 'id="dnd-turn-progress-list"' in html
    assert "Live turn progress" in html
    assert "Thinking" in html
    assert "JSON received" in html
    assert "Committed" in html
    assert "dndAutoTurnJobId" in html
    assert "pollDndAutoTurnJob" in html
    assert "renderDndTurnProgress" in html
    assert "turns/auto/jobs" in html


def test_dnd_character_generation_and_world_builder_endpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)
    campaign = dashboard_app.create_dnd_campaign("Forge", description="Sky islands and dragon storms")
    player = dashboard_app.create_dnd_player(campaign["id"], "Alice", "human")
    calls = []

    async def fake_hermes_json(messages, **kwargs):
        text = json.dumps(messages)
        calls.append(text)
        if "character_creation" in text:
            return {
                "character": {
                    "name": "Kael Stormwake",
                    "kind": "pc",
                    "ancestry": "Human",
                    "class_name": "Ranger",
                    "background": "Outlander",
                    "level": 2,
                    "ability_scores": {"str": 10, "dex": 15, "con": 13, "int": 11, "wis": 14, "cha": 9},
                    "equipment": ["longbow", "explorer's pack"],
                    "backstory": "Raised under storm sails.",
                }
            }
        return {
            "world": {"theme": "sky frontier", "content_pack_id": "fantasy_core"},
            "locations": [{"name": "Cloudbreak Port", "summary": "A cliffside airship harbor."}],
            "npcs": [{"name": "Captain Vey", "summary": "Airship captain with a secret route."}],
            "factions": [{"name": "Storm Tithe", "summary": "Collectors of dragon-weather relics."}],
            "quests": [{"title": "Chart the Red Squall", "hook": "Map the storm before it eats the port."}],
            "encounters": [{"title": "Dockside Drake", "summary": "A young drake attacks mooring chains."}],
            "starting_scene": {"summary": "Red lightning crawls over Cloudbreak Port.", "location": "Cloudbreak Port", "mood": "urgent", "visible_threats": ["red squall"], "open_questions": ["Who called the storm?"]},
        }

    monkeypatch.setattr(dashboard_app, "call_dnd_hermes_json", fake_hermes_json)

    char_response = asyncio.run(
        dashboard_app.dnd_character_generate_endpoint(
            FakeRequest({"prompt": "storm scout", "player_id": player["id"], "constraints": {"level": 2}}, path_params={"campaign_id": campaign["id"]})
        )
    )
    world_response = asyncio.run(
        dashboard_app.dnd_world_generate_endpoint(
            FakeRequest({"brief": "sky islands", "parameters": {"tone": "urgent"}}, path_params={"campaign_id": campaign["id"]})
        )
    )
    entities_response = asyncio.run(
        dashboard_app.dnd_world_entities_endpoint(FakeRequest(path_params={"campaign_id": campaign["id"]}))
    )

    character = _decode(char_response)["character"]
    world_payload = _decode(world_response)
    entities = _decode(entities_response)["entities"]

    assert char_response.status_code == 200
    assert character["name"] == "Kael Stormwake"
    assert character["player_id"] == player["id"]
    assert character["character_sheet"]["schema"] == "dnd.character_creation.v1"
    assert world_response.status_code == 200
    assert world_payload["campaign"]["current_scene"]["location"] == "Cloudbreak Port"
    assert {entity["entity_type"] for entity in entities} >= {"location", "npc", "faction", "quest", "encounter"}
    assert any(event["event_type"] == "character_generated" for event in dashboard_app.list_dnd_events(campaign["id"]))
    assert any(event["event_type"] == "world_generated" for event in dashboard_app.list_dnd_events(campaign["id"]))


def test_dnd_manual_character_and_world_entity_endpoints_and_contract():
    html = dashboard_source()
    paths = [getattr(route, "path", None) for route in dashboard_app.routes]

    assert "/dnd/popout" in paths
    assert "/api/dnd/schemas" in paths
    assert "/api/dnd/campaigns/{campaign_id}/characters" in paths
    assert "/api/dnd/campaigns/{campaign_id}/characters/generate" in paths
    assert "/api/dnd/campaigns/{campaign_id}/world/entities" in paths
    assert "/api/dnd/campaigns/{campaign_id}/world/generate" in paths
    assert 'id="dnd-popout-btn"' in html
    assert "openDndPopout" in html
    assert "dnd-popout-mode" in html
    assert 'id="dnd-character-card"' in html
    assert 'id="dnd-character-ai-brief"' in html
    assert "generateDndCharacter" in html
    assert 'id="dnd-world-builder-card"' in html
    assert "generateDndWorld" in html
    assert "createDndWorldEntity" in html
    assert "dnd-dashboard-grid" in html
    assert "dnd.world_generation.v1" in html
