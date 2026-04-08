# Hermes Dashboard

Standalone web dashboard for the Hermes AI agent runtime.

This repository packages the Hermes dashboard UI and chat proxy so other people can run the same dashboard outside the main `mojomast/hermes` monorepo.

## One-Line Install

Paste this into a terminal:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/mojomast/hermesdashboard/main/install.sh)"
```

The installer is interactive and prompts for:

- your Hermes home directory
- your Hermes runtime path
- your Hermes venv path
- API host and port
- dashboard host and port
- dashboard API key

It then writes local launcher scripts so you can start the dashboard without manually re-entering paths.

## What It Includes

- streaming Hermes chat UI
- sessions browser and session detail viewer
- memory editor
- skills browser
- secrets editor
- config and model controls
- graph visualization of sessions, files, tools, models, and skills
- delegated task streaming inside expanded `delegate_task` tool blocks
- persisted session summaries in sessions, graph, and session detail

## Who This Is For

This repo is for people who already have a working Hermes runtime and want the dashboard as a standalone project.

You still need a Hermes agent install because this dashboard imports Hermes runtime modules like:

- `hermes_constants`
- `hermes_state`
- `gateway.platforms.api_server`
- `agent.session_summarizer`

## Architecture

The dashboard is split into two local services:

1. Dashboard web app on `8081`
2. Hermes API-only chat server on `8642`

The browser talks to the dashboard web app.
The dashboard web app proxies chat traffic to the Hermes API server.

## Repository Layout

- `app.py`: Starlette dashboard backend and `/chat` SSE proxy
- `templates/index.html`: single-file frontend
- `run_api_server_only.py`: launches only the Hermes API server needed for dashboard chat
- `start.sh`: convenience launcher for the dashboard web app
- `requirements.txt`: dashboard Python dependencies

## Requirements

- Linux or macOS shell environment
- Python 3.11+
- a working Hermes checkout/install
- Hermes virtualenv with the runtime dependencies available
- access to a Hermes home directory, usually `~/.hermes`

## Required Hermes Pieces

You need a Hermes runtime checkout somewhere on disk. By default this dashboard expects:

- Hermes home: `~/.hermes`
- Hermes runtime repo: `~/.hermes/hermes-agent`
- Hermes venv: `~/.hermes/hermes-agent/venv`

If your layout differs, set:

- `HERMES_HOME`
- `HERMES_AGENT_PATH`
- `HERMES_VENV`

## Install

1. Clone this repo, or use the one-line installer.
2. Create a Python environment for the dashboard, or reuse the Hermes venv.
3. Install dependencies if needed:

```sh
pip install -r requirements.txt
```

## Configuration

Useful environment variables:

- `HERMES_HOME`
- `HERMES_AGENT_PATH`
- `HERMES_VENV`
- `HERMES_API`
- `API_SERVER_HOST`
- `API_SERVER_PORT`
- `API_SERVER_KEY`
- `DASHBOARD_HOST`
- `DASHBOARD_PORT`

The dashboard also reads `~/.hermes/.env` if present.

That matters for features like:

- summary regeneration
- OpenRouter-backed session summaries
- any Hermes runtime secrets already configured in `.env`

## Run It

### 1. Start the Hermes API-only server

If you used the installer, this becomes:

```sh
./run-api-server.sh
```

```sh
cd /path/to/hermesdashboard

API_SERVER_ENABLED=true \
API_SERVER_HOST=127.0.0.1 \
API_SERVER_PORT=8642 \
API_SERVER_KEY=your-dashboard-api-key \
python run_api_server_only.py
```

If you use the Hermes venv directly:

```sh
cd /path/to/hermesdashboard

API_SERVER_ENABLED=true \
API_SERVER_HOST=127.0.0.1 \
API_SERVER_PORT=8642 \
API_SERVER_KEY=your-dashboard-api-key \
/path/to/hermes-agent/venv/bin/python run_api_server_only.py
```

### 2. Start the dashboard web app

If you used the installer, this becomes:

```sh
./run-dashboard.sh
```

```sh
cd /path/to/hermesdashboard
./start.sh
```

Or manually:

```sh
cd /path/to/hermesdashboard

