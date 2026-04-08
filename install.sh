#!/bin/sh

set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

prompt() {
  label="$1"
  default_value="$2"
  printf "%s [%s]: " "$label" "$default_value" >&2
  IFS= read -r value || true
  if [ -z "$value" ]; then
    printf "%s" "$default_value"
  else
    printf "%s" "$value"
  fi
}

prompt_yes_no() {
  label="$1"
  default_value="$2"
  suffix="y/N"
  if [ "$default_value" = "y" ]; then
    suffix="Y/n"
  fi
  while true; do
    printf "%s [%s]: " "$label" "$suffix" >&2
    IFS= read -r value || true
    value=$(printf "%s" "$value" | tr '[:upper:]' '[:lower:]')
    if [ -z "$value" ]; then
      value="$default_value"
    fi
    case "$value" in
      y|yes) printf "y"; return 0 ;;
      n|no) printf "n"; return 0 ;;
    esac
  done
}

require_file() {
  path="$1"
  message="$2"
  if [ ! -e "$path" ]; then
    printf "\nError: %s\nMissing path: %s\n" "$message" "$path" >&2
    exit 1
  fi
}

printf "\nHermes Dashboard installer\n"
printf "This will configure the standalone dashboard against an existing Hermes install.\n\n"

DEFAULT_HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_HOME=$(prompt "Hermes home directory" "$DEFAULT_HERMES_HOME")
HERMES_AGENT_PATH=$(prompt "Hermes agent runtime path" "${HERMES_AGENT_PATH:-$HERMES_HOME/hermes-agent}")
HERMES_VENV=$(prompt "Hermes virtualenv path" "${HERMES_VENV:-$HERMES_AGENT_PATH/venv}")
API_SERVER_HOST=$(prompt "Hermes API host" "${API_SERVER_HOST:-127.0.0.1}")
API_SERVER_PORT=$(prompt "Hermes API port" "${API_SERVER_PORT:-8642}")
DASHBOARD_HOST=$(prompt "Dashboard bind host" "${DASHBOARD_HOST:-0.0.0.0}")
DASHBOARD_PORT=$(prompt "Dashboard port" "${DASHBOARD_PORT:-8081}")
API_SERVER_KEY=$(prompt "Dashboard API key" "${API_SERVER_KEY:-hermes-dashboard-secret-9e4349ef052042545dd435d3330a2287}")

require_file "$HERMES_AGENT_PATH" "Hermes agent runtime path does not exist."
require_file "$HERMES_VENV/bin/python" "Hermes virtualenv Python was not found."
require_file "$HERMES_AGENT_PATH/gateway/platforms/api_server.py" "This does not look like a Hermes runtime checkout."

ENV_FILE="$REPO_DIR/.env.local"
cat > "$ENV_FILE" <<EOF
HERMES_HOME=$HERMES_HOME
HERMES_AGENT_PATH=$HERMES_AGENT_PATH
HERMES_VENV=$HERMES_VENV
HERMES_API=http://$API_SERVER_HOST:$API_SERVER_PORT
API_SERVER_HOST=$API_SERVER_HOST
API_SERVER_PORT=$API_SERVER_PORT
API_SERVER_KEY=$API_SERVER_KEY
DASHBOARD_HOST=$DASHBOARD_HOST
DASHBOARD_PORT=$DASHBOARD_PORT
EOF

chmod 600 "$ENV_FILE"

cat > "$REPO_DIR/run-dashboard.sh" <<'EOF'
#!/bin/sh
set -eu
REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f "$REPO_DIR/.env.local" ]; then
  set -a
  . "$REPO_DIR/.env.local"
  set +a
fi
exec "$REPO_DIR/start.sh"
EOF

cat > "$REPO_DIR/run-api-server.sh" <<'EOF'
#!/bin/sh
set -eu
REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f "$REPO_DIR/.env.local" ]; then
  set -a
  . "$REPO_DIR/.env.local"
  set +a
fi
export API_SERVER_ENABLED=true
exec "$HERMES_VENV/bin/python" "$REPO_DIR/run_api_server_only.py"
EOF

chmod +x "$REPO_DIR/run-dashboard.sh" "$REPO_DIR/run-api-server.sh"

CREATE_LAUNCHERS=$(prompt_yes_no "Create background launcher scripts in this repo" "y")
if [ "$CREATE_LAUNCHERS" = "y" ]; then
  cat > "$REPO_DIR/start-background.sh" <<'EOF'
#!/bin/sh
set -eu
REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f "$REPO_DIR/.env.local" ]; then
  set -a
  . "$REPO_DIR/.env.local"
  set +a
fi
nohup "$REPO_DIR/run-api-server.sh" >/tmp/hermes-api-only.log 2>&1 &
nohup "$REPO_DIR/run-dashboard.sh" >/tmp/hermes-dashboard.log 2>&1 &
printf 'Dashboard: http://127.0.0.1:%s\n' "$DASHBOARD_PORT"
EOF
  chmod +x "$REPO_DIR/start-background.sh"
fi

printf "\nSetup complete.\n\n"
printf "Next commands:\n"
printf "  cd %s\n" "$REPO_DIR"
printf "  ./run-api-server.sh\n"
printf "  ./run-dashboard.sh\n"
if [ -f "$REPO_DIR/start-background.sh" ]; then
  printf "  ./start-background.sh\n"
fi
printf "\nThen open: http://127.0.0.1:%s\n" "$DASHBOARD_PORT"
