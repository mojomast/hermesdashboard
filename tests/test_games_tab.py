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
            def __init__(self, content=None, status_code=200, **kwargs):
                self.status_code = status_code
                self.kwargs = kwargs
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

        class StreamingResponse(_Response):
            pass

        applications.Starlette = Starlette
        routing.Route = Route
        templating.Jinja2Templates = Jinja2Templates
        responses.JSONResponse = JSONResponse
        responses.PlainTextResponse = PlainTextResponse
        responses.StreamingResponse = StreamingResponse

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
    pass


def _decode(response):
    return json.loads(response.body.decode("utf-8"))


def test_games_catalog_reads_gaming_skills_from_hermes_home(tmp_path, monkeypatch):
    skills_dir = tmp_path / "skills" / "gaming"
    pokemon = skills_dir / "pokemon-player"
    minecraft = skills_dir / "minecraft-modpack-server"
    pokemon.mkdir(parents=True)
    minecraft.mkdir(parents=True)
    (pokemon / "SKILL.md").write_text(
        "---\nname: pokemon-player\ndescription: Play Pokemon autonomously.\ntags: [gaming, pokemon, emulator]\n---\n# Pokemon\n",
        encoding="utf-8",
    )
    (minecraft / "SKILL.md").write_text(
        "---\nname: minecraft-modpack-server\ndescription: Run modded Minecraft servers.\ntags: [minecraft, gaming, server]\n---\n# Minecraft\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    catalog = dashboard_app.get_games_catalog()

    assert catalog["count"] == 2
    assert [game["id"] for game in catalog["games"]] == ["minecraft-modpack-server", "pokemon-player"]
    assert catalog["games"][0]["category"] == "Server"
    assert catalog["games"][1]["category"] == "Emulator"
    assert catalog["games"][1]["tags"] == ["gaming", "pokemon", "emulator"]


def test_games_catalog_exposes_doom_watch_metadata(tmp_path, monkeypatch):
    doom = tmp_path / "skills" / "gaming" / "doom-player"
    doom.mkdir(parents=True)
    (doom / "SKILL.md").write_text(
        "---\n"
        "name: doom-player\n"
        "description: Watch Hermes play Doom via ViZDoom.\n"
        "tags: [gaming, doom, vizdoom, fps, watch]\n"
        "dashboard:\n"
        "  watch_url: /doom/\n"
        "  launch_label: Watch Hermes play Doom\n"
        "  status_hint: Start the Doom watch server first.\n"
        "---\n"
        "# Doom Player\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    catalog = dashboard_app.get_games_catalog()

    assert catalog["count"] == 1
    game = catalog["games"][0]
    assert game["id"] == "doom-player"
    assert game["category"] == "Watch"
    assert game["watch_url"] == "/doom/"
    assert game["launch_label"] == "Watch Hermes play Doom"
    assert game["status_hint"] == "Start the Doom watch server first."


def test_games_catalog_exposes_minihack_watch_metadata(tmp_path, monkeypatch):
    minihack = tmp_path / "skills" / "gaming" / "minihack-player"
    minihack.mkdir(parents=True)
    (minihack / "SKILL.md").write_text(
        "---\n"
        "name: minihack-player\n"
        "description: Watch Hermes crawl MiniHack dungeons.\n"
        "tags: [gaming, minihack, nethack, roguelike, watch, benchmark]\n"
        "dashboard:\n"
        "  watch_url: /minihack/\n"
        "  launch_label: Watch Hermes Crawl Dungeons\n"
        "  status_hint: Start the MiniHack watch server first.\n"
        "---\n"
        "# MiniHack Player\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    catalog = dashboard_app.get_games_catalog()

    assert catalog["count"] == 1
    game = catalog["games"][0]
    assert game["id"] == "minihack-player"
    assert game["category"] == "Watch"
    assert game["watch_url"] == "/minihack/"
    assert game["launch_label"] == "Watch Hermes Crawl Dungeons"
    assert game["status_hint"] == "Start the MiniHack watch server first."


def test_games_catalog_exposes_pokemon_dashboard_metadata(tmp_path, monkeypatch):
    pokemon = tmp_path / "skills" / "gaming" / "pokemon-player"
    pokemon.mkdir(parents=True)
    (pokemon / "SKILL.md").write_text(
        "---\n"
        "name: pokemon-player\n"
        "description: Play Pokemon games autonomously via local emulator dashboard.\n"
        "tags: [gaming, pokemon, emulator, pyboy, gameboy]\n"
        "dashboard:\n"
        "  upload_url: /pokemon/dashboard/onboarding.html\n"
        "  upload_label: Upload / Choose ROM\n"
        "  watch_url: /pokemon/dashboard/watch.html\n"
        "  launch_label: Watch Hermes Play Pokémon\n"
        "  control_url: /pokemon/dashboard/\n"
        "  control_label: Control Pokémon\n"
        "  status_hint: Start pokemon-agent on 127.0.0.1:9876 first.\n"
        "---\n"
        "# Pokemon Player\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    catalog = dashboard_app.get_games_catalog()

    assert catalog["count"] == 1
    game = catalog["games"][0]
    assert game["id"] == "pokemon-player"
    assert game["category"] == "Emulator"
    assert game["upload_url"] == "/pokemon/dashboard/onboarding.html"
    assert game["upload_label"] == "Upload / Choose ROM"
    assert game["watch_url"] == "/pokemon/dashboard/watch.html"
    assert game["launch_label"] == "Watch Hermes Play Pokémon"
    assert game["control_url"] == "/pokemon/dashboard/"
    assert game["control_label"] == "Control Pokémon"
    assert game["status_hint"] == "Start pokemon-agent on 127.0.0.1:9876 first."


def test_games_api_route_returns_catalog(tmp_path, monkeypatch):
    import asyncio

    game_dir = tmp_path / "skills" / "gaming" / "chess-coach"
    game_dir.mkdir(parents=True)
    (game_dir / "SKILL.md").write_text(
        "---\nname: chess-coach\ndescription: Analyze games.\ntags: [gaming, chess]\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    response = asyncio.run(dashboard_app.get_games_endpoint(FakeRequest()))
    payload = _decode(response)

    assert response.status_code == 200
    assert payload["count"] == 1
    assert payload["games"][0]["id"] == "chess-coach"
    route_paths = [
        getattr(route, "path", getattr(route, "path_format", None))
        or (route.args[0] if getattr(route, "args", None) else None)
        for route in dashboard_app.routes
    ]
    assert "/api/games" in route_paths
    assert "/doom/" in route_paths
    assert "/doom/{path:path}" in route_paths
    assert "/minihack/" in route_paths
    assert "/minihack/{path:path}" in route_paths
    assert "/pokemon/" in route_paths
    assert "/pokemon/{path:path}" in route_paths
    assert "/api/diagnostics/context" in route_paths
    assert "/api/pokemon/restart" in route_paths
    assert "/pokemon/chat" in route_paths
    assert "/pokemon/api/diagnostics/context" in route_paths


def test_diagnostics_redacts_secret_like_keys():
    payload = dashboard_app._diagnostics_redact(
        {
            "api_key": "abc123",
            "nested": {"Authorization": "Bearer nope", "safe": "ok"},
            "items": [{"password": "hidden", "value": "visible"}],
        }
    )

    assert payload["api_key"] == "[redacted]"
    assert payload["nested"]["Authorization"] == "[redacted]"
    assert payload["nested"]["safe"] == "ok"
    assert payload["items"][0]["password"] == "[redacted]"
    assert payload["items"][0]["value"] == "visible"


def test_doom_watch_html_rewrite_scopes_absolute_assets_to_proxy():
    html = """
    <img src="/stream.mjpg">
    <script>fetch('/status.json',{cache:'no-store'});</script>
    <span><code>/status.json</code> · <code>/stream.mjpg</code></span>
    """

    rewritten = dashboard_app._rewrite_doom_watch_html(html)

    assert 'src="/doom/stream.mjpg"' in rewritten
    assert "fetch('/doom/status.json'" in rewritten
    assert "<code>/doom/status.json</code> · <code>/doom/stream.mjpg</code>" in rewritten
    assert 'src="/stream.mjpg"' not in rewritten
    assert "fetch('/status.json'" not in rewritten


def test_pokemon_dashboard_js_rewrite_scopes_api_and_ws_to_proxy():
    js = """
    function getBaseURL() {
        return window.location.protocol + '//' + window.location.host;
    }

    function getWSURL() {
        var proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return proto + '//' + window.location.host + '/ws';
    }
    """

    rewritten = dashboard_app._rewrite_pokemon_dashboard_js(js)

    assert "return window.location.protocol + '//' + window.location.host + '/pokemon';" in rewritten
    assert "return proto + '//' + window.location.host + '/pokemon/ws';" in rewritten
    assert "return window.location.protocol + '//' + window.location.host;" not in rewritten
    assert "return proto + '//' + window.location.host + '/ws';" not in rewritten


def test_pokemon_upstream_path_maps_proxy_root_to_dashboard():
    assert dashboard_app._pokemon_upstream_path("") == "/dashboard/"
    assert dashboard_app._pokemon_upstream_path("dashboard") == "/dashboard/"
    assert dashboard_app._pokemon_upstream_path("dashboard/app.js") == "/dashboard/app.js"
    assert dashboard_app._pokemon_upstream_path("health") == "/health"
    assert dashboard_app._pokemon_upstream_path("screenshot/base64") == "/screenshot/base64"


def test_games_tab_is_wired_into_dashboard_template():
    html = dashboard_source()

    assert 'data-panel="games"' in html
    assert 'id="games-panel"' in html
    assert 'id="games-watch-frame"' in html
    assert "upload_url" in html
    assert "openGameWatch" in html
    assert "restartPokemonAgent()" in html
    assert "/api/pokemon/restart" in html
    assert "loadGames()" in html
    assert "'games'" in html
