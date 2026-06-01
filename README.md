# Hermes Dashboard

Standalone web dashboard for the Hermes AI agent runtime.

This repo packages the Hermes dashboard UI as a reusable standalone project for people who already have a working Hermes install.

## One-Line Install

Paste this into a terminal:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/mojomast/hermesdashboard/main/install.sh)"
```

The installer is interactive. It will:

- clone or update `hermesdashboard` into `~/hermesdashboard` by default
- ask where your Hermes home, checkout, and virtualenv live
- detect whether you already have a Hermes API running
- configure the dashboard to either reuse that API or use the bundled API-only launcher
- generate local launcher scripts and a per-install API key
- run preflight checks for Python version, dashboard dependencies, and common path issues

If you are unsure what to enter for host and port, just press Enter to accept the recommended defaults:

- Hermes API: `127.0.0.1:8642`
- Dashboard: `127.0.0.1:8081`

If you want a different install location, set `HERMESDASHBOARD_DIR` first:

```sh
HERMESDASHBOARD_DIR="$HOME/tools/hermesdashboard" bash -c "$(curl -fsSL https://raw.githubusercontent.com/mojomast/hermesdashboard/main/install.sh)"
```

## Updating

See [`UPDATE.md`](UPDATE.md) for all update paths, including non-command-line options.

From the running dashboard, click the gear button in the header and choose **Update Instructions**. The dashboard explains GitHub Desktop/Git GUI updates, Download ZIP updates, installer reruns, and terminal updates, then reminds you to restart and use **Reload Dashboard**.

## Quick Start

After installation:

```sh
cd ~/hermesdashboard
./run-api-server.sh
./run-dashboard.sh
```

Run those scripts as your normal user, not with `sudo`.

Then open:

```text
http://127.0.0.1:8081
```

## Accessing the Dashboard After Install

If a user asks "how do I open it?", the short answer is:

1. Go to your install directory, usually `~/hermesdashboard`
2. Start the launchers:

```sh
./run-api-server.sh
./run-dashboard.sh
```

3. Open the dashboard URL in a browser

Default local URL:

```text
http://127.0.0.1:8081
```

If you chose a different host or port during install, check `.env.local` in the repo directory.

Important values:

- `DASHBOARD_HOST`
- `DASHBOARD_PORT`
- `HERMES_API`

Examples:

- if `DASHBOARD_HOST=127.0.0.1` and `DASHBOARD_PORT=8081`, open `http://127.0.0.1:8081`
- if `DASHBOARD_HOST=0.0.0.0` and `DASHBOARD_PORT=8081`, open `http://localhost:8081` on the same machine
- if the dashboard is bound externally on another machine, open `http://<that-machine-ip>:<DASHBOARD_PORT>` from your browser

Quick check:

```sh
curl -s http://127.0.0.1:8081/api/status
```

If that returns JSON, the dashboard is running and reachable.

If your Hermes install already provides an API server, you can skip the bundled launcher and point the dashboard at it with `HERMES_API`.

In that mode, `./run-api-server.sh` becomes a helper that reminds you the dashboard is reusing your existing Hermes API.

If you see `Permission denied` when starting the dashboard, the most likely cause is that `start.sh` is not executable. Fix it with:

```sh
chmod +x ./start.sh ./run-dashboard.sh ./run-api-server.sh
```

## Auto-Start

On Linux, the installer can ask whether you want Hermes Dashboard and the Hermes API-only server to start automatically when you log in.

If you say yes, it will:

- generate user-level `systemd` services
- try to enable and start them automatically

On non-Linux systems, the installer currently falls back to manual startup and tells the user to use:

- `./run-api-server.sh`
- `./run-dashboard.sh`

## What You Get

