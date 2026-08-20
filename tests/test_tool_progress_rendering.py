import json
import re
import subprocess

from tests.dashboard_sources import DASHBOARD_JS, dashboard_source


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


def test_in_flight_subagent_rail_indicator_reuses_live_windows_and_stop_controls():
    html = dashboard_source()
    css = DASHBOARD_JS.parent.parent.joinpath("css", "dashboard.css").read_text(encoding="utf-8")

    assert "function getInFlightSubagents()" in html
    assert "function renderSubagentFlightRailItem()" in html
    assert "function renderSubagentFlightPopover(" in html
    assert "function watchSubagentFlightStatus(" in html
    assert "restoreActiveRunChildSessions();" in html
    assert "rememberRunChildSession(runState, childEntry, 'LIVE')" in html
    assert "updateDrawerBadge(childSessionId, 'STOPPING')" in html
    assert "previousStatus === 'STOPPING'" in html
    assert "restoredChildFlightSessions.has(childSessionId)" in html
    assert "childFlightEventSources.delete(childSessionId)" in html
    assert 'class="btn live-view-btn"' in html
    assert 'class="btn emergency-stop-btn subagent-stop-btn"' in html
    assert "openChildSessionDrawer(childSessionId, anchorEl, label)" in html
    assert "requestStopSubagent(stopBtn.dataset.childSessionId" in html
    assert ".subagent-flight-toggle" in css
    assert "subagent-flight-hover" in css
    assert ".subagent-flight-popover" in css


def test_child_sessions_nest_below_room_tabs_in_the_left_rail():
    html = dashboard_source()
    css = DASHBOARD_JS.parent.parent.joinpath("css", "dashboard.css").read_text(encoding="utf-8")

    rail = html.split("function renderChatRoomRail()", 1)[1].split("function updateChatRoomChrome()", 1)[0]
    assert "renderRoomChildSessionEntries('main')" in rail
    assert "renderRoomChildSessionEntries('shared')" in rail
    assert "renderRoomChildSessionEntries(roomId)" in rail
    assert "chat-room-group" in rail
    assert "function renderRoomChildSessionEntries(roomId)" in html
    assert "Array.isArray(run?.childSessions)" in html
    assert ".chat-room-children" in css
    assert ".chat-room-child-open" in css
    assert ".chat-room-child-dot" in css
    assert "chat-room-child-stop subagent-stop-btn" in html
    assert "live-view-btn" in html.split("function renderRoomChildSessionEntries(roomId)", 1)[1]


def test_delegate_live_actions_are_not_nested_inside_the_tool_toggle_button():
    html = dashboard_source()

    pill = html[html.index('<button type="button" class="tool-call-pill"'):]
    pill = pill[:pill.index('</button>')]
    assert "${drawerBtn}" not in pill
    assert "${drawerBtn}" in html


def test_subagent_windows_use_a_stable_body_level_layer_not_tool_markup():
    html = dashboard_source()

    assert "id = 'subagent-window-layer'" in html
    assert "document.body.appendChild(layer)" in html
    assert "function ensureSubagentWindowLayer" in html
    assert "anchorEl.closest('details, .tool-call-block, .tool-section')" not in html
    assert "host.insertAdjacentHTML('beforeend'" not in html


def test_transcript_condensation_pipeline_is_wired_to_chat_session_and_floating_views():
    html = dashboard_source()
    conversation_renderer = html.split("function renderConversation()", 1)[1].split("function makeExecutionNodeId", 1)[0]
    session_renderer = html.split("function renderSessionTranscript(traceContext)", 1)[1].split("async function hydrateChatFromSession", 1)[0]

    assert "renderTranscriptSegments(buildTranscriptRenderSegments(rows)" in conversation_renderer
    assert session_renderer.count("renderTranscriptSegments(buildTranscriptRenderSegments(rows)") == 2
    assert "function buildTranscriptRenderSegments" in html
    assert "function renderTranscriptExecutionEntries" in html


