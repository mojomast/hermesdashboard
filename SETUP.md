# Setup Guide

## Requirements

- Linux or macOS shell environment
- Python 3.11+
- a working Hermes checkout/install
- Hermes virtualenv with runtime dependencies available
- access to a Hermes home directory, usually `~/.hermes`

## Required Hermes Layout

Default expected paths:

- `HERMES_HOME=~/.hermes`
- `HERMES_AGENT_PATH=~/.hermes/hermes-agent`
- `HERMES_VENV=~/.hermes/hermes-agent/venv`

If your layout differs, the installer lets you override those values.

## Installer

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/mojomast/hermesdashboard/main/install.sh)"
```

By default this installs or updates the repo at `~/hermesdashboard` and then runs the interactive configurator there.

If you want a different install directory:

```sh
HERMESDASHBOARD_DIR="$HOME/tools/hermesdashboard" bash -c "$(curl -fsSL https://raw.githubusercontent.com/mojomast/hermesdashboard/main/install.sh)"
```

The installer prompts for:

- Hermes home directory
- Hermes runtime path
- Hermes virtualenv path
- Hermes API host and port
- whether to keep the dashboard local-only or bind it externally
- dashboard port
- dashboard API key

The installer also:

- checks Python version and dashboard dependencies
- detects whether a Hermes API is already running
- chooses between reusing an existing API and the bundled API-only launcher
- warns about missing `state.db`, missing `config.yaml`, and non-writable `HERMES_HOME`

It writes local files such as:

- `.env.local`
- `run-api-server.sh`
- `run-dashboard.sh`
- optional `start-background.sh`

Run those scripts as your normal user. Do not use `sudo` unless your Hermes install and this dashboard repo were both intentionally set up as root-owned paths.

If the installer selects “reuse existing Hermes API”, then `run-api-server.sh` becomes a helper that reminds you to use your already-running Hermes API instead of launching a bundled one.

## Opening the Dashboard

After install, most users can open the dashboard like this:

```sh
cd ~/hermesdashboard
./run-api-server.sh
./run-dashboard.sh
```

Then open this URL in a browser:

```text
http://127.0.0.1:8081
```

If you picked a different host or port during install, check `.env.local` in the install directory.

The main values are:

- `DASHBOARD_HOST`
- `DASHBOARD_PORT`
- `HERMES_API`

How to interpret them:

- `DASHBOARD_HOST=127.0.0.1` means open the dashboard from the same machine only
- `DASHBOARD_HOST=0.0.0.0` means the dashboard is listening on all interfaces; on the same machine you can usually open `http://localhost:<port>`
- if you are accessing it from another machine, use `http://<server-ip>:<port>`

Quick health checks:

```sh
curl -s http://127.0.0.1:8642/health
curl -s http://127.0.0.1:8081/api/status
```

If the second command returns JSON, the web dashboard is up.

Optional extras:

- Linux user-level `systemd` units
- Docker dashboard web app runtime

## Linux Auto-Start

On Linux systems with `systemctl` available, the installer asks:

`Auto-start the Hermes dashboard and API when you log in on this machine?`

If you choose yes, it will:

- create `~/.config/systemd/user/hermes-dashboard-api.service`
- create `~/.config/systemd/user/hermes-dashboard-web.service`
- run `systemctl --user daemon-reload`
- attempt `systemctl --user enable --now hermes-dashboard-api.service hermes-dashboard-web.service`

This is user-session startup, which means it normally starts after reboot once the user logs in.

Advanced option:

```sh
sudo loginctl enable-linger "$USER"
```

That can help keep user services available even before a fresh interactive login.

## Manual Install

1. Clone the repo.
2. Install dashboard dependencies if needed:

```sh
pip install -r requirements.txt
```

3. Start the API-only server:

```sh
API_SERVER_ENABLED=true \
API_SERVER_HOST=127.0.0.1 \
API_SERVER_PORT=8642 \
API_SERVER_KEY=your-dashboard-api-key \
/path/to/hermes-agent/venv/bin/python run_api_server_only.py
```

4. Start the dashboard web app:

```sh
HERMES_HOME="$HOME/.hermes" \
HERMES_AGENT_PATH="$HOME/.hermes/hermes-agent" \
HERMES_API="http://127.0.0.1:8642" \
DASHBOARD_PORT=8081 \
/path/to/hermes-agent/venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8081
```

If `./run-dashboard.sh` fails with `Permission denied`, make sure the launcher chain is executable:

```sh
chmod +x ./start.sh ./run-dashboard.sh ./run-api-server.sh ./run-dashboard-docker.sh
```

Healthy first-run smoke test:

```sh
./run-api-server.sh
curl -s http://127.0.0.1:8642/health
./run-dashboard.sh
curl -s http://127.0.0.1:8081/api/status
```

## Docker Dashboard Runtime

Docker support is built into the repo for users who want the dashboard web app in a container.

The Hermes API-only server still runs on the host. Start it with `./run-api-server.sh` or use your normal Hermes API process. The container connects back to the host API through `host.docker.internal` when `.env.local` points at `127.0.0.1` or `localhost`.

Typical flow:

```sh
./run-api-server.sh
./run-dashboard-docker.sh
```

What the Docker launcher uses:

- `Dockerfile` builds the dashboard image from this checkout
- `docker-compose.yml` publishes `${DASHBOARD_PORT:-8081}` on the host
- `.env.local` provides API key, port, and local path configuration
- `${HERMES_HOME}` is mounted read/write at `/hermes-home` so dashboard config, secrets, sessions, and local dashboard state still persist
- `${HERMES_AGENT_PATH}` is mounted read-only at `/hermes-agent` so optional Hermes Python modules can be imported by the dashboard

If your Hermes API is already remote, set `HERMES_API` in `.env.local` to that remote URL and the Docker launcher will preserve it. To override the container-facing API URL explicitly, set `DOCKER_HERMES_API` before running the launcher.
