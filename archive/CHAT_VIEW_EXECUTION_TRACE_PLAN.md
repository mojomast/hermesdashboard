# Chat View Execution Trace Plan

## Goal

Improve the Hermes dashboard chat view so users can understand in-progress and historical agent execution without losing nested context.

The specific problems to solve are:

- nested work is missing or only visible in side panels
- tool activity can appear out of order or detached from the assistant step that caused it
- status/update pills do not point back to the exact transcript location they describe
- live rendering and historical session rendering diverge

This plan is written for a separate implementation agent.

## Primary Outcome

Build a unified execution-trace rendering model for the dashboard that:

- groups assistant steps and their tool activity coherently
- preserves parallel tool-call batches visually
- shows child/background runs as inline stages or linked execution nodes
- makes status/update items clickable and scroll to the exact nested area they refer to
- keeps live streaming and historical hydration behavior aligned

## Scope Priority

### Phase 1

- front-end normalization layer for transcript/execution nodes
- anchored DOM ids for messages, tools, child sessions, and diagnostics
- click-to-jump from status/update pills into the nested transcript area
- historical session rendering improvements using existing data
- inline rendering for child/background review stages

### Phase 2

- backend payload improvements for stable linkage and deterministic ordering
- preserve full canonical tool-call payloads in persisted session data
- add stronger child-run linkage and request-dump attachment

### Phase 3

- event-log persistence for full execution trace reconstruction
- monotonic sequence numbers and first-class tool/subagent run records

## Required Context

### Dashboard Frontend

- [`templates/index.html`](templates/index.html)
  - `buildConversationFromSessionData()`
  - `renderConversation()`
  - `renderAssistantMessage()`
  - `renderAssistantEvents()`
  - `renderToolBlock()`
  - `renderDelegateChildStreams()`
  - `viewSession()`
  - `renderSessionMessage()`
  - `renderSessionOverview()`
  - `renderBackgroundReviews()`
  - `renderRequestResultActivity()`
  - `navigateTo()`
  - `handleHashChange()`
  - `streamChatRun()`

### Dashboard Backend

- [`app.py`](app.py)
  - `get_session()`
  - `_session_activity_payload()`
  - `_session_overview_payload()`
  - `_child_session_ids()`
  - `get_session_files()`
  - `_run_chat_stream()`

### Active Hermes Runtime

- [`../hermes-agent/run_agent.py`](../hermes-agent/run_agent.py)
  - `_flush_messages_to_session_db()` currently persists some tool-call rows without canonical ids
- [`../hermes-agent/hermes_state.py`](../hermes-agent/hermes_state.py)
  - `sessions` and `messages` storage model
  - `append_message()` ordering behavior
- [`../hermes-agent/tools/delegate_tool.py`](../hermes-agent/tools/delegate_tool.py)
  - parent context only sees delegation summary, not child intermediate activity
- [`../hermes-agent/gateway/platforms/api_server.py`](../hermes-agent/gateway/platforms/api_server.py)
  - live SSE event flow for `tool_call`, `tool_output`, `tool_progress`, `meta`, `run_state`

### Real Session Examples To Use During Implementation

- [`../sessions/session_20260413_151048_d066f3.json`](../sessions/session_20260413_151048_d066f3.json)
  - fallback/retry chain and parallel batches
- [`../sessions/session_20260413_155007_79c0f3.json`](../sessions/session_20260413_155007_79c0f3.json)
  - two fan-out waves of failed web searches
- [`../sessions/session_cron_6447dcafd1e6_20260413_155337.json`](../sessions/session_cron_6447dcafd1e6_20260413_155337.json)
  - large cron build wrapper session
- [`../sessions/session_cron_6447dcafd1e6_20260413_155337_review_0b7b15.json`](../sessions/session_cron_6447dcafd1e6_20260413_155337_review_0b7b15.json)
  - related review session that should feel linked, not detached
- [`../sessions/session_20260410_160211_d99294.json`](../sessions/session_20260410_160211_d99294.json)
  - abrupt-looking delegated run