- streaming Hermes chat UI
- compact single-line tool activity rows with on-demand drill-down panels
- load-time chat banner that shows when Hermes still has an in-flight run after refresh
- explicit `Reattach Session` and `Resume Stream` actions for persisted in-progress chat runs
- sessions browser and session detail viewer
- memory, skills, secrets, and config panels
- expanded config editor with sectioned settings and advanced JSON editors
- graph visualization for sessions, files, tools, models, and skills
- persisted graph display settings for labels, spacing, edges, motion, and panel sizing
- delegated task streaming inside expanded `delegate_task` blocks
- **live subagent drawer** — click "Live view" on any `delegate_task` block to open a real-time floating panel showing the child session's activity
- session summaries in sessions, graph, and session detail
- **token & cost accounting** — per-session token usage badge and step-by-step cost breakdown
- **session search & filter** — full-text search across sessions with status, date range, and real-time filtering
- **cron schedule viewer** — dedicated Schedule tab showing cron jobs with run history, next-run countdowns, and session links
- **interrupt/pause live runs** — pause button for in-flight chat runs, queues an interrupt before the next tool call
- **Cmd+K command palette** — keyboard-driven command palette for quick navigation and recent session access
- **threaded Message Board** — forum-style threads with persistent posts, per-thread replies, and Hermes responses scoped to each thread's own context
- hardened dashboard-to-Hermes streaming bridge for long tool-heavy runs, including tool progress forwarding, heartbeats, clean disconnect handling, and sanitized chat history

## Message Board

The Message Board tab provides forum-style threads for working with Hermes outside the main chat transcript.

Each thread behaves like its own conversation window:

- create a thread with a title and first post
- Hermes replies inside that thread
- reply again with `Post only` or `Post + ask Hermes`
- Hermes receives the ordered messages from that thread as context, not unrelated dashboard chat history
- threads and replies persist in `~/.hermes/dashboard_message_board.sqlite3`

This makes it useful for durable work queues, design discussions, self-improvement notes, and future subagent collaboration. The storage model already separates author and role so additional contributors can be added later without changing the thread concept.

Relevant endpoints:

- `GET /api/message-board` — list threads
- `POST /api/message-board` — create a thread and request the first Hermes reply
- `GET /api/message-board/{post_id}` — fetch one thread with messages
- `POST /api/message-board/{post_id}/messages` — add a thread reply, optionally asking Hermes to respond

## Streaming Reliability

The dashboard chat bridge is designed to preserve the entire Hermes run stream instead of dropping after the first tool event.

Current behavior:

- forwards Hermes `hermes.tool.progress` SSE events into dashboard `tool_progress` events
- forwards streamed content and usage metadata incrementally
- sends heartbeats while long tools are quiet so browsers and proxies keep the stream open
- cleans stale dashboard transport errors and UI-only trace metadata before sending history back to Hermes
- uses a synchronous upstream SSE reader in a worker thread to avoid premature async stream closure seen with long tool-heavy runs
- stores resumable run state so refreshes can reattach or resume explicitly

## Upstream Compatibility

This repo is intended to work with upstream Hermes installs, not just local forks.

Compatibility notes:

- the dashboard no longer requires `agent.session_summarizer` from the Hermes runtime
- session summary backfill/regeneration endpoints now fall back to dashboard-local summary generation using `state.db`
- config/env metadata features use local fallbacks when optional Hermes CLI internals are unavailable
- if your Hermes install does not expose the bundled API-only launcher internals, use your existing Hermes API and set `HERMES_API`


## Architecture and Refactor Status

Hermes Dashboard is being decomposed with vocabulary-first bounded contexts while preserving public behavior. The current dependency direction is:

```text
app.py bootstrap / route table
  -> dashboard_backend/routes/* request wrappers (dashboard-state extracted; broader contexts gradual)
  -> dashboard_backend/services/* bounded-context services
  -> dashboard_backend/core/* shared path/config/response helpers (planned)
```

During this refactor, `app.py` remains the Starlette bootstrap, route registry, and compatibility-wrapper owner. Services must not import `app.py`; app-owned mutable dependencies such as `HERMES_HOME`, database paths, locks, and runtime config are passed into services at call time so tests and local callers that monkeypatch app symbols keep working.

Extracted backend modules so far:

