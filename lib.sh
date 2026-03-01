#!/bin/bash
# Shared variables and functions for setup.sh and sync.sh.
# Source this file, do not execute directly.

REPO_URL="https://github.com/zrr1999/marrow-core.git"
CORE_DIR="/opt/marrow-core"
DAEMON_DIR="/Library/LaunchDaemons"
WORKSPACE="/Users/marrow"
PYTHON="/opt/homebrew/bin/python3"

PLISTS=(com.marrow.heart com.marrow.heart.sync)

# Keep in sync with marrow_core/sandbox.py WORKSPACE_DIRS
WORKSPACE_DIRS=(
  runtime/state
  runtime/handoff/scout-to-artisan
  runtime/handoff/artisan-to-scout
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

link_agents() {
  for agent_md in "${CORE_DIR}"/agents/*.md; do
    [[ -f "$agent_md" ]] || continue
    local name dst
    name=$(basename "$agent_md")
    dst="${WORKSPACE}/.opencode/agents/${name}"
    sudo -u marrow ln -sf "$agent_md" "$dst"
  done
}

install_daemon() {
  local name="$1"
  local src="${CORE_DIR}/${name}.plist"
  local dst="${DAEMON_DIR}/${name}.plist"
  [[ -f "$src" ]] || return 0
  sudo cp "$src" "$dst"
  sudo chown root:wheel "$dst"
  sudo chmod 644 "$dst"
  sudo launchctl bootout "system/${name}" 2>/dev/null || true
  sudo launchctl bootstrap system "$dst"
}

ensure_venv() {
  command -v uv >/dev/null 2>&1 || { echo "ERROR: uv required (brew install uv)" >&2; exit 1; }
  [[ -d "${CORE_DIR}/.venv" ]] || uv venv --python "$PYTHON" --directory "$CORE_DIR" >/dev/null
  uv sync --no-dev --directory "$CORE_DIR"
}
