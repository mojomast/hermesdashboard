from tests.dashboard_sources import dashboard_source


def test_browser_notification_settings_and_permission_flow_are_rendered():
    source = dashboard_source()

    assert 'id="dashboard-notification-toggle"' in source
    assert 'toggleDashboardNotifications()' in source
    assert 'id="dashboard-notification-approvals"' in source
    assert 'id="dashboard-notification-runs"' in source
    assert 'id="dashboard-notification-subagents"' in source
    assert 'id="dashboard-notification-errors"' in source
    assert 'id="dashboard-notification-visible"' in source
    assert "Notification.requestPermission()" in source
    assert "DASHBOARD_NOTIFICATION_SETTINGS_KEY" in source
    assert "renderDashboardNotificationSettings();" in source


def test_browser_notifications_cover_approval_and_attention_events():
    source = dashboard_source()

    assert "function sendDashboardNotification(kind, title, body, options = {})" in source
    assert "new Notification(title" in source
    assert "Hermes approval required" in source
    assert "Hermes finished" in source
    assert "Hermes run needs attention" in source
    assert "Hermes subagent finished" in source
    assert "Hermes subagent failed" in source
    assert "dashboardNotificationKeys.has(key)" in source
    assert "document.visibilityState === 'visible' && !options.force" in source
    assert "notification.onclick" in source
