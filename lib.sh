#!/bin/bash
# Shared variables and functions for setup.sh.
# Source this file, do not execute directly.

# When running as root under launchd the PATH is minimal (/usr/bin:/bin:…).
# Prepend common uv / Homebrew install locations so ensure_venv() can find uv.
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH}"

REPO_URL="https://github.com/zrr1999/marrow-core.git"
CORE_DIR="/opt/marrow-core"
CONFIG_PATH="${CORE_DIR}/marrow.toml"
WORKSPACE="/Users/marrow"
SERVICE_RENDER_PLATFORM="${SERVICE_RENDER_PLATFORM:-auto}"

PLISTS=(com.marrow.heart)
SYSTEMD_UNITS=(marrow-heart.service)

# Keep in sync with marrow_core/contracts.py WORKSPACE_DIRS
WORKSPACE_DIRS=(
  runtime/state
  runtime/checkpoints
  runtime/logs/exec
  tasks/queue
  tasks/delegated
  tasks/done
  context.d
  .opencode/agents
)

ensure_workspace_dirs() {
  local dirs=()
  for d in "${WORKSPACE_DIRS[@]}"; do
    dirs+=("${WORKSPACE}/${d}")
  done
  sudo -u marrow mkdir -p "${dirs[@]}"
}

cast_roles() {
  local marrow_bin="${CORE_DIR}/.venv/bin/python"
  [[ -x "$marrow_bin" ]] || return 1
  "$marrow_bin" -m marrow_core.cli setup --config "${CONFIG_PATH}"
}

config_service_mode() {
  CONFIG_PATH_ENV="${CONFIG_PATH}" python3 - <<'PY'
from __future__ import annotations
import os
import tomllib
from pathlib import Path

path = Path(os.environ["CONFIG_PATH_ENV"])
if not path.is_file():
    print("single_user")
else:
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    print((data.get("service") or {}).get("mode", "single_user"))
PY
}

install_daemon() {
  local name="$1"
  local src="${CORE_DIR}/${name}.plist"
  local daemon_dir="/Library/LaunchDaemons"
  local dst="${daemon_dir}/${name}.plist"
  [[ "$(uname -s)" == "Darwin" ]] || return 0
  [[ -f "$src" ]] || return 0
  sudo cp "$src" "$dst"
  sudo chown root:wheel "$dst"
  sudo chmod 644 "$dst"
  sudo launchctl bootout "system/${name}" 2>/dev/null || true
  sudo launchctl bootstrap system "$dst"
}

install_systemd_unit() {
  local name="$1"
  local src="${CORE_DIR}/${name}"
  local dst="/etc/systemd/system/${name}"
  [[ "$(uname -s)" == "Linux" ]] || return 0
  [[ -f "$src" ]] || return 0
  sudo cp "$src" "$dst"
  sudo chmod 644 "$dst"
}

render_service_files() {
  local marrow_bin="${CORE_DIR}/.venv/bin/marrow"
  [[ -x "$marrow_bin" ]] || return 1
  "$marrow_bin" install-service \
    --config "${CONFIG_PATH}" \
    --platform "$SERVICE_RENDER_PLATFORM" \
    --output-dir "$CORE_DIR"
}

install_services() {
  render_service_files

  if [[ "$(uname -s)" == "Darwin" ]]; then
    local name
    for name in "${PLISTS[@]}"; do
      install_daemon "$name"
    done
    return
  fi

  if [[ "$(uname -s)" == "Linux" ]]; then
    local unit
    for unit in "${SYSTEMD_UNITS[@]}"; do
      install_systemd_unit "$unit"
    done
    sudo systemctl daemon-reload
    sudo systemctl enable --now marrow-heart.service
  fi
}

show_service_status() {
  if [[ "$(uname -s)" == "Darwin" ]]; then
    launchctl list | grep com.marrow.heart || true
    return
  fi

  if [[ "$(uname -s)" == "Linux" ]]; then
    systemctl --no-pager --full status marrow-heart.service 2>/dev/null || true
  fi
}

ensure_venv() {
  command -v uv >/dev/null 2>&1 || {
    echo "ERROR: uv not found in PATH (${PATH}). Install via: brew install uv" >&2
    exit 1
  }
  # Use uv's built-in Python resolution (>=3.12 per pyproject.toml) rather than
  # a hardcoded path that only works on Homebrew macOS installations.
  [[ -d "${CORE_DIR}/.venv" ]] || uv venv --python 3.12 --directory "$CORE_DIR" >/dev/null
  uv sync --no-dev --directory "$CORE_DIR"
}