- `dashboard_backend/services/dashboard_state.py` owns SQLite persistence for browser/dashboard state projections; `dashboard_backend/routes/dashboard_state.py` owns request parsing/JSON envelopes for `GET`/`PUT`/`DELETE /api/dashboard-state/{key}`; `app.py` keeps `_load_dashboard_state`, `_save_dashboard_state`, `_delete_dashboard_state`, related private wrappers, and app-level endpoint names for route-table/monkeypatch compatibility.
- `dashboard_backend/services/token_usage.py` owns read-only token/cost aggregation ledgers and projections; `/api/token-usage` and app-level helper names remain stable.
- `dashboard_backend/services/message_board.py` owns message-board SQLite post/message persistence; `/api/message-board*` route handlers and Hermes reply generation remain in `app.py` for compatibility.
- `dashboard_backend/services/scrolls.py` owns read-only Scrolls snapshot projection delegation; `GET /api/scrolls/snapshot` remains wrapped in `app.py` and injects the configured Vesuvius project root at call time.
- `dashboard_backend/services/games_catalog.py` owns read-only Games tab skill catalog/frontmatter projection; `/api/games` remains wrapped in `app.py` and injects `HERMES_HOME` at call time while game proxy/process routes stay in the app orchestrator.
- Self-improvement event-coverage repair/anomaly projections are read-only and test-covered; repair commands render as inert operator guidance while self-improvement/autonomous-development tabs remain hidden-by-default until shipping gates pass.

Refactor passes follow `AUDIT -> MAP -> EXTRACT -> VERIFY -> DOCUMENT -> COMMIT`. For backend extraction passes, run the focused context tests first, then the full gate:

```sh
python -m py_compile app.py
node --check static/js/dashboard.js
python -m pytest
```

Compatibility contracts for the current refactor copy:

- Preserve public route paths and payload shapes.
- Preserve DOM IDs, CSS class names, tab IDs, and frontend behavior.
- Keep `static/js/dashboard.js` as a classic deferred compatibility script; do not switch to `type="module"` yet.
- Preserve global JavaScript functions while inline handlers still rely on them.
- Do not introduce npm/Vite/bundler requirements for these passes.

See [`docs/app-refactor-map.md`](docs/app-refactor-map.md) for the backend bounded-context map and [`docs/self-improvement-autonomous-shipping-plan.md`](docs/self-improvement-autonomous-shipping-plan.md) for safety gates before default-visible self-improvement/autonomous-development tabs.

## First-Run Verification

After the installer finishes, a healthy first run looks like this:

```sh
cd ~/hermesdashboard
./run-api-server.sh
curl -s http://127.0.0.1:8642/health
./run-dashboard.sh
curl -s http://127.0.0.1:8081/api/status
```

Then open `http://127.0.0.1:8081` in your browser.

If you forgot which port was selected during install, open `~/hermesdashboard/.env.local` and look for `DASHBOARD_PORT`.

## Expanded Config Surface

The Config tab is backed by `GET /api/settings` and is no longer limited to a few basic controls.

Current sections:

- `Model & Routing`
- `Agent & Personality`
- `Memory & Session`
- `Tools & Skills`
- `Browser / Web / Voice`
- `Display & UX`
- `Advanced Admin`

Highlights:

- normalized effective config plus raw config are returned together for safer rendering
- complex nested groups use JSON editors instead of lossy field-by-field forms
- custom personalities are stored at `agent.personalities`
- `platform_toolsets` preserves custom non-configurable entries such as MCP server names
- larger memory defaults are surfaced cleanly in Config: `memory.memory_char_limit=22000` and `memory.user_char_limit=13750`

## Sessions UX

The dashboard session experience is designed to be more scannable and more debuggable.

