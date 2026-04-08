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

Then open:

```text
http://127.0.0.1:8081
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