def test_subagent_windows_use_dedicated_nearly_opaque_dark_and_light_surfaces():
    css = DASHBOARD_JS.parent.parent.joinpath("css", "dashboard.css").read_text(encoding="utf-8")
    assert "--subagent-window-surface: rgba(15, 15, 35, 0.96)" in css
    assert "--subagent-window-surface: rgba(255, 255, 255, 0.98)" in css
    rule = re.search(r"\.child-session-drawer\.subagent-window\s*\{([^}]*)\}", css, re.S)
    assert rule and "background: var(--subagent-window-surface)" in rule.group(1)
    assert "background: var(--bg-card" not in rule.group(1)


def test_subagent_window_manager_supports_independent_focus_drag_resize_and_minimize():
    html = dashboard_source()

    assert "const childWindowState = new Map()" in html
    assert "function bringSubagentWindowToFront" in html
    assert "function clampSubagentWindowToViewport" in html
    assert "data-minimize-child-session" in html
    assert "data-subagent-resize-handle" in html
    assert "pointerdown" in html
    assert "setPointerCapture" in html
    assert "subagent-window-minimized" in html


def test_delegate_bubble_only_renders_compact_child_status_and_open_controls():
    html = dashboard_source()
    renderer = html.split("function renderDelegateChildStreams(tool)", 1)[1]
    renderer = renderer.split("const liveChildSessionMap", 1)[0]

    assert "subagent-monitor-row" in renderer
    assert "live-view-btn" in renderer
    assert "renderToolCallList" not in renderer
    assert "delegate-task-raw" not in renderer
    assert "assistant-tools" not in renderer


def test_cached_drawer_replay_renders_without_recording_events_again():
    html = dashboard_source()
    replay = html.split("function renderCachedDrawerEvents", 1)[1]
    replay = replay.split("function appendLiveDrawerEventIfOpen", 1)[0]

    assert "renderDrawerLiveTrace" in replay
    assert "appendDrawerEventRow" not in replay


def test_subagent_live_trace_reuses_main_chat_tool_renderer_and_preserves_content():
    html = dashboard_source()
    live_trace = html.split("function buildDrawerLiveTraceState", 1)[1]
    live_trace = live_trace.split("function ensureDrawerLiveTail", 1)[0]

    assert "createAssistantTraceState" in live_trace
    assert "reduceAssistantTraceEvent" in live_trace
    assert "renderAssistantEvents" in live_trace
    assert "renderAssistantMessageShell" in live_trace
    assert "syncToolCallUi" in live_trace
    assert "parsed.content" in html


def test_drawer_event_dedup_prefers_ids_and_only_briefly_suppresses_signatures():
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    start = source.index("const childDrawerDedupState")
    end = source.index("function renderDrawerEventRow", start)
    helpers = source[start:end]
    script = f"""
const childDrawerEventCache = new Map();
function getEventMetadata(value) {{ return value.arguments || {{}}; }}
{helpers}
const first = {{type: 'tool_progress', progress: 'same', event_id: 'event-7'}};
const fallback = {{type: 'tool_progress', progress: 'same'}};
for (let i = 0; i < 550; i += 1) shouldAcceptDrawerEvent('bounded', {{event_id: `id-${{i}}`}}, i);
const result = {{
  explicitFirst: shouldAcceptDrawerEvent('child', first, 1000),
  explicitDuplicate: shouldAcceptDrawerEvent('child', {{...first}}, 9000),
  fallbackFirst: shouldAcceptDrawerEvent('other', fallback, 1000),
  fallbackDuplicate: shouldAcceptDrawerEvent('other', {{progress: 'same', type: 'tool_progress'}}, 1100),
  fallbackLater: shouldAcceptDrawerEvent('other', {{...fallback}}, 2601),
  boundedSize: childDrawerDedupState.get('bounded').size,
}};
console.log(JSON.stringify(result));
"""
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    values = json.loads(result.stdout)
    assert values == {
        "explicitFirst": True,
        "explicitDuplicate": False,
        "fallbackFirst": True,
        "fallbackDuplicate": False,
        "fallbackLater": True,
        "boundedSize": 500,
    }


