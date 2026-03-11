#!/bin/bash
# marrow-core setup: clone, install, link agents, start daemons.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib.sh"

# --- Repository ---
if [[ ! -d "${CORE_DIR}/.git" ]]; then
  sudo git clone --branch main --single-branch "$REPO_URL" "$CORE_DIR"
else
  sudo git -C "$CORE_DIR" pull --ff-only origin main
fi

# --- Venv ---
sudo bash -lc "source '${CORE_DIR}/lib.sh' && ensure_venv"

# --- Runtime bootstrap ---
SERVICE_MODE="$(config_service_mode)"

if [[ "${SERVICE_MODE}" != "supervisor" ]]; then
  # --- Workspace dirs & cast runtime agent configs ---
  ensure_workspace_dirs
  cast_roles

  # --- Copy default context providers (agent-owned, modifiable) ---
  for ctx_script in "${CORE_DIR}"/context.d/*; do
    [[ -f "$ctx_script" ]] || continue
    name=$(basename "$ctx_script")
    dst="${WORKSPACE}/context.d/${name}"
    if [[ ! -f "$dst" ]]; then
      sudo -u marrow cp "$ctx_script" "$dst"
      sudo -u marrow chmod +x "$dst"
    fi
  done
  sudo -u marrow chmod +x "${WORKSPACE}"/context.d/* 2>/dev/null || true
else
  cast_roles
fi

# --- Install & start daemons ---
install_services

echo "[marrow] Setup complete."
show_service_status
