from pathlib import Path


DASHBOARD_HTML = Path(__file__).resolve().parents[1] / "templates" / "index.html"


def test_unmatched_tool_progress_is_retained_for_later_promotion_but_not_rendered_as_card():
    html = DASHBOARD_HTML.read_text(encoding="utf-8")

    assert "reason: event.reason || 'unmatched_tool_progress'" in html
    assert "function findPromotableProgressDiagnosticNode" in html
    assert "promotableProgressDiagnostic" in html
    assert "if (node?.payload?.reason === 'unmatched_tool_progress') return '';" in html


def test_parallel_tool_batch_status_is_aggregated_not_hard_coded_running():
    html = DASHBOARD_HTML.read_text(encoding="utf-8")

    assert "function getParallelToolBatchStatusClass" in html
    assert "const batchStatusClass = getParallelToolBatchStatusClass(tools);" in html
    assert "tool-call-status-dot ${escapeHtml(batchStatusClass)}" in html
    assert "<span class=\"tool-call-status-dot running\"></span>" not in html
