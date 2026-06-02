# Operations Guide

## Common Commands

If you used the installer:

```sh
./run-api-server.sh
./run-dashboard.sh
./start-background.sh
```

Run these as your normal user, not with `sudo`.

Docker dashboard alternative:

```sh
./run-api-server.sh
./run-dashboard-docker.sh
```

The Docker alternative containers only the dashboard web app. Keep the Hermes API running on the host or point `.env.local` at an existing remote `HERMES_API`.

## Optional systemd Setup

If the installer generated user services on Linux:

```sh
systemctl --user daemon-reload
systemctl --user enable --now hermes-dashboard-api.service hermes-dashboard-web.service
```

## Useful Checks

```sh
curl -s http://127.0.0.1:8081/
curl -s http://127.0.0.1:8081/api/status
curl -s http://127.0.0.1:8081/api/settings
curl -s http://127.0.0.1:8081/api/models
curl -s http://127.0.0.1:8081/api/graph?depth=full&hours=24
curl -s http://127.0.0.1:8642/health
ss -ltnp | grep 8081
ss -ltnp | grep 8642
```

## Logs

- dashboard log: `/tmp/hermes-dashboard.log`
- API-only log: `/tmp/hermes-api-only.log`

## Troubleshooting

### Dashboard looks stale

- hard refresh the browser
- restart the `8081` dashboard process
- verify `GET /api/settings` returns JSON from the current code

### Launcher says `Permission denied`

- make sure `start.sh`, `run-dashboard.sh`, and `run-api-server.sh` are executable
- run `chmod +x ./start.sh ./run-dashboard.sh ./run-api-server.sh`
- run them as your normal user instead of `sudo`
- if the repo lives on a `noexec` mount, run `sh ./run-dashboard.sh` or move it to a normal executable filesystem

### Installer completed but first run still fails

- check `python3 --version` and make sure the chosen Hermes virtualenv is Python 3.11+
- if the dashboard reports missing modules, run `"$HERMES_VENV/bin/python" -m pip install -r requirements.txt`
- verify `curl -s http://127.0.0.1:8642/health` if using the bundled API path
- verify `curl -s http://127.0.0.1:8081/api/status` after starting the dashboard

### Address already in use

- choose a different `DASHBOARD_PORT` or `API_SERVER_PORT` during install
- or stop the existing service already listening on that port

### Chat says Hermes is unavailable

- verify `8642` is listening
- verify `API_SERVER_KEY` matches what the dashboard process is using
- if you are not using the bundled launcher, verify `HERMES_API` points at your real Hermes API server
- if the dashboard is running in Docker and your host API is local, verify the container uses `DOCKER_HERMES_API=http://host.docker.internal:<api-port>`

### Docker dashboard fails to start

- verify Docker Compose works with `docker compose version`
- run `./run-api-server.sh` first unless you already have a Hermes API running elsewhere
- verify `.env.local` exists; rerun `./install.sh` if it is missing
- verify `HERMES_HOME` and `HERMES_AGENT_PATH` in `.env.local` are host paths Docker can mount
- if port publishing fails, choose a different `DASHBOARD_PORT` in `.env.local`

### Config tab does not load or save

- verify `GET /api/settings` succeeds
- verify the Hermes install used by this standalone repo includes `hermes_cli.config`, `hermes_cli.skin_engine`, and `hermes_cli.tools_config`
- if the Config tab still reflects old markup, restart `8081` and hard refresh

### Summary endpoints fail on an upstream Hermes install

- this repo no longer depends on `agent.session_summarizer`; summary regeneration/backfill should work from `state.db`
- if it still fails, verify the dashboard can read the target `HERMES_HOME/state.db`

### Bundled API-only launcher fails to start

- some Hermes installs do not expose the internal gateway modules used by `run_api_server_only.py`
- in that case, start Hermes API using your normal runtime path and set `HERMES_API` for the dashboard instead of using the bundled launcher

### Sessions list still shows poor titles

- use the dashboard summary regeneration action to recompute both title and summary from the persisted transcript
- if older sessions still look wrong, verify the dashboard can read the target `HERMES_HOME/state.db` and retry the backfill endpoint

### Session detail still feels sparse

- verify `GET /api/sessions/{id}` includes token, cost, lineage, and reasoning fields from the current Hermes runtime
- restart `8081` and hard refresh after upgrading the dashboard code

### Delegated task stream does not update live

- restart both `8642` and `8081`
- hard refresh the browser
- make sure both services are running the latest code

### I refreshed while Hermes was still responding

- look for the chat banner that says Hermes still has an in-flight or resumable run
- use `Reattach Session` to load the persisted session transcript back into Chat if a session id was already assigned
- use `Resume Stream` to reconnect the saved live stream from the last cached event offset
- if the banner appears but the run is clearly stale, use `Clear Chat` to drop the saved local run state

### Session summary regeneration fails

- verify the dashboard can read the target `HERMES_HOME/state.db`
- verify the selected session actually has persisted transcript messages to summarize

### Graph settings do not stick

- hard refresh once after deploying updated frontend assets
- verify your browser allows localStorage for the dashboard origin
- use the graph settings reset action if a previous saved value is causing an odd layout
