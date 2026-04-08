# Hermes Dashboard

Standalone web dashboard for the Hermes AI agent runtime.

This repo packages the Hermes dashboard UI as a reusable standalone project for people who already have a working Hermes install.

## One-Line Install

Paste this into a terminal:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/mojomast/hermesdashboard/main/install.sh)"
```

The installer is interactive and writes local launcher scripts for your Hermes paths.

If you are unsure what to enter for host and port, just press Enter to accept the recommended defaults:

- Hermes API: `127.0.0.1:8642`
- Dashboard: `0.0.0.0:8081`

## Quick Start

After installation:

```sh
cd /path/to/hermesdashboard
./run-api-server.sh
./run-dashboard.sh
```

Run those scripts as your normal user, not with `sudo`.

Then open:

```text
http://127.0.0.1:8081
```

If your Hermes install already provides an API server, you can skip the bundled launcher and point the dashboard at it with `HERMES_API`.

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
- delegated task streaming inside expanded `delegate_task` blocks
- session summaries in sessions, graph, and session detail

## Upstream Compatibility

This repo is intended to work with upstream Hermes installs, not just local forks.

Compatibility notes:

- the dashboard no longer requires `agent.session_summarizer` from the Hermes runtime
- session summary backfill/regeneration endpoints now fall back to dashboard-local summary generation using `state.db`
- config/env metadata features use local fallbacks when optional Hermes CLI internals are unavailable
- if your Hermes install does not expose the bundled API-only launcher internals, use your existing Hermes API and set `HERMES_API`

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

- session titles now come from the same transcript-based summarization path used for session summaries in Hermes
- session detail now includes stored metadata such as model, timing, lineage, tokens, and cost
- assistant messages can show persisted reasoning/debug fields when Hermes recorded them

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

## Repository

- Public repo: `https://github.com/mojomast/hermesdashboard`
