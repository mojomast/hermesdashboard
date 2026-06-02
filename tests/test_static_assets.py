import app as dashboard_app
from tests.dashboard_sources import DASHBOARD_CSS, DASHBOARD_JS, dashboard_template


def test_dashboard_template_links_extracted_static_assets():
    html = dashboard_template()

    assert '<link rel="stylesheet" href="/static/css/dashboard.css' in html
    assert '<script src="/static/js/dashboard.js' in html
    assert 'drawer-dock-20260602' in html
    assert '<style>' not in html
    assert 'type="module"' not in html
    assert '{% include' not in html


def test_rendered_dashboard_keeps_key_panel_and_route_contracts():
    html = dashboard_template()

    expected_panel_ids = [
        "chat-panel",
        "message-board-panel",
        "config-panel",
        "secrets-panel",
        "sessions-panel",
        "agent-observability-panel",
        "memory-panel",
        "skills-panel",
        "games-panel",
        "diagnostics-panel",
        "dnd-panel",
        "self-improvement-panel",
        "autonomous-development-panel",
        "scrolls-panel",
        "cron-panel",
        "schedule-panel",
        "graph-panel",
    ]
    for panel_id in expected_panel_ids:
        assert f'id="{panel_id}"' in html

    expected_panels = [
        "chat",
        "message-board",
        "config",
        "secrets",
        "sessions",
        "agent-observability",
        "memory",
        "skills",
        "games",
        "diagnostics",
        "dnd",
        "self-improvement",
        "autonomous-development",
        "scrolls",
        "cron",
        "schedule",
        "graph",
    ]
    for panel in expected_panels:
        assert f'data-panel="{panel}"' in html


def test_extracted_assets_exist_and_keep_expected_contracts():
    css = DASHBOARD_CSS.read_text(encoding="utf-8")
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert '* { margin: 0; padding: 0; box-sizing: border-box; }' in css
    assert 'function initTheme()' in js
    assert 'function toggleTheme()' in js
    assert 'export default' not in js
    assert 'export {' not in js


def test_chat_image_paste_contract_is_preserved_across_template_and_assets():
    html = dashboard_template()
    css = DASHBOARD_CSS.read_text(encoding="utf-8")
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert 'id="chat-attachment-preview-bar"' in html
    assert 'id="chat-image-input"' in html
    assert 'id="chat-image-btn"' in html
    assert 'accept="image/*"' in html
    assert '.chat-attachment-preview-bar' in css
    assert '.chat-attachment-preview' in css
    assert '.chat-message-image-wrap' in css
    assert 'function renderUserMessageContent' in js
    assert 'function handleUserInputPaste' in js
    assert 'async function attachImageFiles' in js
    assert 'FileReader' in js
    assert 'pendingImageAttachments' in js
    assert "type: 'image_url'" in js
    assert "userInput.addEventListener('paste', handleUserInputPaste)" in js


def test_live_subagent_drawers_use_persistent_side_by_side_dock():
    css = DASHBOARD_CSS.read_text(encoding="utf-8")
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert "function ensureChildSessionDrawerDock()" in js
    assert "function renderOpenChildSessionDrawers()" in js
    assert "child-session-drawer-dock" in js
    assert "host.insertAdjacentHTML" not in js
    assert "renderOpenChildSessionDrawers();" in js
    assert "appendDrawerEventRow(childSessionId, transcriptEl, event, { cache: false })" in js
    assert ".child-session-drawer-dock" in css
    assert "position: fixed" in css
    assert "display: flex" in css
    assert "flex: 0 0 min(440px" in css


def test_static_route_is_registered_with_extracted_asset_directory():
    static_routes = [route for route in dashboard_app.routes if getattr(route, "path", None) == "/static"]
    assert len(static_routes) == 1

    static_app = getattr(static_routes[0], "app", None)
    directory = getattr(static_app, "directory", None)
    if directory is None:
        directory = getattr(static_app, "kwargs", {}).get("directory")

    assert str(directory).endswith("static")
