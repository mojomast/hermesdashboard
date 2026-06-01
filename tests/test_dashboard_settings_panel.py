from tests.dashboard_sources import dashboard_source


def _html() -> str:
    return dashboard_source()


def test_dashboard_settings_button_and_menu_are_rendered():
    html = _html()

    assert 'id="dashboard-settings-button"' in html
    assert 'toggleDashboardSettings(event)' in html
    assert 'id="dashboard-settings-menu"' in html
    assert 'Reload Dashboard' in html
    assert 'hardRefreshDashboard()' in html
    assert 'Update Instructions' in html
    assert 'openUpdateInstructions()' in html
    assert 'Auto Update' in html
    assert 'startDashboardAutoUpdate()' in html


def test_dashboard_update_instructions_cover_non_cli_paths():
    html = _html()

    assert 'id="update-instructions-modal"' in html
    assert 'GitHub Desktop or another Git GUI' in html
    assert 'Download ZIP from GitHub' in html
    assert 'https://github.com/mojomast/hermesdashboard' in html
    assert 'id="dashboard-update-command"' in html
    assert 'git pull --ff-only' in html
    assert 'id="dashboard-auto-update-button"' in html
    assert 'id="dashboard-auto-update-status"' in html
    assert "fetch('/api/dashboard/update'" in html
    assert 'function startDashboardAutoUpdate()' in html
    assert 'function summarizeDashboardUpdateResult(data)' in html
    assert 'function copyDashboardUpdateCommand()' in html


def test_dashboard_tab_visibility_settings_are_persistent_and_safe():
    html = _html()

    assert "DASHBOARD_TAB_SETTINGS_KEY = 'hermes_dashboard_hidden_tabs_v1'" in html
    assert "DEFAULT_VISIBLE_DASHBOARD_TABS" in html
    assert "function getDefaultHiddenDashboardTabs()" in html
    assert "function getHiddenDashboardTabs()" in html
    assert "raw === null" in html
    assert "function setDashboardTabVisible(panel, visible)" in html
    assert "localStorage.setItem(DASHBOARD_TAB_SETTINGS_KEY" in html
    assert "panel === 'chat'" in html
    assert "dashboard-tab-hidden" in html
    assert "Experimental" in html
    assert "local tooling" in html
    assert "showAllDashboardTabs()" in html


def test_hidden_tabs_are_respected_by_hash_routing():
    html = _html()

    assert "!isDashboardTabVisible(panel)" in html
    assert "navigateTo('chat')" in html
    assert "const validPanels = ['chat','message-board'" in html
    assert "applyDashboardTabSettings();" in html
    assert "renderDashboardTabSettings();" in html


def test_scrollprize_tab_is_available_in_dashboard_settings_registry():
    html = _html()

    assert "id: 'scrolls', label: 'Vesuvius AutoResearch', experimental: true" in html
    assert 'data-panel="scrolls"' in html
