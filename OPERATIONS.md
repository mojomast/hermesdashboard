# Operations Guide

## Common Commands

If you used the installer:

```sh
./run-api-server.sh
./run-dashboard.sh
./start-background.sh
```

Run these as your normal user, not with `sudo`.

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

### Chat says Hermes is unavailable

- verify `8642` is listening
- verify `API_SERVER_KEY` matches what the dashboard process is using
- if you are not using the bundled launcher, verify `HERMES_API` points at your real Hermes API server

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

- verify the Hermes runtime includes the newer transcript-based auto-title generation
- regenerate session summaries/titles only affects new sessions automatically; older sessions may still need manual cleanup or future backfill tooling

### Session detail still feels sparse

- verify `GET /api/sessions/{id}` includes token, cost, lineage, and reasoning fields from the current Hermes runtime
- restart `8081` and hard refresh after upgrading the dashboard code

### Delegated task stream does not update live

- restart both `8642` and `8081`
- hard refresh the browser
- make sure both services are running the latest code

### Session summary regeneration fails

- verify `OPENROUTER_API_KEY` is present in `~/.hermes/.env`
- make sure the dashboard process loaded that `.env`
