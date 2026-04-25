#!/bin/sh

set -eu

INSTALL_URL="https://raw.githubusercontent.com/mojomast/hermesdashboard/main/install.sh"
BOOTSTRAP_URL="https://github.com/mojomast/hermesdashboard.git"

resolve_repo_dir() {
  candidate=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
  if [ -f "$candidate/start.sh" ] && [ -f "$candidate/app.py" ] && [ -f "$candidate/requirements.txt" ]; then
    printf "%s" "$candidate"
    return 0
  fi
  return 1
}

if REPO_DIR=$(resolve_repo_dir); then
  :
else
  if [ -n "${HERMESDASHBOARD_BOOTSTRAPPED:-}" ]; then
    printf "Could not locate hermesdashboard repo files next to install.sh.\n" >&2
    printf "Expected start.sh, app.py, and requirements.txt in the same directory.\n" >&2
    exit 1
  fi

  TARGET_DIR=${HERMESDASHBOARD_DIR:-"$HOME/hermesdashboard"}
  printf "Hermes Dashboard bootstrap\n" >&2
  printf "This one-line installer needs a local checkout first.\n" >&2
  printf "Installing into: %s\n" "$TARGET_DIR" >&2

  if [ -e "$TARGET_DIR" ] && [ ! -d "$TARGET_DIR" ]; then
    printf "Target path exists and is not a directory: %s\n" "$TARGET_DIR" >&2
    exit 1
  fi

  if [ -d "$TARGET_DIR/.git" ]; then
    printf "Existing checkout found. Updating it first...\n" >&2
    git -C "$TARGET_DIR" pull --ff-only
  else
    if [ -e "$TARGET_DIR" ] && [ -n "$(ls -A "$TARGET_DIR" 2>/dev/null || true)" ]; then
      printf "Target directory already exists and is not empty: %s\n" "$TARGET_DIR" >&2
      printf "Set HERMESDASHBOARD_DIR to an empty directory or remove the existing contents.\n" >&2
      exit 1
    fi
    mkdir -p "$TARGET_DIR"
    git clone "$BOOTSTRAP_URL" "$TARGET_DIR"
  fi

  exec env HERMESDASHBOARD_BOOTSTRAPPED=1 sh "$TARGET_DIR/install.sh"
fi

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

require_command() {
  cmd="$1"
  message="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    die "$message"
  fi
}

port_in_use() {
  port="$1"
  python3 - "$port" <<'PY'
import socket
import sys
port = int(sys.argv[1])
for host in ("127.0.0.1", "0.0.0.0"):
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex((host, port)) == 0:
            raise SystemExit(0)
raise SystemExit(1)
PY
}

