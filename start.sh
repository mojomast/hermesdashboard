#!/bin/sh

set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_AGENT_PATH="${HERMES_AGENT_PATH:-$HERMES_HOME/hermes-agent}"
HERMES_VENV="${HERMES_VENV:-$HERMES_AGENT_PATH/venv}"
HERMES_API="${HERMES_API:-http://127.0.0.1:8642}"
DASHBOARD_HOST="${DASHBOARD_HOST:-0.0.0.0}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8081}"

if [ -f "$HERMES_HOME/.env" ]; then
  set -a
  . "$HERMES_HOME/.env"
  set +a
fi

export HERMES_AGENT_PATH
export HERMES_API
export DASHBOARD_PORT

cd "$REPO_DIR"
exec "$HERMES_VENV/bin/python" -m uvicorn app:app --host "$DASHBOARD_HOST" --port "$DASHBOARD_PORT"