def test_mobile_subagent_windows_cycle_visible_slots_reset_closed_state_and_support_resize():
    html = dashboard_source()

    assert "childMobileWindowSequence % getMobileWindowSlotCount()" in html
    assert "const MOBILE_WINDOW_MAX_SLOTS = 6" in html
    assert "state.mobileIndex %= getMobileWindowSlotCount(viewportHeight)" in html
    assert "childWindowState.delete(childSessionId)" in html
    assert "refreshMobileWindowSlots()" in html
    assert "--mobile-window-index" in html
    assert "top: calc(8px + (var(--mobile-window-index, 0) * 42px))" in html
    assert 'role="button" tabindex="0" aria-label="Resize subagent window; use arrow keys"' in html
    assert "resizeHandle?.addEventListener('keydown'" in html


def test_subagent_event_source_retains_native_reconnect_and_restores_live_status():
    html = dashboard_source()
    handler = html.split("function openDrawerEventSource", 1)[1]
    handler = handler.split("function renderDelegateLiveActionStrip", 1)[0]

    assert "es.onopen = () => updateDrawerBadge(childSessionId, 'LIVE')" in handler
    assert "updateDrawerBadge(childSessionId, 'LIVE');" in handler
    assert "'RECONNECTING'" in handler
    assert "'OFFLINE'" in handler
    error_handler = handler.split("es.onerror =", 1)[1]
    assert "es.close()" not in error_handler
    assert "drawerEventSources.delete" not in error_handler


def test_subagent_event_source_propagates_stable_sse_occurrence_id():
    html = dashboard_source()
    handler = html.split("function openDrawerEventSource", 1)[1]
    handler = handler.split("function renderDelegateLiveActionStrip", 1)[0]

    assert "event.lastEventId" in handler
    assert "parsed.event_id = event.lastEventId" in handler


def test_mobile_slot_cycle_and_explicit_close_lifecycle_run_in_javascript():
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    state_start = source.index("const childWindowState")
    state_end = source.index("function clampSubagentWindowToViewport", state_start)
    state_helpers = source[state_start:state_end]
    close_start = source.index("function closeChildSessionDrawer")
    close_end = source.index("function updateDrawerBadge", close_start)
    close_helper = source[close_start:close_end]
    script = f"""
globalThis.window = {{ innerHeight: 240 }};
globalThis.document = {{
  documentElement: {{ clientHeight: 240 }},
  querySelectorAll: () => [],
}};
globalThis.CSS = {{ escape: value => String(value) }};
const drawerEventSources = new Map();
const openDrawerSet = new Set();
{state_helpers}
const indices = Array.from({{length: 12}}, (_, index) => getSubagentWindowState(`child-${{index}}`).mobileIndex);
let closed = false;
drawerEventSources.set('child-0', {{ close: () => {{ closed = true; }} }});
openDrawerSet.add('child-0');
{close_helper}
closeChildSessionDrawer('child-0');
console.log(JSON.stringify({{
  slotCount: getMobileWindowSlotCount(),
  indices,
  bounded: indices.every(index => index >= 0 && index < getMobileWindowSlotCount()),
  sourceClosed: closed,
  sourceRemoved: !drawerEventSources.has('child-0'),
  openRemoved: !openDrawerSet.has('child-0'),
  stateRemoved: !childWindowState.has('child-0'),
}}));
"""
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    values = json.loads(result.stdout)

    assert values == {
        "slotCount": 5,
        "indices": [0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1],
        "bounded": True,
        "sourceClosed": True,
        "sourceRemoved": True,
        "openRemoved": True,
        "stateRemoved": True,
    }
