import asyncio
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


def _extract_dashboard_js_helpers() -> str:
    index_html = (
        Path(__file__).resolve().parent.parent / "templates" / "index.html"
    ).read_text()
    start = index_html.index("function makeExecutionNodeId")
    end = index_html.index("function parseToolPayload")
    middle_end = index_html.index("function getDelegateChildBucket")
    script_parts = [
        "function log() {}\n",
        index_html[start:end],
        index_html[end:middle_end],
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
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
        f.write(script)
        tmp_path = f.name
    try:
        result = subprocess.run(
            ["node", tmp_path],
            cwd=Path(__file__).resolve().parent.parent,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
    finally:
        os.unlink(tmp_path)


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


class DashboardAssistantTimelineTests(unittest.TestCase):
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
  parallelCount: state.events[0]?.node?.payload?.toolNodes?.length || 0,
  finalText: state.events[1]?.text || '',
};
            """
        )

        self.assertEqual(result["eventTypes"], ["parallel_group", "content"])
        self.assertEqual(result["parallelCount"], 2)
        self.assertEqual(result["finalText"], "Final answer")

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
            ["content", "parallel_group", "content", "tool_output", "content"],
        )
        self.assertEqual(result["labels"][0], "Wave 1 intro")
        self.assertEqual(result["labels"][2], " Wave 2 intro")
        self.assertEqual(result["labels"][4], " Final")

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
        self.assertEqual(result["eventTypes"], ["parallel_group"])

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

        self.assertEqual(result["eventTypes"], ["content", "parallel_group"])
        self.assertEqual(
            result["itemKinds"], ["assistant_content", "tool_run", "tool_run"]
        )
        self.assertEqual(result["content"], "Intro")


if __name__ == "__main__":
    unittest.main()