- session titles now come from the same transcript-based local metadata extraction path used for session summaries
- missing titles and summaries can be backfilled automatically through the dashboard maintenance endpoints
- the dashboard also runs a small startup maintenance pass to repair older missing titles/summaries automatically
- graph session nodes now fall back to summary-derived labels when a stored title is still missing
- graph edges connect sessions to skills when persisted `skill_manage` activity shows a skill was used
- graph floating session panels render assistant/tool activity in transcript order instead of separating tool calls from tool results
- graph display settings persist in the browser for label density, font sizing, node scale, spacing, edge visibility, edge types, motion mode, and panel sizing
- session detail now includes stored metadata such as model, timing, lineage, tokens, and cost
- assistant messages can show persisted reasoning/debug fields when Hermes recorded them
- session detail and live chat now share the same assistant-step trace reduction model for content, tool runs, and orphan diagnostics
- session detail now normalizes assistant steps, tool runs, child sessions, and request-dump diagnostics into one execution-style transcript view
- multi-tool assistant turns render as grouped parallel batches instead of detached flat tool rows
- unmatched live or historical tool outputs stay explicit as diagnostics instead of being guessed onto another tool by name
- background review, skill-change, and session-search activity can deep-link back into the owning transcript location when linkage exists
- child sessions and related request-dump artifacts render inline in the parent session detail flow while remaining inspectable separately
- floating session panels now scope transcript DOM ids so deep-link targets stay aligned with the main session detail view instead of colliding with graph popouts
- the Sessions panel can attach Chat to an existing session via `Use in Chat`, loading the persisted session transcript into Chat
- when the dashboard reloads during an active streamed response, Chat now surfaces the saved run state in a banner instead of silently resuming in the background
- the active-run banner can reattach the saved session transcript into Chat without discarding the in-flight run metadata
- the active-run banner can also explicitly resume the saved live stream from the last cached event offset
- summary regeneration refreshes both title and summary through dashboard-local metadata recomputation

## Live Subagent Drawer

When Hermes spawns a child session via `delegate_task`, the dashboard shows a **"Live view"** button on the tool block.

Clicking it opens a floating drawer that:

- shows the child session's live transcript in real time
- streams new child activity via SSE as the subagent works
- badges the child status as LIVE, DONE, or ERROR
- stays open across chat re-renders (uses `position: fixed`)
- can be closed with the × button

**How it works:**

1. The agent emits a `child_session_started` event via `tool_progress_callback` when a subagent is spawned
2. The dashboard frontend captures this over SSE and stores the child session mapping
3. The "Live view" button appears on the `delegate_task` block
4. Clicking it fetches the child session detail and opens an SSE stream for live updates
5. The drawer renders the same execution trace as the main session view

**Backend requirements:**

- The agent must emit `child_session_started` events (supported in recent Hermes versions)
- Child sessions must have a valid `session_id` and `delegate_call_id`
- The dashboard `/api/sessions/{id}/stream` endpoint provides the SSE feed

## Secrets Tab

The Secrets tab is metadata-driven from Hermes env metadata instead of a short hardcoded dashboard-only list.

That means the standalone dashboard can show:

- richer provider and tool coverage
- descriptions and category labels for known secrets
- detected unknown API keys, tokens, secrets, and `_URL` values as advanced entries

## Important

This is not a full standalone Hermes runtime.

It depends on an existing Hermes install for:

- the Hermes runtime modules
- the Hermes home directory and `state.db`
- config, memories, skills, and environment secrets

## Docs

- [Setup Guide](SETUP.md)
- [Operations Guide](OPERATIONS.md)
- [Implementation Notes](IMPLEMENTATION.md)
- [Backend Refactor Map](docs/app-refactor-map.md)
- [Frontend/General Refactor Map](docs/refactor-map.md)
- [Self-Improvement / Autonomous Development Shipping Plan](docs/self-improvement-autonomous-shipping-plan.md)
- [Contributing Guide](CONTRIBUTING.md)

## Contributing

Contributions are welcome.

If you want to help build Hermes Dashboard:

- check the open issues and pick something small or well-scoped
- discuss bigger changes before starting them
- test your changes locally before opening a pull request
- update docs when behavior or setup changes

Start here:

- [Contributing Guide](CONTRIBUTING.md)

## Repository

- Public repo: `https://github.com/mojomast/hermesdashboard`
