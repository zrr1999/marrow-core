#!/bin/bash
# marrow-core auto-sync: pull latest, refresh venv, re-link agents, restart.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib.sh"

[[ -d "${CORE_DIR}/.git" ]] || git clone --branch main --single-branch "$REPO_URL" "$CORE_DIR"

git -C "$CORE_DIR" fetch origin main

LOCAL=$(git -C "$CORE_DIR" rev-parse HEAD)
REMOTE=$(git -C "$CORE_DIR" rev-parse origin/main)

if [[ "$LOCAL" == "$REMOTE" ]]; then
  echo "[marrow-sync] Already up to date."
  exit 0
fi

echo "[marrow-sync] Updating..."

if [[ -n "$(git -C "$CORE_DIR" status --short)" ]]; then
  echo "[marrow-sync] WARNING: local changes detected in ${CORE_DIR}; aborting sync to avoid destructive update" >&2
  exit 1
fi

git -C "$CORE_DIR" merge --ff-only origin/main

# Refresh venv
ensure_venv

# Ensure workspace dirs & re-cast runtime agent configs
ensure_workspace_dirs
cast_roles

# Re-render and restart services
install_services

echo "[marrow-sync] Done."
