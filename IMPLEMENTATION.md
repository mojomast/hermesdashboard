# Implementation Notes

This repo is a standalone packaging of the Hermes dashboard, but it is not a full standalone Hermes runtime.

It depends on an existing Hermes install for:

- runtime modules under `hermes-agent`
- the Hermes home directory and `state.db`
- memories, skills, config, and environment secrets

## Installer Flow

`install.sh` is designed to be curl-able and interactive.

It asks the user for:

- `HERMES_HOME`
- `HERMES_AGENT_PATH`
- `HERMES_VENV`
- API host and port
- dashboard host and port
- `API_SERVER_KEY`

Then it writes:

- `.env.local`
- `run-api-server.sh`
- `run-dashboard.sh`
- optional `start-background.sh`

Those generated files are intentionally ignored by git so each user can keep a local setup.

Optional generated files:

- `~/.config/systemd/user/hermes-dashboard-api.service`
- `~/.config/systemd/user/hermes-dashboard-web.service`
- `Dockerfile`
- `docker-compose.yml`

## Public Reuse

When changing the dashboard for outside users, prefer:

- environment variables over hardcoded local paths
- launcher scripts over manual multi-command setup
- repo-local generated config files instead of editing tracked source files

## Installer UX Goals

The installer should stay:

- curl-able as a one-line setup path
- interactive, with sensible defaults
- path-driven instead of forcing one repo layout
- explicit about the fact that Docker support is only for the dashboard web wrapper, not the Hermes runtime itself
- goal-oriented in prompts, e.g. `Auto-start on login?` instead of asking users whether they want raw `systemd` unit generation

## Required Runtime Surface

The standalone dashboard expects these pieces from Hermes:

- `hermes_constants`
- `hermes_cli.config`
- `hermes_cli.skin_engine`
- `hermes_cli.tools_config`

Only some of those are hard dependencies now.

- `hermes_constants` is used when available, but the dashboard has a local `HERMES_HOME` fallback
- `hermes_cli.config`, `hermes_cli.skin_engine`, and `hermes_cli.tools_config` are used when available, but the dashboard now has local fallbacks for config/env handling, skins, toolset metadata, and secret metadata
- `agent.session_summarizer` is no longer required; summary regeneration/backfill is implemented locally in the dashboard repo
- `gateway.platforms.api_server` is only needed if the user wants to use `run_api_server_only.py`

If the upstream Hermes runtime changes those import paths, the fallback behavior should keep the dashboard usable. The bundled API-only launcher remains the most fragile integration point.

## Config API Surface

The standalone package now depends on the richer dashboard config surface from `app.py`:

- `GET /api/config` returns raw persisted YAML
- `GET /api/settings` returns the dashboard-oriented settings payload used by the Config tab
- `POST /api/config` accepts dotted-path updates back into raw config

`GET /api/settings` includes:

- overview stats
- normalized model metadata
- built-in and custom personalities
- skin metadata
- configurable toolsets and platform metadata
- platform toolset extras that must be preserved on save
- metadata-driven secret coverage

The frontend assumes the Config tab is rendered dynamically after `loadSettings()`. Static references to config DOM nodes before that render are unsafe.

The dashboard also assumes newer Hermes runtime behavior for sessions:

- larger persistent memory defaults (`memory.memory_char_limit=22000`, `memory.user_char_limit=13750`)
- transcript-based local title generation aligned with session summaries
- local session maintenance endpoints backfill both missing titles and missing summaries for older rows in `state.db`
- richer session detail fields in `GET /api/sessions/{id}` including timing, token, cost, lineage, and reasoning/debug metadata
- `POST /api/sessions/{id}/summary` now refreshes both title and summary from persisted transcript data without depending on the Hermes runtime summarizer
- graph session panels merge assistant content, tool calls, and tool outputs into transcript order before rendering
- graph display settings are stored in browser localStorage so graph layout and panel sizing preferences survive reloads

## Execution Trace Rendering

The dashboard now has a Phase 1 execution-trace normalization path in `templates/index.html`.

Current behavior:

- historical session detail, floating session views, and live chat assistant rendering now share one reducer-style assistant trace model
- persisted rows replay through the same assistant-step reduction path used by live SSE events instead of maintaining a separate historical event builder
- multi-tool assistant turns render as explicit grouped batches so parallel waves stay visually coherent
- live chat tool calls render as compact single-line rows with lazy `Input`, `Output`, `Metrics`, and `Raw` drill-down panels
- unmatched persisted and live tool rows render as orphan diagnostics instead of fake assistant messages or name-matched fallback attachments
- child sessions and related request-dump artifacts are attached inline in the parent session detail view
- side-panel activity items can deep-link into the normalized transcript when the backend can derive a target
- floating session transcript renderers scope DOM ids to avoid collisions with the main session-detail transcript
- **live subagent drawer**: child sessions discovered via SSE `child_session_started` events get a "Live view" button on their parent `delegate_task` block; clicking it opens a fixed-position drawer that streams child activity via SSE and survives chat re-renders

## Active Run Recovery

