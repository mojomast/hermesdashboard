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
HAS_SYSTEMCTL="n"
case "$OS_NAME" in
  Linux|Darwin) ;;
  *) warn "This installer is primarily tested on Linux and macOS. Current OS: $OS_NAME" ;;
esac
if [ "$OS_NAME" = "Linux" ] && command -v systemctl >/dev/null 2>&1; then
  HAS_SYSTEMCTL="y"
fi

printf "\n%sHermes Dashboard installer%s\n" "$COLOR_BOLD" "$COLOR_RESET"
printf "This will configure the standalone dashboard against an existing Hermes install.\n\n"
info "Recommended defaults:"
info "  Hermes API: 127.0.0.1:8642"
info "  Dashboard: 0.0.0.0:8081"
info "If you're unsure, press Enter to accept the defaults."
printf "\n"

DEFAULT_HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_HOME=$(prompt "Hermes home directory" "$DEFAULT_HERMES_HOME")
HERMES_AGENT_PATH=$(prompt "Hermes agent runtime path" "${HERMES_AGENT_PATH:-$HERMES_HOME/hermes-agent}")
HERMES_VENV=$(prompt "Hermes virtualenv path" "${HERMES_VENV:-$HERMES_AGENT_PATH/venv}")
API_SERVER_HOST=$(prompt "Hermes API host (recommended: 127.0.0.1)" "${API_SERVER_HOST:-127.0.0.1}")
API_SERVER_PORT=$(prompt "Hermes API port (recommended: 8642)" "${API_SERVER_PORT:-8642}")
DASHBOARD_HOST=$(prompt "Dashboard bind host (recommended: 0.0.0.0)" "${DASHBOARD_HOST:-0.0.0.0}")
DASHBOARD_PORT=$(prompt "Dashboard port (recommended: 8081)" "${DASHBOARD_PORT:-8081}")
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

CREATE_LAUNCHERS=$(prompt_yes_no "Create simple background launcher scripts in this repo" "y")
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

if [ "$HAS_SYSTEMCTL" = "y" ]; then
  info "Linux auto-start is available through systemd user services."
  info "If enabled, Hermes will start automatically after reboot once you log in."
  ENABLE_AUTOSTART=$(prompt_yes_no "Auto-start the Hermes dashboard and API when you log in on this machine" "n")
  if [ "$ENABLE_AUTOSTART" = "y" ]; then
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
    if systemctl --user daemon-reload && systemctl --user enable --now hermes-dashboard-api.service hermes-dashboard-web.service; then
      success "Enabled and started hermes-dashboard-api.service and hermes-dashboard-web.service"
      warn "Optional: run 'sudo loginctl enable-linger $USER' if you want user services available before login after reboot."
    else
      warn "Could not enable/start the systemd user services automatically."
      warn "Run this manually: systemctl --user daemon-reload && systemctl --user enable --now hermes-dashboard-api.service hermes-dashboard-web.service"
    fi
  fi
elif [ "$OS_NAME" != "Linux" ]; then
  warn "Automatic startup via this installer is currently only set up for Linux systemd user services."
  warn "On this OS, use ./run-api-server.sh and ./run-dashboard.sh or hook them into your own login/startup tool."
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
