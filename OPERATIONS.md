# Operations Guide

## Common Commands

If you used the installer:

```sh
./run-api-server.sh
./run-dashboard.sh
./start-background.sh
```

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