- [`../sessions/request_dump_20260410_160211_d99294_20260410_161112_606977.json`](../sessions/request_dump_20260410_160211_d99294_20260410_161112_606977.json)
  - related diagnostic artifact that should be attached to the owning session

## Findings That Must Drive The Design

### 1. Live and historical rendering are currently different systems

- live chat uses streamed SSE events and richer transient nesting
- historical session hydration rebuilds a much flatter conversation model

Consequence:

- the same run looks different before and after reload

### 2. Historical hydration flattens tool activity too aggressively

`buildConversationFromSessionData()` currently:

- turns assistant rows into assistant messages with `tools`
- tries to attach later tool rows by `tool_call_id`
- emits synthetic assistant messages for unmatched tool outputs

Consequence:

- tool outputs can appear detached from the assistant step that caused them
- ordering feels wrong even when raw storage is technically ordered

### 3. Child/background work is not inline in the main transcript

Current dashboard behavior:

- child sessions are summarized separately in `children` and `background_reviews`
- they are not part of the main transcript graph

Consequence:

- nested work feels missing
- chronology feels broken

### 4. Persisted tool-call data is not fully reliable for reconstruction

`run_agent.py` currently has a path that stores tool calls as simplified objects with only:

- `name`
- `arguments`

without preserving canonical call ids.

Consequence:

- historical matching of tool outputs to tool calls can fail

### 5. Delegate/subagent activity is mostly transient

`delegate_tool.py` explicitly keeps child intermediate activity out of the parent context.

Consequence:

- the dashboard cannot fully reconstruct nested delegate internals from stored session rows alone

## Design Requirements

### Transcript Model

The UI should render from one normalized execution structure for both live and historical views.

Suggested node types:

- `user_message`
- `assistant_step`
- `assistant_content`
- `tool_run`
- `tool_progress`
- `child_session`
- `parallel_group`
- `diagnostic_artifact`

Each node should have:

- `node_id`
- `session_id`
- `kind`
- `timestamp`
- `sort_key`
- `parent_node_id`
- `call_id` when relevant
- `label`
- `payload`

### Anchorability

Every renderable node needs a stable DOM id, for example:

- `message-<id>`
- `tool-<call_id>`
- `child-session-<session_id>`
- `artifact-<session_id>-<slug>`

Status/update items must carry target references to these nodes.

### Navigation Behavior

When a user clicks an update/status reference, the dashboard should:

1. navigate to the correct session detail page if needed
2. expand all collapsed ancestors
3. scroll the target node into view
4. apply a brief highlight pulse to the destination

### Parallel Batches

If one assistant turn emits multiple tool calls, they must render as a grouped batch, not independent floating rows.

Examples:

- `Search wave 1: 5 parallel calls`
- `Read batch: 4 files`

### Child Session Treatment

Child sessions and background reviews should render as inline stages in the parent session detail view, while remaining inspectable individually.

Examples:

- `Spawned review session`
- `Background build stage`
- `Delegated sub-run`

## Implementation Plan

### Phase 1: Frontend Trace Normalization

Create a normalized execution-node builder in the dashboard frontend.

Tasks:

1. Add a normalization layer in `templates/index.html` that converts both:
   - hydrated session payloads
   - live SSE events
   into a shared `ExecutionNode[]` graph/tree
2. Make assistant rows become `assistant_step` containers rather than plain chat bubbles with ad hoc tool arrays
3. Attach matched tool rows under their originating assistant step
4. Mark unmatched tool outputs as explicit orphan diagnostics instead of fake assistant messages
5. Preserve array order of tool calls as sibling order under the same assistant step

Why this solves the problem:

- fixes detached tool output rendering
- makes steps readable as coherent units
- creates a foundation for click-to-jump and child-stage linking

### Phase 1A: Anchor And Deep-Link Support

Tasks:

1. Add stable DOM ids to transcript nodes
2. Add a transcript index map from logical target ids to DOM ids
3. Extend routing to support deep links like:
   - `#/sessions/detail/<sessionId>/tool/<callId>`
   - `#/sessions/detail/<sessionId>/child/<childSessionId>`
