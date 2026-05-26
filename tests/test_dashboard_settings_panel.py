from pathlib import Path


TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "index.html"


def _html() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_dashboard_settings_button_and_menu_are_rendered():
    html = _html()

    assert 'id="dashboard-settings-button"' in html
    assert 'toggleDashboardSettings(event)' in html
    assert 'id="dashboard-settings-menu"' in html
    assert 'Reload Dashboard' in html
    assert 'hardRefreshDashboard()' in html


def test_dashboard_tab_visibility_settings_are_persistent_and_safe():
    html = _html()

    assert "DASHBOARD_TAB_SETTINGS_KEY = 'hermes_dashboard_hidden_tabs_v1'" in html
    assert "function getHiddenDashboardTabs()" in html
    assert "function setDashboardTabVisible(panel, visible)" in html
    assert "localStorage.setItem(DASHBOARD_TAB_SETTINGS_KEY" in html
    assert "panel === 'chat'" in html
    assert "dashboard-tab-hidden" in html


def test_hidden_tabs_are_respected_by_hash_routing():
    html = _html()

    assert "!isDashboardTabVisible(panel)" in html
    assert "navigateTo('chat')" in html
    assert "const validPanels = ['chat','message-board'" in html
    assert "applyDashboardTabSettings();" in html
    assert "renderDashboardTabSettings();" in html


def test_scrollprize_tab_is_available_in_dashboard_settings_registry():
    html = _html()

    assert "{ id: 'scrolls', label: 'Vesuvius AutoResearch' }" in html
    assert 'data-panel="scrolls"' in html
