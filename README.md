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

## What You Get

- streaming Hermes chat UI
- sessions browser and session detail viewer
- memory, skills, secrets, and config panels
- graph visualization for sessions, files, tools, models, and skills
- delegated task streaming inside expanded `delegate_task` blocks
- session summaries in sessions, graph, and session detail

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
