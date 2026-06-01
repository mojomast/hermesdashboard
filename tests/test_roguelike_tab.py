from pathlib import Path

from tests.dashboard_sources import dashboard_source, raw_dashboard_template

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_roguelike_tab_is_registered_with_hash_router_settings_and_breadcrumbs():
    source = dashboard_source()
    shell = raw_dashboard_template()

    assert '{% include "dashboard/partials/panels/roguelike.html" %}' in shell
    assert 'data-panel="roguelike"' in source
    assert source.count('data-panel="roguelike"') >= 2
    assert "onclick=\"navigateTo('roguelike')\"" in source
    assert 'id="roguelike-panel"' in source
    assert "{ id: 'roguelike', label: 'Roguelike'" in source
    assert "'roguelike'" in source.split("const validPanels =", 1)[1].split(";", 1)[0]
    assert "case 'roguelike': initRoguelike(); break;" in source
    assert "roguelike:'Roguelike'" in source or "'roguelike':'Roguelike'" in source


def test_hermes_labyrinth_shell_and_frontend_contract_are_present():
    source = dashboard_source()

    assert 'id="hermes-rogue"' in source
    assert 'Hermes Labyrinth' in source
    assert 'id="rogue-map"' in source
    assert 'role="grid"' in source
    assert 'tabindex="0"' in source
    assert 'id="rogue-log"' in source
    assert 'id="rogue-live-status"' in source
    assert 'aria-live="polite"' in source
    assert 'data-rogue-move="0,-1"' in source
    assert 'id="rogue-new-run"' in source
    assert 'id="rogue-seeded-run"' in source
    assert 'id="rogue-copy-summary"' in source


def test_hermes_labyrinth_js_is_seeded_playable_and_self_contained():
    source = dashboard_source()
    app_source = APP.read_text(encoding="utf-8")

    assert "const HermesRogue = (() =>" in source
    assert "window.HermesRogue = HermesRogue" in source
    assert "function stringSeed" in source
    assert "if (/^\\d+$/.test(value)) return Number(value) >>> 0;" in source
    assert "function mulberry32" in source
    assert "function generateFloor" in source
    assert "function enemyTurn" in source
    assert "function checkWinLoss" in source
    assert "function handleKeydown" in source
    assert "function copySummary" in source
    assert "hermesRogue." in source
    assert "/api/roguelike" not in source
    assert "/api/hermes-rogue" not in source
    assert 'Route("/api/roguelike"' not in app_source
    assert 'Route("/api/hermes-rogue"' not in app_source
