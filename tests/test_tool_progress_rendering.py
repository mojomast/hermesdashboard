from tests.dashboard_sources import dashboard_source


def test_unmatched_tool_progress_is_retained_for_later_promotion_but_not_rendered_as_card():
    html = dashboard_source()

    assert "reason: event.reason || 'unmatched_tool_progress'" in html
    assert "function findPromotableProgressDiagnosticNode" in html
    assert "promotableProgressDiagnostic" in html
    assert "if (node?.payload?.reason === 'unmatched_tool_progress') return '';" in html


def test_parallel_tool_batch_status_is_aggregated_not_hard_coded_running():
    html = dashboard_source()

    assert "function getParallelToolBatchStatusClass" in html
    assert "const batchStatusClass = getParallelToolBatchStatusClass(tools);" in html
    assert "tool-call-status-dot ${escapeHtml(batchStatusClass)}" in html
    assert "<span class=\"tool-call-status-dot running\"></span>" not in html


def test_delegate_task_live_header_does_not_cap_child_sessions_at_three():
    html = dashboard_source()

    assert "function renderDelegateLiveActionStrip" in html
    assert "childEntries.map((entry, childIdx)" in html
    assert "childEntries.slice(0, 3)" not in html
    assert "delegate-live-actions" in html
    assert "live subagent" in html
