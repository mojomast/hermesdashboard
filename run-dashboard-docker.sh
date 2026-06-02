#!/bin/sh

set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ENV_FILE="$REPO_DIR/.env.local"

if [ ! -f "$ENV_FILE" ]; then
  printf 'Missing %s. Run ./install.sh first or create .env.local from SETUP.md.\n' "$ENV_FILE" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  printf 'docker is required to run the dashboard container.\n' >&2
  exit 1
fi

set -a
. "$ENV_FILE"
set +a

case "${HERMES_API:-}" in
  http://127.0.0.1:*|http://localhost:*)
    DOCKER_HERMES_API="${DOCKER_HERMES_API:-http://host.docker.internal:${API_SERVER_PORT:-8642}}"
    ;;
  "")
    DOCKER_HERMES_API="${DOCKER_HERMES_API:-http://host.docker.internal:${API_SERVER_PORT:-8642}}"
    ;;
  *)
    DOCKER_HERMES_API="${DOCKER_HERMES_API:-$HERMES_API}"
    ;;
esac

export HERMES_HOME HERMES_AGENT_PATH DASHBOARD_PORT DOCKER_HERMES_API

exec docker compose --env-file "$ENV_FILE" -f "$REPO_DIR/docker-compose.yml" up --build