HERMES_HOME="$HOME/.hermes" \
HERMES_AGENT_PATH="$HOME/.hermes/hermes-agent" \
HERMES_API="http://127.0.0.1:8642" \
DASHBOARD_PORT=8081 \
/path/to/hermes-agent/venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8081
```

### 3. Open the dashboard

```text
http://127.0.0.1:8081
```

## Production-ish Background Launch

If you used the installer and opted into launcher scripts:

```sh
./start-background.sh
```

Manual version:

```sh
nohup env \
  API_SERVER_ENABLED=true \
  API_SERVER_HOST=127.0.0.1 \
  API_SERVER_PORT=8642 \
  API_SERVER_KEY=your-dashboard-api-key \
  /path/to/hermes-agent/venv/bin/python run_api_server_only.py \
  >/tmp/hermes-api-only.log 2>&1 &

nohup sh -c 'set -a && . "$HOME/.hermes/.env" && set +a && exec ./start.sh' \
  >/tmp/hermes-dashboard.log 2>&1 &
```

## Features

### Chat

- streaming chat via Hermes `/v1/chat/completions`
- structured tool call rendering
- tool timers
- debug log panel
- prompt breakdown display
- `delegate_task` nested subagent activity

### Session Summaries

- automatic summary generation for new chats after the first completed exchange
- manual session summary regeneration
- historical summary backfill endpoint
- summaries displayed in:
  - sessions list
  - session detail
  - graph tooltips
  - graph sidebars and floating panels

### Graph

- session, file, tool, model, and skill graph
- hover tooltips
- floating detail panels
- graph filters and time scopes

## Endpoints

Main dashboard routes:

- `GET /`
- `POST /chat`
- `GET /api/status`
- `GET /api/models`
- `GET /api/personalities`
- `GET /api/sessions`
- `GET /api/sessions/{session_id}`
- `POST /api/sessions/backfill-summaries`
- `POST /api/sessions/{session_id}/summary`
- `GET /api/graph`
- `GET /api/memory`
- `POST /api/memory`
- `GET /api/skills`
- `POST /api/skills/toggle`
- `GET /api/secrets`
- `POST /api/secrets`

## How To Implement This In Your Own Hermes Setup

If you want to adapt this dashboard for your own Hermes deployment:

1. Point `HERMES_AGENT_PATH` at your Hermes runtime checkout.
2. Point `HERMES_HOME` at the Hermes state directory you want to inspect.
3. Start the API-only server with `run_api_server_only.py`.
4. Start the web app with `app.py`.
5. Ensure your `.env` includes any keys needed by Hermes features you want surfaced in the dashboard.

The easiest path for most users is the interactive installer because it writes repo-local launch scripts around their chosen Hermes paths.

Important implementation note:

- this repo is not a standalone replacement for Hermes itself
- it is a standalone dashboard package that depends on a Hermes runtime being available

## Troubleshooting

### Dashboard looks stale

- hard refresh the browser
- restart the `8081` dashboard process

### Chat says Hermes is unavailable

- verify `8642` is listening
- verify `API_SERVER_KEY` matches what the dashboard process is using

### Delegated task stream does not update live

- restart both `8642` and `8081`
- hard refresh the browser
- make sure both services are running the latest code

### Session summary regeneration fails

- verify `OPENROUTER_API_KEY` is present in `~/.hermes/.env`
- make sure the dashboard process loaded that `.env`

## Useful Checks

```sh
curl -s http://127.0.0.1:8081/
curl -s http://127.0.0.1:8081/api/status
curl -s http://127.0.0.1:8081/api/models
curl -s http://127.0.0.1:8081/api/graph?depth=full&hours=24
curl -s http://127.0.0.1:8642/health
ss -ltnp | grep 8081
ss -ltnp | grep 8642
```

## Logs

- dashboard log: `/tmp/hermes-dashboard.log`
- API-only log: `/tmp/hermes-api-only.log`

## Public Use

This repository is public and intended for reuse.

If you publish modifications, keep the runtime path/configuration instructions clear so other users can wire the dashboard into their own Hermes installation without guessing.