4. Add `scrollToExecutionNode(target)` helper:
   - expand ancestors
   - `scrollIntoView`
   - temporary highlight
5. Make status/update pills clickable and route to the target node

Why this solves the problem:

- directly addresses the request that updates reference the place in the nested execution they describe

### Phase 1B: Inline Child-Run Rendering

Tasks:

1. Use `children` and `background_reviews` from `/api/sessions/{id}` as inline execution stages in the parent detail transcript
2. Render child sessions as collapsed inline blocks with:
   - title/session id
   - summary
   - timestamp
   - link to open focused child session view
3. Add click targets from side summaries into the inline transcript stage
4. Where request dumps or similar related artifacts exist, show them as diagnostics attached to the relevant session view

Why this solves the problem:

- nested work becomes visible in-context instead of hidden in side panels

### Phase 1C: Parallel Batch Visualization

Tasks:

1. Detect assistant turns with multiple tool calls and render them as `parallel_group`
2. Label the group based on tool names or count
3. Support expansion/collapse of the group while preserving per-call detail
4. Use the example sessions above to validate search waves and read batches

Why this solves the problem:

- makes concurrency look intentional rather than chaotic or out of order

## Phase 2: Backend Payload Improvements

Implement only after Phase 1 is stable.

Tasks:

1. Fix persisted tool-call serialization in `../hermes-agent/run_agent.py` so canonical ids are preserved
2. Ensure dashboard payloads include enough linkage metadata to build stable node ids
3. Normalize ordering to use deterministic sort keys wherever possible
4. Make related artifacts discoverable from the dashboard backend

Why this matters:

- improves historical reconstruction quality
- reduces orphan-tool edge cases

## Phase 3: Event Log Persistence

This is the long-term correct model.

Suggested new storage concepts:

- `session_events`
- `tool_runs`
- `subagent_runs`
- monotonic `seq` per session

This phase should not block Phase 1, but the Phase 1 code should be designed so it can consume richer event data later without a rewrite.

## Testing Requirements

### Dashboard UI Validation

Use the example session files listed above to verify:

- assistant/tool grouping is stable after reload
- parallel waves render as grouped batches
- child sessions show inline in parent detail view
- clicking a status/update pill scrolls to the correct nested node
- unmatched tool output is explicitly labeled, not silently merged into an unrelated area

### Runtime/Backend Validation

Relevant code paths:

- [`../hermes-agent/run_agent.py`](../hermes-agent/run_agent.py)
- [`../hermes-agent/gateway/platforms/api_server.py`](../hermes-agent/gateway/platforms/api_server.py)
- [`app.py`](app.py)

At minimum, add targeted tests covering:

- session payload ordering
- child-session stage inclusion
- canonical tool-call id preservation once backend changes are made

### Regression Checks

Do not regress:

- current live streaming behavior
- current session detail loading
- current file-activity panels
- existing deep-link behavior for session detail pages

## Acceptance Criteria

The work is complete when:

1. A complex session with multiple tool batches no longer reads like random flat noise.
2. Child/background work is visible in the session detail flow, not only side panels.
3. Clicking a status/update item reliably jumps to the exact relevant transcript/tool area.
4. Live and historical rendering are meaningfully aligned.
5. Example sessions above are easier to understand without having to inspect raw JSON.

## Constraints

- prefer the smallest correct incremental changes first
- do not attempt full event-log persistence in the same first pass unless clearly isolated and safe
- do not break the current dashboard session list or chat send flow
- keep implementation grounded in the currently served dashboard at `/home/mojo/.hermes/dashboard`

## Suggested Implementation Order For The Next Agent

1. Read this file and inspect the linked source files
2. Use subagents to divide:
   - frontend trace normalization
   - backend session payload review
   - artifact-based validation against real sessions
3. Implement Phase 1 first
4. Validate against the example sessions
5. Only then decide whether a safe subset of Phase 2 should be included in the same change
