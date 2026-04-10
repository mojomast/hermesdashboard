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
- sessions browser and session detail viewer
- memory, skills, secrets, and config panels
- expanded config editor with sectioned settings and advanced JSON editors
- graph visualization for sessions, files, tools, models, and skills
- persisted graph display settings for labels, spacing, edges, motion, and panel sizing
- delegated task streaming inside expanded `delegate_task` blocks
- session summaries in sessions, graph, and session detail

## Upstream Compatibility

This repo is intended to work with upstream Hermes installs, not just local forks.

Compatibility notes:

- the dashboard no longer requires `agent.session_summarizer` from the Hermes runtime
- session summary backfill/regeneration endpoints now fall back to dashboard-local summary generation using `state.db`
- config/env metadata features use local fallbacks when optional Hermes CLI internals are unavailable
- if your Hermes install does not expose the bundled API-only launcher internals, use your existing Hermes API and set `HERMES_API`

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
- the Sessions panel can attach Chat to an existing session via `Use in Chat`, loading the persisted session transcript into Chat
- summary regeneration refreshes both title and summary through dashboard-local metadata recomputation

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
