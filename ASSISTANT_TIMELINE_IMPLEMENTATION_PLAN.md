# Assistant Timeline Implementation Plan

## Goal

Implement the full assistant execution timeline fix in the dashboard so assistant answers render in the actual order they occurred relative to tool calls, tool outputs, and follow-up assistant text.

This replaces the current single merged assistant content model with an ordered timeline model shared by both:

- live SSE rendering
- historical session hydration

## Problem Summary

The current reducer-like assistant trace model still stores assistant content as one merged string. That loses interleaving.

Current failure mode:

- assistant emits intro text
- assistant issues one or more tool calls
- tool outputs arrive
- assistant emits final answer text

The dashboard cannot faithfully represent that sequence because content is reconstructed as one block and then rendered before or after tools using heuristics.

The real fix is to preserve ordered timeline items within a single assistant step.

## Implementation Plan

### 1. Inspect the current assistant trace flow

Focus on these functions in `templates/index.html`:

- `createAssistantTraceState()`
- `reduceAssistantTraceEvent()`
- `buildAssistantEventsFromTraceState()`
- `normalizeAssistantMessage()`
- `buildHistoricalExecutionTrace()`
- `buildAssistantMessageFromTraceNode()`
- `persistActiveAssistantState()`
- `finalizeActiveRun()`
- `streamChatRun()`

Also read:

- `CHAT_VIEW_EXECUTION_TRACE_PLAN.md`

### 2. Replace merged assistant content with an ordered timeline model

Target trace shape:

```js
trace: {
  sessionId,
  stepNode,
  items: [],
  toolIndexByCallId: {},
  orphanNodes: [],
  pendingDelegateChildren: {},
  toolSequence: 0,
  orphanSequence: 0,
}
```

Each `items` entry should be one of:

- `content`
- `tool`
- `diagnostic`

### 3. Make the reducer preserve actual event order

Reducer rules:

- `content`
  - append text to the last content item if it is adjacent content
  - otherwise create a new content item
- `tool_call`
  - append a tool item at the current point in the timeline
  - index it by canonical `call_id`
- `tool_output`
  - update the matching tool item in place by `call_id`
- `tool_progress`
  - update the matching tool item in place by `call_id`
- `diagnostic`
  - append at the point it occurred
- unmatched `tool_output` / `tool_progress`
  - keep explicit orphan diagnostics

### 4. Stop reconstructing order from merged state

`buildAssistantEventsFromTraceState()` should map `trace.items` directly instead of synthesizing ordering from:

- one merged `content`
- one list of `toolNodes`

The renderer should consume timeline order directly.

### 5. Update historical hydration to use the same timeline reducer semantics

Historical sessions should replay into the same ordered model used by live streaming.

Expected flow:

- assistant message text becomes one or more content timeline items
- assistant `tool_calls` become tool items in array order
- subsequent tool rows update those items by `tool_call_id`

### 6. Update active-run persistence and resume

`persistActiveAssistantState()` and resume hydration must preserve the ordered timeline state.

At minimum, persisted assistant state should preserve enough information to rebuild:

- `trace.items`
- tool lookup state by canonical `call_id`
- orphan diagnostics

Reloading mid-run should not collapse interleaving.

### 7. Preserve existing behavior that must not regress

Keep working:

- deep-link behavior for tool, child, and artifact nodes
- scoped DOM ids for floating session panels
- inline child/background review rendering
- parallel tool grouping
- orphan diagnostics for truly unmatched outputs

### 8. Add focused regression coverage

Add tests for:

- content -> tools -> content
- intro text -> parallel tools -> final answer
- multiple tool waves inside one assistant step
- resume mid-run from persisted active state
- unmatched output remains orphaned only when truly unmatched

### 9. Validate against real sessions and existing tests

At minimum run:

```bash
python3 -m unittest tests.test_execution_trace_payloads
```

Also do targeted sanity checks against the sample sessions named in `CHAT_VIEW_EXECUTION_TRACE_PLAN.md`.

### 10. Keep changes minimal but complete

- Prefer additive conversion inside the current reducer architecture
- Avoid broad rewrites if the timeline model can be introduced cleanly
- Do not touch backend/runtime code unless the dashboard implementation proves it is necessary

## Prompt For The Next Agent

```text
Implement the full assistant execution timeline fix in `/home/mojo/.hermes/dashboard` so assistant answers render in the actual order they occurred relative to tool calls and tool outputs.

Context:
- The current dashboard uses a reducer-like assistant trace model, but it still stores assistant content as one merged string.
- A minimal `contentOrder` fix was added, but that is not enough.
- The real fix is to preserve ordered interleaving inside a single assistant step.
- Current symptom: when the bot streams text after tool calls, chat still cannot faithfully represent multiple content segments around tool activity.

Primary goal:
Replace the single merged assistant content model with an ordered timeline model for each assistant step, shared by both live SSE rendering and historical session hydration.

Required architecture:
- Work in `dashboard/templates/index.html`
- Use a timeline shape inside assistant trace state, something like:
  - `trace.items: []`
  - `trace.toolIndexByCallId: {}`
- Timeline items should represent:
  - content
  - tool
  - diagnostic
- Preserve exact event order within one assistant step

Implementation requirements:
1. Read `/home/mojo/.hermes/dashboard/CHAT_VIEW_EXECUTION_TRACE_PLAN.md` first.
2. Use subagents aggressively before and during implementation:
   - one frontend explore subagent to inspect current reducer/render/hydration flow
   - one explore subagent to inspect real session payloads and confirm ordering expectations
   - optionally one general/explore subagent at the end for a quick regression review
3. Do not do a giant rewrite if a contained conversion inside the current reducer model is enough.
4. Preserve:
   - deep-link behavior
   - scoped DOM ids for floating session panels
   - inline child/background review rendering
   - parallel tool grouping
   - explicit orphan diagnostics for truly unmatched outputs
5. Keep the smallest correct change, but do the full timeline conversion, not another ordering flag workaround.

Concrete code targets to inspect:
- `createAssistantTraceState()`
- `reduceAssistantTraceEvent()`
- `buildAssistantEventsFromTraceState()`
- `normalizeAssistantMessage()`
- `buildHistoricalExecutionTrace()`
- `buildAssistantMessageFromTraceNode()`
- `persistActiveAssistantState()`
- `finalizeActiveRun()`
- `streamChatRun()`

Desired behavior:
- If the assistant emits intro text, then tools, then conclusion text, chat should show:
  - intro text
  - tool block(s)
  - conclusion text
- If the assistant emits multiple tool waves inside one step, preserve that order.
- If a run is resumed from persisted active state, preserve the ordering.
- Historical hydration should follow the same reducer semantics as live streaming.

Testing requirements:
- Add focused regression coverage for:
  - content -> tools -> content
  - parallel tools -> final answer
  - multiple tool waves in one assistant step
  - resume mid-run from persisted active state
  - unmatched output remains orphaned only when truly unmatched
- Run:
  - `python3 -m unittest tests.test_execution_trace_payloads`
- Perform at least a targeted sanity check against the sample sessions named in the plan file.

Important constraints:
- There may be unrelated local modifications in the repo. Do not overwrite or revert them.
- Use `apply_patch` for file edits.
- Prefer additive/minimal structural changes over broad rewrites.
- Do not touch backend/runtime code unless the dashboard implementation proves it is necessary.

Expected final report:
- what changed
- which functions were materially refactored
- how the timeline model works
- what tests/verification were run
- whether any residual limitations remain
- whether anything was intentionally deferred

Start by reading the plan file and launching the two subagents.
```
