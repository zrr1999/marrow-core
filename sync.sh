#!/bin/bash
# marrow-core auto-sync: pull latest, refresh venv, re-link agents, restart.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib.sh"

[[ -d "${CORE_DIR}/.git" ]] || git clone --branch main --single-branch "$REPO_URL" "$CORE_DIR"

cd "$CORE_DIR"
git fetch origin main

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [[ "$LOCAL" == "$REMOTE" ]]; then
  echo "[marrow-sync] Already up to date."
  exit 0
fi

echo "[marrow-sync] Updating..."

# Stash if dirty
if ! git diff --quiet HEAD 2>/dev/null || ! git diff --quiet --cached HEAD 2>/dev/null; then
  echo "[marrow-sync] WARNING: stashing local changes" >&2
  git stash push -m "marrow-sync $(date +%Y%m%d-%H%M%S)"
fi

git merge --ff-only origin/main 2>/dev/null || {
  echo "[marrow-sync] WARNING: ff failed, resetting" >&2
  git reset --hard origin/main
}

# Refresh venv
ensure_venv

# Ensure workspace dirs & re-link agents (core may have updated agent defs)
ensure_workspace_dirs
link_agents

# Restart heartbeat daemon
install_daemon "com.marrow.heart"

echo "[marrow-sync] Done."
