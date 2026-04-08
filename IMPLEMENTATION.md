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
- transcript-based auto-title generation aligned with session summaries
- richer session detail fields in `GET /api/sessions/{id}` including timing, token, cost, lineage, and reasoning/debug metadata

## Auto-Start UX

Preferred installer behavior:

- ask the user whether they want the dashboard and API to auto-start on login
- on Linux with `systemctl`, generate user services and attempt to enable/start them immediately
- on non-Linux systems, explain that manual startup is currently the supported path from this installer

This keeps the prompt user-centered and avoids requiring familiarity with `systemd` to complete setup.