http_ok() {
  url="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 2 "$url" >/dev/null 2>&1
  else
    return 1
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
info "  Dashboard: 127.0.0.1:8081"
info "If you're unsure, press Enter to accept the defaults."
printf "\n"

require_command git "git is required for the one-line installer bootstrap."
require_command python3 "python3 is required to run the installer checks."

DEFAULT_HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_HOME=$(prompt "Hermes home directory" "$DEFAULT_HERMES_HOME")
HERMES_AGENT_PATH=$(prompt "Path to your Hermes checkout (folder containing gateway/ and hermes_cli/)" "${HERMES_AGENT_PATH:-$HERMES_HOME/hermes-agent}")
HERMES_VENV=$(prompt "Hermes virtualenv path" "${HERMES_VENV:-$HERMES_AGENT_PATH/venv}")
API_SERVER_HOST=$(prompt "Hermes API host" "${API_SERVER_HOST:-127.0.0.1}")
API_SERVER_PORT=$(prompt "Hermes API port" "${API_SERVER_PORT:-8642}")
LOCAL_ONLY=$(prompt_yes_no "Only open the dashboard on this machine" "y")
if [ "$LOCAL_ONLY" = "y" ]; then
  DASHBOARD_HOST="127.0.0.1"
else
  DASHBOARD_HOST=$(prompt "Dashboard bind host" "${DASHBOARD_HOST:-0.0.0.0}")
fi
DASHBOARD_PORT=$(prompt "Dashboard port (recommended: 8081)" "${DASHBOARD_PORT:-8081}")
DEFAULT_API_SERVER_KEY=$(python3 - <<'PY'
import secrets
print(secrets.token_hex(24))
PY
)
API_SERVER_KEY=$(prompt "Dashboard API key (used between dashboard and Hermes API)" "${API_SERVER_KEY:-$DEFAULT_API_SERVER_KEY}")

require_file "$HERMES_AGENT_PATH" "Hermes agent runtime path does not exist."
require_file "$HERMES_VENV/bin/python" "Hermes virtualenv Python was not found."
require_file "$HERMES_AGENT_PATH/gateway/platforms/api_server.py" "This does not look like a Hermes runtime checkout."

PYTHON_OK=$(
  "$HERMES_VENV/bin/python" - <<'PY'
import importlib
import sys

if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required for hermesdashboard")

missing = []
for module in ["starlette", "uvicorn", "httpx", "sse_starlette", "yaml", "jinja2"]:
    try:
        importlib.import_module(module)
    except Exception:
        missing.append(module)

if missing:
    raise SystemExit("Missing dashboard dependencies: " + ", ".join(missing))

print("ok")
PY
) || true

if [ "$PYTHON_OK" != "ok" ]; then
  warn "$PYTHON_OK"
  INSTALL_DEPS=$(prompt_yes_no "Install dashboard Python dependencies into this virtualenv now" "y")
  if [ "$INSTALL_DEPS" = "y" ]; then
    "$HERMES_VENV/bin/python" -m pip install -r "$REPO_DIR/requirements.txt"
  else
    warn "You will need to install dashboard dependencies manually before first run."
  fi
fi

USE_EXISTING_API="n"
if http_ok "http://$API_SERVER_HOST:$API_SERVER_PORT/health"; then
  success "Detected a running Hermes API at http://$API_SERVER_HOST:$API_SERVER_PORT"
  USE_EXISTING_API=$(prompt_yes_no "Reuse the existing Hermes API instead of the bundled API-only launcher" "y")
else
  API_IMPORTS_OK=$(
    HERMES_AGENT_PATH="$HERMES_AGENT_PATH" "$HERMES_VENV/bin/python" - <<'PY'
import os
import sys
from pathlib import Path
sys.path.insert(0, os.environ["HERMES_AGENT_PATH"])
try:
    import gateway.config  # noqa: F401
    import gateway.platforms.api_server  # noqa: F401
except Exception as exc:
    raise SystemExit(str(exc))
print("ok")
PY
  ) || true
  if [ "$API_IMPORTS_OK" != "ok" ]; then
    warn "Bundled API-only launcher may not work with this Hermes install: $API_IMPORTS_OK"
    USE_EXISTING_API=$(prompt_yes_no "Use an existing Hermes API instead of the bundled API-only launcher" "y")
  fi
fi

if port_in_use "$DASHBOARD_PORT"; then
  warn "Port $DASHBOARD_PORT already appears to be in use on this machine."
fi

if [ ! -f "$HERMES_HOME/.env" ]; then
  warn "No $HERMES_HOME/.env found. Summary regeneration and provider-backed features may need manual env setup."
fi

if [ ! -f "$HERMES_HOME/config.yaml" ]; then
  warn "No $HERMES_HOME/config.yaml found. The Config panel may be partially empty until Hermes creates one."
fi

if [ ! -f "$HERMES_HOME/state.db" ]; then
  warn "No $HERMES_HOME/state.db found yet. Sessions/history panels will be empty until Hermes creates it."
fi

if [ ! -w "$HERMES_HOME" ]; then
  warn "HERMES_HOME is not writable by the current user. Config, memory, and secret edits may not persist."
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

chmod +x "$REPO_DIR/start.sh" "$REPO_DIR/run-dashboard.sh" "$REPO_DIR/run-api-server.sh"

if [ "$USE_EXISTING_API" = "y" ]; then
  cat > "$REPO_DIR/run-api-server.sh" <<'EOF'
#!/bin/sh
set -eu
REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f "$REPO_DIR/.env.local" ]; then
  set -a
  . "$REPO_DIR/.env.local"
  set +a
fi
printf 'Using existing Hermes API at %s\n' "$HERMES_API"
printf 'Nothing to start here. Launch your Hermes API using your normal runtime path if needed.\n'
EOF
  chmod +x "$REPO_DIR/run-api-server.sh"
fi

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
printf "Mode selected: "
if [ "$USE_EXISTING_API" = "y" ]; then
  printf "reuse existing Hermes API\n"
else
  printf "bundled API-only launcher\n"
fi
printf "\n"
printf "Next commands:\n"
printf "  cd %s\n" "$REPO_DIR"
printf "  ./run-api-server.sh\n"
printf "  ./run-dashboard.sh\n"
if [ -f "$REPO_DIR/start-background.sh" ]; then
  printf "  ./start-background.sh\n"
fi
printf "\nQuick smoke test:\n"
if [ "$USE_EXISTING_API" = "y" ]; then
  printf "  curl -s http://%s:%s/health\n" "$API_SERVER_HOST" "$API_SERVER_PORT"
else
  printf "  ./run-api-server.sh\n"
  printf "  curl -s http://%s:%s/health\n" "$API_SERVER_HOST" "$API_SERVER_PORT"
fi
printf "  ./run-dashboard.sh\n"
printf "  curl -s http://127.0.0.1:%s/api/status\n" "$DASHBOARD_PORT"
printf "\nThen open: http://127.0.0.1:%s\n" "$DASHBOARD_PORT"
