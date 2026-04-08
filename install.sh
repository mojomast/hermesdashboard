#!/bin/sh

set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ -t 1 ]; then
  COLOR_BLUE=$(printf '\033[34m')
  COLOR_GREEN=$(printf '\033[32m')
  COLOR_YELLOW=$(printf '\033[33m')
  COLOR_RED=$(printf '\033[31m')
  COLOR_BOLD=$(printf '\033[1m')
  COLOR_RESET=$(printf '\033[0m')
else
  COLOR_BLUE=""
  COLOR_GREEN=""
  COLOR_YELLOW=""
  COLOR_RED=""
  COLOR_BOLD=""
  COLOR_RESET=""
fi

info() {
  printf "%s%s%s\n" "$COLOR_BLUE" "$1" "$COLOR_RESET" >&2
}

success() {
  printf "%s%s%s\n" "$COLOR_GREEN" "$1" "$COLOR_RESET" >&2
}

warn() {
  printf "%s%s%s\n" "$COLOR_YELLOW" "$1" "$COLOR_RESET" >&2
}

die() {
  printf "%s%s%s\n" "$COLOR_RED" "$1" "$COLOR_RESET" >&2
  exit 1
}

prompt() {
  label="$1"
  default_value="$2"
  printf "%s%s%s [%s]: " "$COLOR_BOLD" "$label" "$COLOR_RESET" "$default_value" >&2
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
    printf "%s%s%s [%s]: " "$COLOR_BOLD" "$label" "$COLOR_RESET" "$suffix" >&2
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
    die "${message} Missing path: ${path}"
  fi
}

OS_NAME=$(uname -s 2>/dev/null || printf "unknown")
case "$OS_NAME" in
  Linux|Darwin) ;;
  *) warn "This installer is primarily tested on Linux and macOS. Current OS: $OS_NAME" ;;
esac

printf "\n%sHermes Dashboard installer%s\n" "$COLOR_BOLD" "$COLOR_RESET"
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

if [ ! -f "$HERMES_HOME/.env" ]; then
  warn "No $HERMES_HOME/.env found. Summary regeneration and provider-backed features may need manual env setup."
fi

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

if [ "$OS_NAME" = "Linux" ]; then
  CREATE_SYSTEMD=$(prompt_yes_no "Generate user-level systemd units" "n")
  if [ "$CREATE_SYSTEMD" = "y" ]; then
    SYSTEMD_DIR="$HOME/.config/systemd/user"
    mkdir -p "$SYSTEMD_DIR"
    cat > "$SYSTEMD_DIR/hermes-dashboard-api.service" <<EOF
[Unit]
Description=Hermes Dashboard API-only server
After=network.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
EnvironmentFile=$REPO_DIR/.env.local
ExecStart=$REPO_DIR/run-api-server.sh
Restart=on-failure

[Install]
WantedBy=default.target
EOF

    cat > "$SYSTEMD_DIR/hermes-dashboard-web.service" <<EOF
[Unit]
Description=Hermes Dashboard web app
After=network.target hermes-dashboard-api.service
Requires=hermes-dashboard-api.service

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
EnvironmentFile=$REPO_DIR/.env.local
ExecStart=$REPO_DIR/run-dashboard.sh
Restart=on-failure

[Install]
WantedBy=default.target
EOF
    success "Generated systemd user units in $SYSTEMD_DIR"
    warn "Enable them with: systemctl --user daemon-reload && systemctl --user enable --now hermes-dashboard-api.service hermes-dashboard-web.service"
  fi
fi

CREATE_DOCKER=$(prompt_yes_no "Generate Docker wrapper files for the dashboard web app" "n")
if [ "$CREATE_DOCKER" = "y" ]; then
  cat > "$REPO_DIR/Dockerfile" <<'EOF'
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8081"]
EOF

  cat > "$REPO_DIR/docker-compose.yml" <<'EOF'
services:
  hermesdashboard:
    build: .
    ports:
      - "8081:8081"
    env_file:
      - .env.local
    environment:
      HERMES_API: "http://host.docker.internal:8642"
    volumes:
      - ./:/app
      - ${HERMES_HOME:-$HOME/.hermes}:${HERMES_HOME:-$HOME/.hermes}
EOF
  success "Generated Docker wrapper files: Dockerfile and docker-compose.yml"
  warn "The Docker wrapper expects the Hermes API-only server to keep running on the host at port 8642."
fi

printf "\n"
success "Setup complete."
printf "\n"
printf "Next commands:\n"
printf "  cd %s\n" "$REPO_DIR"
printf "  ./run-api-server.sh\n"
printf "  ./run-dashboard.sh\n"
if [ -f "$REPO_DIR/start-background.sh" ]; then
  printf "  ./start-background.sh\n"
fi
printf "\nThen open: http://127.0.0.1:%s\n" "$DASHBOARD_PORT"
