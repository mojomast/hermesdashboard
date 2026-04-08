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

## Required Runtime Surface

The standalone dashboard expects these pieces from Hermes:

- `gateway.platforms.api_server`
- `hermes_constants`
- `hermes_state`
- `agent.session_summarizer`

If the upstream Hermes runtime changes those import paths, update this repo’s `app.py`, `run_api_server_only.py`, and installer defaults together.
