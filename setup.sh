#!/bin/bash
# marrow-core setup: clone, install, link agents, start daemons.
set -euo pipefail

REPO_URL="https://github.com/zrr1999/marrow-core.git"
CORE_DIR="/opt/marrow-core"
DAEMON_DIR="/Library/LaunchDaemons"
WORKSPACE="/Users/marrow"
PYTHON="/opt/homebrew/bin/python3"

PLISTS=(com.marrow.heart com.marrow.heart.sync)

# --- Repository ---
if [[ ! -d "${CORE_DIR}/.git" ]]; then
  sudo git clone --branch main --single-branch "$REPO_URL" "$CORE_DIR"
else
  sudo git -C "$CORE_DIR" pull --ff-only origin main
fi

# --- Venv ---
command -v uv >/dev/null 2>&1 || { echo "ERROR: uv required (brew install uv)" >&2; exit 1; }
sudo bash -lc "cd '${CORE_DIR}' && uv venv --python '${PYTHON}' >/dev/null && uv sync --no-dev"

# --- Workspace dirs ---
sudo -u marrow mkdir -p \
  "${WORKSPACE}/runtime/state" \
  "${WORKSPACE}/runtime/handoff/scout-to-artisan" \
  "${WORKSPACE}/runtime/handoff/artisan-to-scout" \
  "${WORKSPACE}/runtime/checkpoints" \
  "${WORKSPACE}/runtime/logs/exec" \
  "${WORKSPACE}/tasks/queue" \
  "${WORKSPACE}/tasks/delegated" \
  "${WORKSPACE}/tasks/done" \
  "${WORKSPACE}/context.d" \
  "${WORKSPACE}/.opencode/agents"

# --- Symlink base agents ---
for agent_md in "${CORE_DIR}"/agents/*.md; do
  name=$(basename "$agent_md")
  dst="${WORKSPACE}/.opencode/agents/${name}"
  sudo -u marrow ln -sf "$agent_md" "$dst"
done

# --- Copy default context providers (agent-owned, modifiable) ---
for ctx_script in "${CORE_DIR}"/context.d/*; do
  name=$(basename "$ctx_script")
  dst="${WORKSPACE}/context.d/${name}"
  if [[ ! -f "$dst" ]]; then
    sudo -u marrow cp "$ctx_script" "$dst"
    sudo -u marrow chmod +x "$dst"
  fi
done

# --- Make context.d scripts executable ---
sudo -u marrow chmod +x "${WORKSPACE}"/context.d/* 2>/dev/null || true

# --- Install & start daemons ---
for name in "${PLISTS[@]}"; do
  src="${CORE_DIR}/${name}.plist"
  dst="${DAEMON_DIR}/${name}.plist"
  [[ -f "$src" ]] || continue
  sudo cp "$src" "$dst"
  sudo chown root:wheel "$dst"
  sudo chmod 644 "$dst"
  sudo launchctl bootout "system/${name}" 2>/dev/null || true
  sudo launchctl bootstrap system "$dst"
done

echo "[marrow] Setup complete."
launchctl list | grep com.marrow.heart || true
