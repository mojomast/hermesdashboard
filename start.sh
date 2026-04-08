#!/bin/bash
# Start the Hermes Dashboard
# Edit HERMES_HOME and venv path to match your installation

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
VENV="${HERMES_VENV:-$HERMES_HOME/hermes-agent/venv}"

source "$VENV/bin/activate"
cd "$(dirname "$0")"

export API_SERVER_KEY=$(grep "^API_SERVER_KEY=" "$HERMES_HOME/.env" | cut -d'=' -f2)
export DASHBOARD_PORT="${DASHBOARD_PORT:-8081}"

exec uvicorn app:app --host 127.0.0.1 --port "$DASHBOARD_PORT"