The chat frontend persists in-progress streaming runs in browser localStorage.

Current behavior:

- `ACTIVE_RUN_KEY` stores `runId`, `eventOffset`, `startedAt`, `sessionId`, and a reduced assistant state snapshot
- on reload, the dashboard now shows a visible chat banner when an in-flight run is still present instead of silently resuming immediately
- the banner summarizes the latest known tool/content activity and exposes `Stop main agent`, `Reattach Session`, and `Resume Stream`
- `Stop main agent` posts an emergency stop to `/api/sessions/{session_id}/interrupt` with `action: stop`, falling back to `/api/runs/{run_id}/stop` when a session id is not attached yet
- `Reattach Session` hydrates the persisted transcript for the saved `sessionId` into Chat while preserving the active run record
- `Resume Stream` reconnects `/chat` with `resume=true` and the stored `eventOffset`

Why it works this way:

- silent auto-resume after refresh made it hard to tell whether Hermes was still working
- explicit resume avoids clobbering chat DOM state while the user is trying to inspect or reattach the saved session transcript

Current backend additions in `app.py`:

- `POST /api/runs/{run_id}/stop` marks the active dashboard run stopped, cancels the task, sets the session interrupt flag when known, and appends `[DONE]`
- `_run_chat_stream_sync` cooperatively honors `stop_requested` while reading upstream SSE so a worker-thread stream can close promptly after the dashboard stop request
- `GET /api/sessions/{id}` now includes `related_artifacts` for `request_dump_<session_id>_*.json`
- synthesized `background_reviews`, `skill_events`, and `session_search_events` now include additive `target` metadata when a transcript destination can be inferred

Current runtime additions in `../hermes-agent`:

- persisted assistant tool-call rows now preserve canonical `id` and `call_id` in the object-style session flush path
- persisted tool result rows now include `tool_name` so dashboard reconstruction can recover linkage when assistant-side ids are sparse
- delegated child summaries now include `delegate_call_id`, `child_session_id`, and per-tool `call_id` in `tool_trace`
- Responses API output extraction now prefers canonical tool-call ids over composite `call|fc` ids

## Live Subagent Drawer

The live subagent drawer lets users inspect child agent sessions in real time without leaving the parent chat context.

**Event flow:**

1. `delegate_tool.py` emits `child_session_started` via `parent_agent.tool_progress_callback(name, preview, args)`
   - `args` includes: `child_session_id`, `parent_session_id`, `delegate_call_id`, `label`
   - The callback signature is `(name, preview, args)` — no keyword arguments
2. The gateway's `_on_tool_progress` in `api_server.py` forwards this as SSE with `type: "tool_progress"`, `name: "child_session_started"`, and `arguments: {...}`
3. The dashboard frontend receives this in `streamChatRun` and stores it in `liveChildSessionMap` keyed by `delegate_call_id`
4. When rendering a `delegate_task` tool block, `renderToolBlock` checks `liveChildSessionMap.get(tool.call_id)` and adds a "Live view" button if entries exist
5. Clicking the button calls `openChildSessionDrawer(childSessionId, anchorEl, label)` which:
   - creates a fixed-position drawer appended to `document.body`
   - fetches the child session detail via `/api/sessions/{id}`
   - renders the historical trace with `buildHistoricalExecutionTrace` + `renderSessionTranscript`
   - opens an SSE stream via `/api/sessions/{id}/stream` for live updates
   - badges the drawer as LIVE, DONE, or ERROR based on stream events
6. The drawer survives chat re-renders because it uses `position: fixed` and is outside the chat DOM subtree
7. `closeChildSessionDrawer` cleans up the drawer and its EventSource

**Backend endpoint:**

- `GET /api/sessions/{session_id}/stream` — returns an SSE stream
  - If the session is in `ACTIVE_RUNS`, it proxies the active run's event queue
  - Otherwise, it returns a single `run_state` completion event followed by `[DONE]`

**Important limitation:**

- child sessions spawned by the agent backend do not appear in `ACTIVE_RUNS` (only dashboard-initiated runs are tracked)
- this means the SSE stream falls back to immediate completion for most child sessions
- the drawer still shows historical data correctly, but true live streaming only works if the child session happens to be actively running when the drawer opens
- future work could add a polling fallback or a backend session-event endpoint for true live child session tracking

## Important limitation:

- this is still mostly a Phase 1 frontend-first model with a small additive Phase 2 persistence slice
- exact historical reconstruction still depends on persisted `tool_call_id` quality and does not yet have a first-class event log
- child/review linkage outside persisted `parent_session_id` still relies on current payload shape and has not become a full subagent event graph
- live SSE rendering and historical hydration are now aligned at the assistant-step reducer level, but not yet backed by a Phase 3 monotonic event store

## Auto-Start UX

Preferred installer behavior:

- ask the user whether they want the dashboard and API to auto-start on login
- on Linux with `systemctl`, generate user services and attempt to enable/start them immediately
- on non-Linux systems, explain that manual startup is currently the supported path from this installer

This keeps the prompt user-centered and avoids requiring familiarity with `systemd` to complete setup.
