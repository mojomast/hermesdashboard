import asyncio
import datetime
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


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
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        class Jinja2Templates:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

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


from tests.dashboard_sources import DASHBOARD_JS


def _extract_dashboard_js_helpers() -> str:
    index_js = DASHBOARD_JS.read_text(encoding="utf-8")
    start = index_js.index("function makeExecutionNodeId")
    end = index_js.index("function parseToolPayload")
    middle_end = index_js.index("function getDelegateChildBucket")
    script_parts = [
        "function log() {}\n",
        "globalThis.escapeHtml = function(value) { return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\\\"/g, '&quot;').replace(/'/g, '&#039;'); };\n",
        "globalThis.highlightJSON = function(value) { return escapeHtml(value); };\n",
        "globalThis.formatMessageContent = function(value) { return escapeHtml(value); };\n",
        "const toolCallCompletionTimes = new Map(); function getToolElapsed() { return ''; }\n",
        index_js[start:end],
        index_js[end:middle_end],
    ]
    return "\n".join(script_parts)


_DASHBOARD_JS_HELPERS = _extract_dashboard_js_helpers()


def _run_dashboard_trace_js(expression: str):
    script = (
        _DASHBOARD_JS_HELPERS
        + "\n"
        + "const __result = (() => {\n"
        + expression
        + "\n})();\n"
        + "process.stdout.write(JSON.stringify(__result));\n"
    )
    env = os.environ.copy()
    with tempfile.NamedTemporaryFile("w", suffix=".cjs", delete=False) as script_file:
        script_file.write(script)
        script_path = script_file.name
    try:
        result = subprocess.run(
            ["node", script_path],
            cwd=Path(__file__).resolve().parent.parent,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
    finally:
        Path(script_path).unlink(missing_ok=True)
    return json.loads(result.stdout)


def _create_state_db(root: Path) -> Path:
    db_path = root / "state.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            summary TEXT,
            source TEXT,
            model TEXT,
            started_at TEXT,
            ended_at TEXT,
            parent_session_id TEXT,
            message_count INTEGER,
            tool_call_count INTEGER,
            input_tokens INTEGER,
            output_tokens INTEGER,
            estimated_cost_usd REAL,
            cache_read_tokens INTEGER,
            cache_write_tokens INTEGER,
            reasoning_tokens INTEGER,
            actual_cost_usd REAL,
            cost_status TEXT,
            cost_source TEXT,
            end_reason TEXT,
            model_config TEXT,
            system_prompt TEXT,
            billing_provider TEXT,
            billing_base_url TEXT,
            billing_mode TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TEXT,
            tool_call_id TEXT,
            tool_calls TEXT,
            tool_name TEXT,
            token_count INTEGER,
            finish_reason TEXT,
            reasoning TEXT,
            reasoning_details TEXT,
            codex_reasoning_items TEXT
        )
        """
    )

    conn.execute(
        """
        INSERT INTO sessions (
            id, title, summary, source, model, started_at, ended_at, parent_session_id,
            message_count, tool_call_count, input_tokens, output_tokens, estimated_cost_usd,
            cache_read_tokens, cache_write_tokens, reasoning_tokens, actual_cost_usd,
            cost_status, cost_source, end_reason, model_config, system_prompt,
            billing_provider, billing_base_url, billing_mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "parent-session",
            "Parent Session",
            "Parent summary",
            "cli",
            "test-model",
            "2026-04-13T15:53:37",
            "2026-04-13T15:54:37",
            None,
            4,
            2,
            10,
            5,
            0.01,
            0,
            0,
            0,
            0.01,
            "estimated",
            "test",
            "completed",
            "{}",
            "system",
            "test",
            "https://example.test",
            "test",
        ),
    )
    conn.execute(
        """
        INSERT INTO sessions (
            id, title, summary, source, model, started_at, ended_at, parent_session_id,
            message_count, tool_call_count, input_tokens, output_tokens, estimated_cost_usd,
            cache_read_tokens, cache_write_tokens, reasoning_tokens, actual_cost_usd,
            cost_status, cost_source, end_reason, model_config, system_prompt,
            billing_provider, billing_base_url, billing_mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "child-session",
            "Review Session",
            "Child summary",
            "cron",
            "test-model",
            "2026-04-13T15:54:00",
            "2026-04-13T15:54:20",
            "parent-session",
            2,
            1,
            5,
            2,
            0.0,
            0,
            0,
            0,
            0.0,
            "estimated",
            "test",
            "completed",
            "{}",
            "system",
            "test",
            "https://example.test",
            "test",
        ),
    )

    skill_tool_calls = json.dumps(
        [
            {
                "id": "call-skill-1",
                "call_id": "call-skill-1",
                "type": "function",
                "function": {
                    "name": "skill_manage",
                    "arguments": json.dumps({"action": "patch", "name": "trace-skill"}),
                },
            },
            {
                "id": "call-search-1",
                "call_id": "call-search-1",
                "type": "function",
                "function": {
                    "name": "session_search",
                    "arguments": json.dumps({"query": "trace normalization"}),
                },
            },
        ]
    )
    child_tool_calls = json.dumps(
        [
            {
                "id": "child-tool-1",
                "call_id": "child-tool-1",
                "type": "function",
                "function": {
                    "name": "terminal",
                    "arguments": json.dumps({"command": "npm test"}),
                },
            }
        ]
    )

    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp, tool_calls, finish_reason) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "parent-session",
            "assistant",
            "",
            "2026-04-13T15:53:40",
            skill_tool_calls,
            "tool_calls",
        ),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp, tool_call_id, tool_name) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "parent-session",
            "tool",
            json.dumps({"status": "ok", "message": "patched skill"}),
            "2026-04-13T15:53:41",
            "call-skill-1",
            "skill_manage",
        ),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp, tool_call_id, tool_name) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "parent-session",
            "tool",
            json.dumps({"count": 1, "results": [{"session_id": "child-session"}]}),
            "2026-04-13T15:53:42",
            "call-search-1",
            "session_search",
        ),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        ("parent-session", "assistant", "Done.", "2026-04-13T15:53:43"),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp, tool_calls, finish_reason) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "child-session",
            "assistant",
            "",
            "2026-04-13T15:54:01",
            child_tool_calls,
            "tool_calls",
        ),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp, tool_call_id, tool_name) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "child-session",
            "tool",
            json.dumps({"message": "review completed"}),
            "2026-04-13T15:54:02",
            "child-tool-1",
            "terminal",
        ),
    )
    conn.commit()
    conn.close()
    return db_path


class ExecutionTracePayloadTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.sessions_dir = self.root / "sessions"
        self.sessions_dir.mkdir()
        _create_state_db(self.root)
        (
            self.sessions_dir / "request_dump_parent-session_20260413_155500.json"
        ).write_text(
            json.dumps(
                {
                    "timestamp": "2026-04-13T15:55:00",
                    "session_id": "parent-session",
                    "reason": "max_retries_exhausted",
                    "request": {
                        "url": "https://api.example.test/v1/chat/completions",
                        "body": {"model": "glm-5.1"},
                    },
                }
            )
        )
        self.home_patch = mock.patch.object(dashboard_app, "HERMES_HOME", self.root)
        self.home_patch.start()

    def tearDown(self):
        self.home_patch.stop()
        self.temp_dir.cleanup()

    def test_related_session_artifacts_are_discovered(self):
        artifacts = dashboard_app._related_session_artifacts(["parent-session"])
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["kind"], "request_dump")
        self.assertEqual(artifacts[0]["session_id"], "parent-session")
        self.assertEqual(artifacts[0]["reason"], "max_retries_exhausted")
        self.assertEqual(artifacts[0]["model"], "glm-5.1")

    def test_session_activity_payload_includes_trace_targets(self):
        conn = sqlite3.connect(str(self.root / "state.db"))
        conn.row_factory = sqlite3.Row
        try:
            payload = dashboard_app._session_activity_payload(conn, "parent-session")
        finally:
            conn.close()

        self.assertEqual(
            payload["skill_events"][0]["target"], {"kind": "tool", "id": "call-skill-1"}
        )
        self.assertEqual(
            payload["session_search_events"][0]["target"],
            {"kind": "tool", "id": "call-search-1"},
        )
        self.assertEqual(
            payload["background_reviews"][0]["target"],
            {"kind": "child", "id": "child-session"},
        )
        self.assertEqual(
            payload["background_reviews"][0]["events"][0]["call_id"], "child-tool-1"
        )

    def test_get_session_returns_children_activity_and_artifacts(self):
        request = SimpleNamespace(path_params={"session_id": "parent-session"})
        response = asyncio.run(dashboard_app.get_session(request))
        payload = json.loads(response.body)

        self.assertEqual(payload["id"], "parent-session")
        self.assertEqual(payload["children"][0]["id"], "child-session")
        self.assertEqual(
            payload["background_reviews"][0]["target"],
            {"kind": "child", "id": "child-session"},
        )
        self.assertEqual(
            payload["skill_events"][0]["target"], {"kind": "tool", "id": "call-skill-1"}
        )
        self.assertEqual(payload["related_artifacts"][0]["kind"], "request_dump")

    def test_get_sessions_survives_unique_title_collision_during_backfill(self):
        conn = sqlite3.connect(str(self.root / "state.db"))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                "CREATE UNIQUE INDEX idx_sessions_title_unique ON sessions(title)"
            )
            conn.execute(
                "INSERT INTO sessions (id, title, summary, source, model, started_at, ended_at, parent_session_id, message_count, tool_call_count, input_tokens, output_tokens, estimated_cost_usd, cache_read_tokens, cache_write_tokens, reasoning_tokens, actual_cost_usd, cost_status, cost_source, end_reason, model_config, system_prompt, billing_provider, billing_base_url, billing_mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "collision-session",
                    None,
                    None,
                    "cli",
                    "test-model",
                    "2026-04-13T16:00:00",
                    "2026-04-13T16:01:00",
                    None,
                    1,
                    0,
                    0,
                    0,
                    0.0,
                    0,
                    0,
                    0,
                    0.0,
                    "estimated",
                    "test",
                    "completed",
                    "{}",
                    "system",
                    "test",
                    "https://example.test",
                    "test",
                ),
            )
            conn.execute(
                "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                ("collision-session", "user", "Parent Session", "2026-04-13T16:00:01"),
            )
            conn.commit()
        finally:
            conn.close()

        response = asyncio.run(
            dashboard_app.get_sessions(SimpleNamespace(query_params={}))
        )
        payload = json.loads(response.body)

        self.assertNotIn("error", payload)
        self.assertGreaterEqual(payload["total"], 2)
        session_ids = {item["id"] for item in payload["sessions"]}
        self.assertIn("parent-session", session_ids)
        self.assertIn("collision-session", session_ids)

    def test_session_activity_uses_persisted_tool_name_when_assistant_ids_are_sparse(
        self,
    ):
        conn = sqlite3.connect(str(self.root / "state.db"))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, timestamp, tool_calls, finish_reason) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "parent-session",
                    "assistant",
                    "",
                    "2026-04-13T15:53:50",
                    json.dumps(
                        [
                            {
                                "type": "function",
                                "function": {
                                    "name": "session_search",
                                    "arguments": json.dumps({"query": "fallback name"}),
                                },
                            }
                        ]
                    ),
                    "tool_calls",
                ),
            )
            conn.execute(
                "INSERT INTO messages (session_id, role, content, timestamp, tool_call_id, tool_name) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "parent-session",
                    "tool",
                    json.dumps({"count": 0, "results": []}),
                    "2026-04-13T15:53:51",
                    "call-runtime-name",
                    "session_search",
                ),
            )
            conn.commit()
            payload = dashboard_app._session_activity_payload(conn, "parent-session")
        finally:
            conn.close()

        self.assertEqual(
            payload["session_search_events"][-1]["tool_name"], "session_search"
        )
        self.assertEqual(
            payload["session_search_events"][-1]["target"],
            {"kind": "tool", "id": "call-runtime-name"},
        )

    def test_normalize_sse_payload_promotes_tool_call_id_to_call_id(self):
        payloads = dashboard_app._normalize_sse_payload(
            {
                "hermes": {
                    "type": "tool_output",
                    "tool_call_id": "call_promoted_1",
                    "name": "session_search",
                    "output": '{"ok": true}',
                }
            }
        )

        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["type"], "tool_output")
        self.assertEqual(payloads[0]["call_id"], "call_promoted_1")

    def test_normalize_sse_payload_preserves_existing_call_id(self):
        payloads = dashboard_app._normalize_sse_payload(
            {
                "hermes": {
                    "type": "tool_call",
                    "call_id": "call_abc123",
                    "name": "session_search",
                    "arguments": {"query": "recent work"},
                }
            }
        )

        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["type"], "tool_call")
        self.assertEqual(payloads[0]["call_id"], "call_abc123")

    def test_normalize_sse_payload_maps_correlated_hermes_tool_lifecycle(self):
        started = dashboard_app._normalize_sse_payload(
            {
                "tool": "terminal",
                "label": "Run git status",
                "toolCallId": "tool_modern_1",
                "status": "running",
            }
        )
        completed = dashboard_app._normalize_sse_payload(
            {
                "tool": "terminal",
                "toolCallId": "tool_modern_1",
                "status": "completed",
            }
        )

        self.assertEqual(
            started,
            [
                {
                    "type": "tool_call",
                    "name": "terminal",
                    "call_id": "tool_modern_1",
                    "arguments": "",
                    "progress": "Run git status",
                    "status": "running",
                }
            ],
        )
        self.assertEqual(completed[0]["type"], "tool_progress")
        self.assertEqual(completed[0]["call_id"], "tool_modern_1")
        self.assertEqual(completed[0]["status"], "completed")

    def test_child_event_metadata_accepts_top_level_session_id(self):
        self.assertEqual(
            dashboard_app._event_metadata({"type": "tool_call", "session_id": "child-top"})["session_id"],
            "child-top",
        )

    def test_child_stream_routes_content_for_main_chat_parity(self):
        child_id = "child-content-parity"
        dashboard_app.ACTIVE_CHILD_STREAMS.pop(child_id, None)
        try:
            dashboard_app._route_child_stream_event(
                "parent-run",
                {"type": "content", "content": "Subagent finding", "session_id": child_id},
            )
            events = list(dashboard_app.ACTIVE_CHILD_STREAMS[child_id]["events"])
            self.assertTrue(any("Subagent finding" in event["data"] for event in events))
        finally:
            dashboard_app.ACTIVE_CHILD_STREAMS.pop(child_id, None)


class DashboardAssistantTimelineTests(unittest.TestCase):
    def test_subagent_live_trace_preserves_main_chat_tool_semantics(self):
        result = _run_dashboard_trace_js(
            """
const state = buildDrawerLiveTraceState('child-live', [
  {type: 'content', content: 'Inspecting the file.'},
  {type: 'tool_call', id: 'call-live', function: {name: 'read_file', arguments: '{"path":"/tmp/live.txt","offset":0,"enabled":false}'}},
  {type: 'tool_output', call_id: 'call-live', name: 'read_file', output: '', status: 'complete', timestamp: '2026-07-18T12:00:01Z'},
]);
const tool = state.tools[0];
const html = renderAssistantEvents(state, 'subagent-live-child-live');
return {
  content: state.content,
  callId: tool.call_id,
  name: tool.name,
  arguments: tool.arguments,
  hasOutput: Object.prototype.hasOwnProperty.call(tool, 'output'),
  output: tool.output,
  status: tool.status,
  timestamp: tool.timestamp,
  hasMainCard: html.includes('tool-call-block'),
  hasCallId: html.includes('call-live'),
  hasContent: html.includes('Inspecting the file.'),
};
            """
        )
        self.assertEqual(result["content"], "Inspecting the file.")
        self.assertEqual(result["callId"], "call-live")
        self.assertEqual(result["name"], "read_file")
        self.assertIn('/tmp/live.txt', result["arguments"])
        self.assertTrue(result["hasOutput"])
        self.assertEqual(result["output"], "")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["timestamp"], "2026-07-18T12:00:01Z")
        self.assertTrue(result["hasMainCard"])
        self.assertTrue(result["hasCallId"])
        self.assertTrue(result["hasContent"])

    def test_content_tools_content_order_is_preserved(self):
        result = _run_dashboard_trace_js(
            """
const state = createAssistantTraceState({ sessionId: 'session-1' });
reduceAssistantTraceEvent(state, { type: 'content', text: 'Intro', replace: true, timestamp: '2026-04-13T15:00:00Z' });
reduceAssistantTraceEvent(state, { type: 'tool_call', call_id: 'call-1', name: 'read_file', arguments: '{"path":"a"}' });
reduceAssistantTraceEvent(state, { type: 'tool_output', call_id: 'call-1', name: 'read_file', output: 'contents' });
reduceAssistantTraceEvent(state, { type: 'content', text: ' Conclusion' });
return {
  items: state.trace.items.map(node => ({ kind: node.kind, text: node.payload?.text || '', call_id: node.payload?.tool?.call_id || node.call_id || null })),
  events: state.events.map(event => event.type),
  content: state.content,
};
            """
        )

        self.assertEqual(
            result["items"],
            [
                {"kind": "assistant_content", "text": "Intro", "call_id": None},
                {"kind": "tool_run", "text": "", "call_id": "call-1"},
                {"kind": "assistant_content", "text": " Conclusion", "call_id": None},
            ],
        )
        self.assertEqual(result["events"], ["content", "tool_output", "content"])
        self.assertEqual(result["content"], "Intro Conclusion")

    def test_parallel_tools_then_final_answer_group_as_one_wave(self):
        result = _run_dashboard_trace_js(
            """
const state = createAssistantTraceState({ sessionId: 'session-2' });
reduceAssistantTraceEvent(state, { type: 'tool_call', call_id: 'call-a', name: 'web_search', arguments: '{"q":"a"}' });
reduceAssistantTraceEvent(state, { type: 'tool_call', call_id: 'call-b', name: 'web_search', arguments: '{"q":"b"}' });
reduceAssistantTraceEvent(state, { type: 'tool_output', call_id: 'call-a', name: 'web_search', output: 'A' });
reduceAssistantTraceEvent(state, { type: 'tool_output', call_id: 'call-b', name: 'web_search', output: 'B' });
reduceAssistantTraceEvent(state, { type: 'content', text: 'Final answer' });
return {
  eventTypes: state.events.map(event => event.type),
  callIds: state.events.filter(event => event.tool).map(event => event.tool.call_id),
  finalText: state.events[2]?.text || '',
};
            """
        )

        self.assertEqual(result["eventTypes"], ["tool_output", "tool_output", "content"])
        self.assertEqual(result["callIds"], ["call-a", "call-b"])
        self.assertEqual(result["finalText"], "Final answer")

    def test_explicit_parallel_group_survives_reduction_persistence_and_normalization(self):
        result = _run_dashboard_trace_js(
            """
const state = createAssistantTraceState({ sessionId: 'parallel-explicit' });
reduceAssistantTraceEvent(state, {
  type: 'parallel_group',
  node: {
    kind: 'parallel_group',
    node_id: 'group-1',
    payload: {
      label: 'Reviewer supplied group',
      toolNodes: [
        { kind: 'tool_run', node_id: 'tool-a', payload: { tool: { call_id: 'same', name: 'read_file', arguments: '{}' } } },
        { kind: 'tool_run', node_id: 'tool-b', payload: { tool: { call_id: 'other', name: 'web_search', arguments: '{}' } } },
      ],
    },
  },
});
const persisted = JSON.parse(JSON.stringify({ role: 'assistant', trace: state.trace, events: state.events }));
const resumed = normalizeAssistantMessage(persisted);
reduceAssistantTraceEvent(resumed, { type: 'tool_output', call_id: 'same', name: 'read_file', output: '' });
return {
  itemKinds: resumed.trace.items.map(node => node.kind),
  eventTypes: resumed.events.map(event => event.type),
  label: resumed.events[0]?.node?.payload?.label,
  childTypes: resumed.events[0]?.node?.payload?.toolNodes.map(node => hasCapturedToolOutput(node.payload.tool) ? 'tool_output' : 'tool_call'),
};
            """
        )

        self.assertEqual(result["itemKinds"], ["parallel_group"])
        self.assertEqual(result["eventTypes"], ["parallel_group"])
        self.assertEqual(result["label"], "Reviewer supplied group")
        self.assertEqual(result["childTypes"], ["tool_output", "tool_call"])

    def test_empty_string_tool_output_is_captured_and_completed(self):
        result = _run_dashboard_trace_js(
            """
const state = createAssistantTraceState({ sessionId: 'empty-output' });
reduceAssistantTraceEvent(state, { type: 'tool_call', call_id: 'empty', name: 'terminal', arguments: '{}' });
const before = state.events[0].type;
reduceAssistantTraceEvent(state, { type: 'tool_output', call_id: 'empty', name: 'terminal', output: '' });
const tool = state.trace.toolNodes[0].payload.tool;
return {
  before,
  after: state.events[0].type,
  captured: hasCapturedToolOutput(tool),
  status: getToolStatusClass(tool),
  outputPanel: renderToolOutput(tool.name, null, '', hasCapturedToolOutput(tool)),
};
            """
        )

        self.assertEqual(result["before"], "tool_call")
        self.assertEqual(result["after"], "tool_output")
        self.assertTrue(result["captured"])
        self.assertEqual(result["status"], "complete")
        self.assertIn("completed with empty output", result["outputPanel"])

    def test_duplicate_call_ids_are_render_scoped_and_never_enter_inline_javascript(self):
        result = _run_dashboard_trace_js(
            """
const attack = `shared');globalThis.__storedXss=true;//`;
const first = { role: 'assistant', tools: [{ call_id: attack, name: 'read_file', arguments: '{"path":"one"}' }] };
const second = { role: 'assistant', tools: [{ call_id: attack, name: 'read_file', arguments: '{"path":"two"}' }] };
const firstHtml = renderAssistantMessage(first);
const secondHtml = renderAssistantMessage(second);
const firstKey = Array.from(toolCallData.keys())[0];
const secondKey = Array.from(toolCallData.keys())[1];
toolCallUiState.get(firstKey).expanded = true;
return {
  firstKey,
  secondKey,
  independent: firstKey !== secondKey && toolCallUiState.get(secondKey).expanded === false,
  noInlineHandler: !firstHtml.includes('onclick=') && !secondHtml.includes('onclick='),
  escapedAttribute: firstHtml.includes('&#039;'),
  distinctInputs: toolCallData.get(firstKey).parsedArgs.raw !== toolCallData.get(secondKey).parsedArgs.raw,
};
            """
        )

        self.assertNotEqual(result["firstKey"], result["secondKey"])
        self.assertTrue(result["independent"])
        self.assertTrue(result["noInlineHandler"])
        self.assertTrue(result["escapedAttribute"])
        self.assertTrue(result["distinctInputs"])

    def test_raw_tool_panel_safely_serializes_circular_and_bigint_payloads(self):
        result = _run_dashboard_trace_js(
            """
const circular = { count: 9n };
circular.self = circular;
const key = getToolCallId({ call_id: 'raw' }, 0, { renderScope: 'raw-test' });
const tool = { call_id: 'raw', name: 'custom', arguments: circular, output: circular };
toolCallData.set(key, {
  tool,
  options: { node: { payload: circular } },
  parsedArgs: parseToolPayload(circular),
  parsedOutput: parseToolPayload(circular),
});
const html = renderToolPanelContent(key, 'raw');
return { hasBigInt: html.includes('9n'), hasCircular: html.includes('[Circular]') };
            """
        )

        self.assertTrue(result["hasBigInt"])
        self.assertTrue(result["hasCircular"])

    def test_multiple_tool_waves_stay_separate_inside_one_step(self):
        result = _run_dashboard_trace_js(
            """
const state = createAssistantTraceState({ sessionId: 'session-3' });
reduceAssistantTraceEvent(state, { type: 'content', text: 'Wave 1 intro', replace: true });
reduceAssistantTraceEvent(state, { type: 'tool_call', call_id: 'call-1', name: 'web_search', arguments: '{}' });
reduceAssistantTraceEvent(state, { type: 'tool_call', call_id: 'call-2', name: 'web_search', arguments: '{}' });
reduceAssistantTraceEvent(state, { type: 'tool_output', call_id: 'call-1', name: 'web_search', output: '1' });
reduceAssistantTraceEvent(state, { type: 'tool_output', call_id: 'call-2', name: 'web_search', output: '2' });
reduceAssistantTraceEvent(state, { type: 'content', text: ' Wave 2 intro' });
reduceAssistantTraceEvent(state, { type: 'tool_call', call_id: 'call-3', name: 'read_file', arguments: '{}' });
reduceAssistantTraceEvent(state, { type: 'tool_output', call_id: 'call-3', name: 'read_file', output: '3' });
reduceAssistantTraceEvent(state, { type: 'content', text: ' Final' });
return {
  eventTypes: state.events.map(event => event.type),
  labels: state.events.map(event => event.type === 'parallel_group'
    ? event.node.payload.label
    : (event.type === 'content' ? event.text : event.tool?.call_id || '')),
};
            """
        )

        self.assertEqual(
            result["eventTypes"],
            ["content", "tool_output", "tool_output", "content", "tool_output", "content"],
        )
        self.assertEqual(result["labels"][0], "Wave 1 intro")
        self.assertEqual(result["labels"][3], " Wave 2 intro")
        self.assertEqual(result["labels"][5], " Final")

    def test_resume_mid_run_preserves_timeline_order(self):
        result = _run_dashboard_trace_js(
            """
const state = createAssistantTraceState({ sessionId: 'session-4' });
reduceAssistantTraceEvent(state, { type: 'content', text: 'Intro', replace: true });
reduceAssistantTraceEvent(state, { type: 'tool_call', call_id: 'call-1', name: 'read_file', arguments: '{}' });
const persisted = JSON.parse(JSON.stringify({
  role: 'assistant',
  content: state.content,
  tools: state.tools,
  events: state.events,
  trace: state.trace,
}));
const resumed = normalizeAssistantMessage(persisted);
reduceAssistantTraceEvent(resumed, { type: 'tool_output', call_id: 'call-1', name: 'read_file', output: 'done' });
reduceAssistantTraceEvent(resumed, { type: 'content', text: ' After' });
return {
  itemKinds: resumed.trace.items.map(node => node.kind),
  eventTypes: resumed.events.map(event => event.type),
  content: resumed.content,
};
            """
        )

        self.assertEqual(
            result["itemKinds"], ["assistant_content", "tool_run", "assistant_content"]
        )
        self.assertEqual(result["eventTypes"], ["content", "tool_output", "content"])
        self.assertEqual(result["content"], "Intro After")

    def test_unmatched_output_stays_orphan_until_matching_call_arrives(self):
        result = _run_dashboard_trace_js(
            """
const state = createAssistantTraceState({ sessionId: 'session-5' });
reduceAssistantTraceEvent(state, { type: 'content', text: 'Intro', replace: true });
reduceAssistantTraceEvent(state, { type: 'tool_output', call_id: 'call-orphan', name: 'web_search', output: 'first orphan' });
const orphanSnapshot = {
  eventTypes: state.events.map(event => event.type),
  orphanCount: state.trace.orphanNodes.length,
  toolCount: state.trace.toolNodes.length,
};
reduceAssistantTraceEvent(state, { type: 'tool_call', call_id: 'call-orphan', name: 'web_search', arguments: '{}' });
return {
  orphanSnapshot,
  finalEventTypes: state.events.map(event => event.type),
  finalOrphanCount: state.trace.orphanNodes.length,
  finalToolCount: state.trace.toolNodes.length,
  itemKinds: state.trace.items.map(node => node.kind),
};
            """
        )

        self.assertEqual(
            result["orphanSnapshot"],
            {"eventTypes": ["content", "diagnostic"], "orphanCount": 1, "toolCount": 0},
        )
        self.assertEqual(result["finalEventTypes"], ["content", "tool_output"])
        self.assertEqual(result["finalOrphanCount"], 0)
        self.assertEqual(result["finalToolCount"], 1)
        self.assertEqual(result["itemKinds"], ["assistant_content", "tool_run"])

    def test_progress_without_call_id_promotes_into_matching_tool_call(self):
        result = _run_dashboard_trace_js(
            """
const state = createAssistantTraceState({ sessionId: 'session-6' });
reduceAssistantTraceEvent(state, { type: 'content', text: 'Checking', replace: true });
reduceAssistantTraceEvent(state, {
  type: 'tool_progress',
  name: 'session_search',
  arguments: { query: 'build cycle project spec built' },
  progress: 'build cycle project spec built',
});
const beforeCall = {
  eventTypes: state.events.map(event => event.type),
  orphanCount: state.trace.orphanNodes.length,
};
reduceAssistantTraceEvent(state, {
  type: 'tool_call',
  call_id: 'call-search-1',
  name: 'session_search',
  arguments: { query: 'build cycle project spec built' },
});
reduceAssistantTraceEvent(state, {
  type: 'tool_output',
  call_id: 'call-search-1',
  name: 'session_search',
  output: 'done',
});
return {
  beforeCall,
  afterCallEventTypes: state.events.map(event => event.type),
  orphanCount: state.trace.orphanNodes.length,
  toolCount: state.trace.toolNodes.length,
  toolProgress: state.trace.toolNodes[0]?.payload?.tool?.progress || [],
  itemKinds: state.trace.items.map(node => node.kind),
};
            """
        )

        self.assertEqual(
            result["beforeCall"],
            {"eventTypes": ["content", "diagnostic"], "orphanCount": 1},
        )
        self.assertEqual(result["afterCallEventTypes"], ["content", "tool_output"])
        self.assertEqual(result["orphanCount"], 0)
        self.assertEqual(result["toolCount"], 1)
        self.assertEqual(result["itemKinds"], ["assistant_content", "tool_run"])
        self.assertEqual(
            result["toolProgress"][0]["label"], "build cycle project spec built"
        )

    def test_preview_progress_promotes_into_adjacent_matching_tool_call(self):
        result = _run_dashboard_trace_js(
            """
const state = createAssistantTraceState({ sessionId: 'session-6b' });
reduceAssistantTraceEvent(state, { type: 'content', text: 'Checking', replace: true });
reduceAssistantTraceEvent(state, {
  type: 'tool_progress',
  name: 'session_search',
  arguments: 'recall: "what was I working on in the last 6 hours..."',
  progress: 'started',
});
reduceAssistantTraceEvent(state, {
  type: 'tool_call',
  call_id: 'call-search-preview',
  name: 'session_search',
  arguments: { query: 'what was I working on in the last 6 hours', token_budget: 4000 },
});
reduceAssistantTraceEvent(state, {
  type: 'tool_output',
  call_id: 'call-search-preview',
  name: 'session_search',
  output: 'done',
});
return {
  eventTypes: state.events.map(event => event.type),
  orphanCount: state.trace.orphanNodes.length,
  toolCount: state.trace.toolNodes.length,
  toolCallId: state.trace.toolNodes[0]?.payload?.tool?.call_id || null,
  toolProgress: state.trace.toolNodes[0]?.payload?.tool?.progress || [],
  itemKinds: state.trace.items.map(node => node.kind),
};
            """
        )

        self.assertEqual(result["eventTypes"], ["content", "tool_output"])
        self.assertEqual(result["orphanCount"], 0)
        self.assertEqual(result["toolCount"], 1)
        self.assertEqual(result["toolCallId"], "call-search-preview")
        self.assertEqual(result["itemKinds"], ["assistant_content", "tool_run"])
        self.assertEqual(result["toolProgress"][0]["label"], "started")

    def test_terminal_progress_diagnostics_stay_separate_until_matching_call(self):
        result = _run_dashboard_trace_js(
            """
const state = createAssistantTraceState({ sessionId: 'session-term-progress' });
reduceAssistantTraceEvent(state, {
  type: 'tool_progress',
  name: 'terminal',
  arguments: { command: 'python one.py' },
  progress: 'starting one',
});
reduceAssistantTraceEvent(state, {
  type: 'tool_progress',
  name: 'terminal',
  arguments: { command: 'python two.py' },
  progress: 'starting two',
});
const beforeCalls = {
  orphanCount: state.trace.orphanNodes.length,
  orphanCommands: state.trace.orphanNodes.map(node => node.payload.tool.arguments.command),
};
reduceAssistantTraceEvent(state, {
  type: 'tool_call',
  call_id: 'call-terminal-one',
  name: 'terminal',
  arguments: { command: 'python one.py' },
});
reduceAssistantTraceEvent(state, {
  type: 'tool_call',
  call_id: 'call-terminal-two',
  name: 'terminal',
  arguments: { command: 'python two.py' },
});
return {
  beforeCalls,
  orphanCount: state.trace.orphanNodes.length,
  toolCount: state.trace.toolNodes.length,
  progressByCommand: state.trace.toolNodes.map(node => ({
    command: node.payload.tool.arguments.command,
    labels: node.payload.tool.progress.map(item => item.label),
  })),
  eventTypes: state.events.map(event => event.type),
};
            """
        )

        self.assertEqual(result["beforeCalls"]["orphanCount"], 2)
        self.assertEqual(
            result["beforeCalls"]["orphanCommands"], ["python one.py", "python two.py"]
        )
        self.assertEqual(result["orphanCount"], 0)
        self.assertEqual(result["toolCount"], 2)
        self.assertEqual(
            result["progressByCommand"],
            [
                {"command": "python one.py", "labels": ["starting one"]},
                {"command": "python two.py", "labels": ["starting two"]},
            ],
        )
        self.assertEqual(result["eventTypes"], ["tool_call", "tool_call"])

    def test_progress_uses_tool_call_id_alias_for_matching_running_tool(self):
        result = _run_dashboard_trace_js(
            """
const state = createAssistantTraceState({ sessionId: 'session-progress-alias' });
reduceAssistantTraceEvent(state, {
  type: 'tool_call',
  call_id: 'call-terminal-alias',
  name: 'terminal',
  arguments: { command: 'pytest' },
});
reduceAssistantTraceEvent(state, {
  type: 'tool_progress',
  tool_call_id: 'call-terminal-alias',
  name: 'terminal',
  progress: 'running pytest',
});
return {
  orphanCount: state.trace.orphanNodes.length,
  toolCount: state.trace.toolNodes.length,
  toolProgress: state.trace.toolNodes[0]?.payload?.tool?.progress || [],
  eventTypes: state.events.map(event => event.type),
};
            """
        )

        self.assertEqual(result["orphanCount"], 0)
        self.assertEqual(result["toolCount"], 1)
        self.assertEqual(result["toolProgress"][0]["label"], "running pytest")
        self.assertEqual(result["eventTypes"], ["tool_call"])

    def test_delegate_task_renderer_accepts_raw_result_arrays(self):
        result = _run_dashboard_trace_js(
            """
globalThis.escapeHtml = (value) => String(value ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/\"/g, '&quot;')
  .replace(/'/g, '&#039;');
globalThis.highlightJSON = (value) => String(value ?? '');
const raw = JSON.stringify([
  { status: 'completed', task_index: 0, summary: 'subagent A found the bug', duration_seconds: 3 },
  { status: 'failed', task_index: 1, error: 'subagent B timed out', api_calls: 2 }
]);
const html = renderToolOutput('delegate_task', JSON.parse(raw), raw);
return {
  hasFirstSummary: html.includes('subagent A found the bug'),
  hasSecondError: html.includes('subagent B timed out'),
  hasNoEmptyWarning: !html.includes('No delegated task results were returned.'),
};
            """
        )

        self.assertTrue(result["hasFirstSummary"])
        self.assertTrue(result["hasSecondError"])
        self.assertTrue(result["hasNoEmptyWarning"])

    def test_tool_payload_and_call_normalization_preserve_falsy_values_and_skip_malformed_entries(self):
        result = _run_dashboard_trace_js(
            """
const calls = normalizeToolCallEntries([
  null,
  false,
  { id: 'zero', name: 'counter', arguments: 0, output: false },
  { id: 'empty', function: { name: 'empty_tool', arguments: '' }, output: 0 },
]);
return {
  parsedFalse: parseToolPayload(false),
  parsedZero: parseToolPayload(0),
  calls,
};
            """
        )

        self.assertEqual(result["parsedFalse"]["parsed"], False)
        self.assertEqual(result["parsedZero"]["parsed"], 0)
        self.assertEqual(len(result["calls"]), 2)
        self.assertEqual(result["calls"][0]["arguments"], 0)
        self.assertEqual(result["calls"][0]["output"], False)
        self.assertEqual(result["calls"][1]["arguments"], "")
        self.assertEqual(result["calls"][1]["output"], 0)

    def test_falsy_tool_outputs_are_complete_and_circular_payloads_retain_structure(self):
        result = _run_dashboard_trace_js(
            """
const circular = { call_id: 'circle', status: false };
circular.self = circular;
return {
  falseStatus: getToolStatusClass({ call_id: 'false', name: 'flag', output: false }),
  zeroStatus: getToolStatusClass({ call_id: 'zero', name: 'count', output: 0 }),
  circularRaw: parseToolPayload(circular).raw,
};
            """
        )

        self.assertEqual(result["falseStatus"], "complete")
        self.assertEqual(result["zeroStatus"], "complete")
        self.assertIn('"call_id": "circle"', result["circularRaw"])
        self.assertIn("[Circular]", result["circularRaw"])

    def test_delegate_task_renderer_unwraps_nested_envelopes_and_renders_falsy_fields(self):
        result = _run_dashboard_trace_js(
            """
globalThis.escapeHtml = (value) => String(value ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
globalThis.highlightJSON = (value) => String(value ?? '');
const payload = { data: { output: { results: [
  null,
  { status: 'completed', title: 'Falsy result', result: false, duration_seconds: 0, api_calls: 0 },
  { status: 'completed', title: 'Zero result', output: 0 }
] } } };
const raw = JSON.stringify(payload);
const html = renderToolOutput('delegate_task', payload, raw);
return {
  hasFalsyResult: html.includes('false'),
  hasZeroResult: html.includes('>0<'),
  hasRaw: html.includes(raw),
  noEmptyWarning: !html.includes('No delegated task results were returned.'),
};
            """
        )

        self.assertTrue(result["hasFalsyResult"])
        self.assertTrue(result["hasZeroResult"])
        self.assertTrue(result["hasRaw"])
        self.assertTrue(result["noEmptyWarning"])

    def test_execution_history_shows_latest_three_and_keeps_full_history_expandable(self):
        result = _run_dashboard_trace_js(
            """
globalThis.escapeHtml = (value) => String(value ?? '');
const entries = Array.from({length: 7}, (_, idx) => ({ html: `<i>call-${idx + 1}</i>` }));
const html = renderToolCallList(entries);
return {
  hasBubble: html.includes('execution-history-bubble'),
  hiddenCount: (html.match(/execution-history-older/g) || []).length,
  latestHtml: html.split('execution-history-latest')[1],
  toggleLabel: html.includes('Show 4 earlier calls'),
};
            """
        )

        self.assertTrue(result["hasBubble"])
        self.assertEqual(result["hiddenCount"], 1)
        self.assertNotIn("call-4", result["latestHtml"])
        self.assertIn("call-5", result["latestHtml"])
        self.assertIn("call-6", result["latestHtml"])
        self.assertIn("call-7", result["latestHtml"])
        self.assertTrue(result["toggleLabel"])

    def test_live_renderer_groups_tools_across_blank_stream_content(self):
        result = _run_dashboard_trace_js(
            """
const events = [];
for (let idx = 1; idx <= 5; idx += 1) {
  events.push({type: 'tool_call', tool: {call_id: `blank-${idx}`, name: `tool-${idx}`, output: 'ok'}});
  if (idx < 5) events.push({type: 'content', text: '\\n'});
}
const html = groupSequentialToolCards(events).join('');
return {
  bubbles: (html.match(/execution-history-bubble/g) || []).length,
  toggle: html.includes('Show 2 earlier calls'),
  latest: html.split('execution-history-latest')[1] || '',
};
            """
        )
        self.assertEqual(result["bubbles"], 1)
        self.assertTrue(result["toggle"])
        self.assertNotIn("tool-2", result["latest"])
        self.assertTrue(all(name in result["latest"] for name in ("tool-3", "tool-4", "tool-5")))

    def test_live_renderer_keeps_meaningful_content_as_execution_boundary(self):
        result = _run_dashboard_trace_js(
            """
const html = groupSequentialToolCards([
  {type: 'tool_call', tool: {call_id: 'first', name: 'first'}},
  {type: 'content', text: 'Checked the first source.'},
  {type: 'tool_call', tool: {call_id: 'second', name: 'second'}},
]).join('');
return {bubbles: (html.match(/execution-history-bubble/g) || []).length, hasText: html.includes('Checked the first source.')};
            """
        )
        self.assertEqual(result, {"bubbles": 2, "hasText": True})

    def test_transcript_pipeline_condenses_adjacent_assistant_tool_rows_between_content(self):
        result = _run_dashboard_trace_js(
            """
const toolRow = (prefix, count) => Array.from({length: count}, (_, idx) => ({
  role: 'assistant', content: '', events: [{type: 'tool_call', tool: {
    call_id: `${prefix}${idx + 1}`, name: `${prefix}${idx + 1}`, output: 'ok'}}]
}));
const rows = [
  {role: 'assistant', content: 'A'}, ...toolRow('t', 6),
  {role: 'assistant', content: 'B'}, ...toolRow('u', 5),
  {role: 'assistant', content: 'C'},
];
const segments = buildTranscriptRenderSegments(rows);
const html = renderTranscriptSegments(segments, {assistant: body => body, boundary: () => ''});
return {
  types: segments.map(segment => segment.type),
  counts: segments.filter(segment => segment.type === 'execution').map(segment => segment.updates.length),
  bubbles: (html.match(/execution-history-bubble/g) || []).length,
  labels: ['Show 3 earlier calls', 'Show 2 earlier calls'].map(label => html.includes(label)),
  firstLatest: html.split('execution-history-latest')[1].split('</section>')[0],
  secondLatest: html.split('execution-history-latest')[2].split('</section>')[0],
};
            """
        )
        self.assertEqual(result["types"], ["assistant", "execution", "assistant", "execution", "assistant"])
        self.assertEqual(result["counts"], [6, 5])
        self.assertEqual(result["bubbles"], 2)
        self.assertEqual(result["labels"], [True, True])
        self.assertNotIn("t3", result["firstLatest"])
        self.assertTrue(all(name in result["firstLatest"] for name in ("t4", "t5", "t6")))
        self.assertNotIn("u2", result["secondLatest"])
        self.assertTrue(all(name in result["secondLatest"] for name in ("u3", "u4", "u5")))

    def test_parallel_group_is_one_ordered_update_without_splitting_execution_segment(self):
        result = _run_dashboard_trace_js(
            """
const parallelNode = {payload: {label: 'pair', toolNodes: [
  {payload: {tool: {call_id: 'p1', name: 'read_file', output: 'a'}}},
  {payload: {tool: {call_id: 'p2', name: 'read_file', output: 'b'}}},
]}};
const rows = [{role: 'assistant', events: [
  {type: 'tool_call', tool: {call_id: 'before', name: 'before', output: 'ok'}},
  {type: 'parallel_group', node: parallelNode},
  {type: 'tool_call', tool: {call_id: 'after', name: 'after', output: 'ok'}},
]}];
const segments = buildTranscriptRenderSegments(rows);
const html = renderTranscriptSegments(segments, {assistant: body => body, boundary: () => ''});
return {types: segments.map(x => x.type), count: segments[0].updates.length,
  bubbles: (html.match(/execution-history-bubble/g) || []).length,
  parallel: html.includes('parallel 2')};
            """
        )
        self.assertEqual(result, {"types": ["execution"], "count": 3, "bubbles": 1, "parallel": True})

    def test_execution_segment_expansion_has_stable_key_across_live_rerenders(self):
        result = _run_dashboard_trace_js(
            """
const rows = Array.from({length: 4}, (_, idx) => ({
  role: 'assistant', events: [{type: 'tool_call', tool: {call_id: `live-${idx + 1}`, name: 'terminal'}}]
}));
const render = () => {
  const segments = buildTranscriptRenderSegments(rows);
  return {segments, html: renderTranscriptSegments(segments, {assistant: body => body, boundary: () => ''})};
};
const first = render();
const key = first.segments[0].segmentKey;
setExecutionHistoryExpanded(key, true);
rows.push({role: 'assistant', events: [{type: 'tool_call', tool: {call_id: 'live-5', name: 'terminal'}}]});
const second = render();
return {
  sameKey: key === second.segments[0].segmentKey,
  initiallyClosed: !first.html.includes('<details class="execution-history-older" open'),
  remainsOpen: second.html.includes('<details class="execution-history-older" open'),
  appendedCallRendered: second.html.includes('live-5'),
};
            """
        )
        self.assertEqual(result, {
            "sameKey": True,
            "initiallyClosed": True,
            "remainsOpen": True,
            "appendedCallRendered": True,
        })

    def test_execution_segment_keys_do_not_collide_between_segments(self):
        result = _run_dashboard_trace_js(
            """
const rows = [
  {role: 'assistant', events: [{type: 'tool_call', tool: {call_id: 'same', name: 'terminal'}}]},
  {role: 'user', content: 'boundary'},
  {role: 'assistant', events: [{type: 'tool_call', tool: {call_id: 'same', name: 'terminal'}}]},
];
const segments = buildTranscriptRenderSegments(rows).filter(segment => segment.type === 'execution');
return {count: segments.length, unique: new Set(segments.map(segment => segment.segmentKey)).size};
            """
        )
        self.assertEqual(result, {"count": 2, "unique": 2})

    def test_merged_execution_shell_aggregates_unique_row_usage_and_keeps_latest_context(self):
        result = _run_dashboard_trace_js(
            """
const first = {role: 'assistant', usage: {total_tokens: 11, prompt_tokens: 7, model: 'old'},
  last_prompt_tokens: 101, events: [
    {type: 'tool_call', tool: {call_id: 'a', name: 'terminal'}},
    {type: 'tool_output', tool: {call_id: 'a', name: 'terminal', output: 'ok'}},
  ]};
const second = {role: 'assistant', usage: {total_tokens: 22, prompt_tokens: 13, model: 'new'},
  last_prompt_tokens: 202, events: [{type: 'tool_call', tool: {call_id: 'b', name: 'read_file'}}]};
const segment = buildTranscriptRenderSegments([first, second])[0];
const firstNormalized = normalizeAssistantMessage(first);
const secondNormalized = normalizeAssistantMessage(second);
const deduped = mergeTranscriptUsageMetadata([
  {message: first, normalized: firstNormalized},
  {message: first, normalized: firstNormalized},
  {message: second, normalized: secondNormalized},
]);
const html = renderTranscriptSegments([segment], {
  assistant: (body, merged) => renderAssistantMessageShell(merged.message, merged.normalized, body), boundary: () => ''
});
return {usage: segment.normalized.usage, dedupedTotal: deduped.usage.total_tokens,
  context: segment.normalized.last_prompt_tokens,
  total33: html.includes('Total: 33'), prompt20: html.includes('Prompt: 20')};
            """
        )
        self.assertEqual(result["usage"]["total_tokens"], 33)
        self.assertEqual(result["usage"]["prompt_tokens"], 20)
        self.assertEqual(result["usage"]["model"], "new")
        self.assertEqual(result["dedupedTotal"], 33)
        self.assertEqual(result["context"], 202)
        self.assertTrue(result["total33"])
        self.assertTrue(result["prompt20"])

    def test_adjacent_calls_are_not_inferred_to_be_parallel(self):
        result = _run_dashboard_trace_js(
            """
const grouped = groupParallelToolEvents([
  { type: 'tool_call', tool: { call_id: 'one', name: 'read_file' } },
  { type: 'tool_call', tool: { call_id: 'two', name: 'terminal' } },
]);
return grouped.map(event => event.type);
            """
        )

        self.assertEqual(result, ["tool_call", "tool_call"])

    def test_debug_details_include_known_falsy_fields_other_fields_and_raw_payload(self):
        result = _run_dashboard_trace_js(
            """
globalThis.escapeHtml = (value) => String(value ?? '');
const html = renderLogDetails({ args: false, result: 0, error: '', call_id: 'abc', status: 'done' });
return {
  arguments: html.includes('Arguments') && html.includes('false'),
  result: html.includes('Result') && html.includes('0'),
  fields: html.includes('call_id') && html.includes('abc') && html.includes('status'),
  raw: html.includes('Raw payload'),
};
            """
        )

        self.assertTrue(result["arguments"])
        self.assertTrue(result["result"])
        self.assertTrue(result["fields"])
        self.assertTrue(result["raw"])

    def test_historical_hydration_uses_same_timeline_semantics(self):
        result = _run_dashboard_trace_js(
            """
const trace = buildHistoricalExecutionTrace({
  id: 'history-session',
  messages: [
    {
      id: 1,
      role: 'assistant',
      content: 'Intro',
      timestamp: '2026-04-13T15:00:00Z',
      tool_calls: [
        { id: 'call-1', call_id: 'call-1', type: 'function', function: { name: 'read_file', arguments: '{}' } },
        { id: 'call-2', call_id: 'call-2', type: 'function', function: { name: 'read_file', arguments: '{}' } }
      ],
    },
    { id: 2, role: 'tool', tool_call_id: 'call-1', tool_name: 'read_file', content: 'A', timestamp: '2026-04-13T15:00:01Z' },
    { id: 3, role: 'tool', tool_call_id: 'call-2', tool_name: 'read_file', content: 'B', timestamp: '2026-04-13T15:00:02Z' },
    { id: 4, role: 'assistant', content: 'Done', timestamp: '2026-04-13T15:00:03Z' },
  ],
});
const firstAssistant = normalizeAssistantMessage(trace.messages[0]);
return {
  eventTypes: firstAssistant.events.map(event => event.type),
  itemKinds: firstAssistant.trace.items.map(node => node.kind),
  content: firstAssistant.content,
};
            """
        )

        self.assertEqual(result["eventTypes"], ["content", "tool_output", "tool_output"])
        self.assertEqual(
            result["itemKinds"], ["assistant_content", "tool_run", "tool_run"]
        )
        self.assertEqual(result["content"], "Intro")


class DashboardReadmeFeatureWiringTests(unittest.TestCase):
    def test_skill_listing_and_content_support_flat_and_categorized_layouts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            flat = root / "skills" / "flat-skill"
            categorized = root / "skills" / "software-development" / "cat-skill"
            flat.mkdir(parents=True)
            categorized.mkdir(parents=True)
            flat.joinpath("SKILL.md").write_text(
                "---\nname: Flat Skill\ndescription: Flat description\n---\n# Flat\n"
            )
            categorized.joinpath("SKILL.md").write_text(
                "---\nname: Cat Skill\ndescription: Cat description\n---\n# Cat\n"
            )

            with mock.patch.object(dashboard_app, "HERMES_HOME", root), mock.patch.object(
                dashboard_app, "get_config", return_value={"skills": {"disabled": []}}
            ):
                response = asyncio.run(dashboard_app.get_skills(SimpleNamespace()))
                payload = json.loads(response.body)
                skills = {skill["id"]: skill for skill in payload["skills"]}
                self.assertEqual(skills["flat-skill"]["name"], "Flat Skill")
                self.assertEqual(skills["flat-skill"]["category"], "")
                self.assertEqual(skills["cat-skill"]["name"], "Cat Skill")
                self.assertEqual(
                    skills["cat-skill"]["category"], "software-development"
                )

                content_response = asyncio.run(
                    dashboard_app.get_skill_content(
                        SimpleNamespace(path_params={"skill_id": "cat-skill"})
                    )
                )
                content_payload = json.loads(content_response.body)
                self.assertIn("# Cat", content_payload["content"])

    def test_graph_time_filter_handles_iso_timestamps_and_flat_skills(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "skills" / "flat-skill").mkdir(parents=True)
            (root / "skills" / "flat-skill" / "SKILL.md").write_text(
                "---\nname: Flat Skill\ndescription: Flat graph skill\n---\n"
            )
            conn = sqlite3.connect(root / "state.db")
            conn.execute(
                """
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY, title TEXT, source TEXT, model TEXT,
                    parent_session_id TEXT, summary TEXT, started_at TEXT,
                    ended_at TEXT, message_count INTEGER, tool_call_count INTEGER,
                    input_tokens INTEGER, output_tokens INTEGER,
                    estimated_cost_usd REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT,
                    tool_call_id TEXT, tool_calls TEXT, tool_name TEXT, timestamp TEXT
                )
                """
            )
            now = datetime.datetime.now(datetime.timezone.utc)
            recent = now.isoformat()
            old = (now - datetime.timedelta(days=3)).isoformat()
            conn.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("recent", "Recent", "cli", "model-a", None, "", recent, recent, 1, 0, 0, 0, 0.0),
            )
            conn.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("old", "Old", "cli", "model-a", None, "", old, old, 1, 0, 0, 0, 0.0),
            )
            conn.commit()
            conn.close()

            request = SimpleNamespace(query_params={"depth": "full", "hours": "24"})
            with mock.patch.object(dashboard_app, "HERMES_HOME", root), mock.patch.object(
                dashboard_app, "get_config", return_value={"skills": {"disabled": []}}
            ):
                response = asyncio.run(dashboard_app.get_graph_data(request))
                payload = json.loads(response.body)

            node_ids = {node["id"] for node in payload["nodes"]}
            self.assertIn("session:recent", node_ids)
            self.assertNotIn("session:old", node_ids)
            self.assertIn("skill:flat-skill", node_ids)
            self.assertNotIn("error", payload)

    def test_hermes_agent_path_uses_installer_env_override(self):
        with tempfile.TemporaryDirectory() as td:
            configured = Path(td)
            with mock.patch.dict(os.environ, {"HERMES_AGENT_PATH": str(configured)}):
                self.assertEqual(dashboard_app._hermes_agent_path(), configured.resolve())



if __name__ == "__main__":
    unittest.main()
