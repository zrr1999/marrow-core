#!/bin/bash
# marrow-core auto-sync: pull latest, refresh venv, re-link agents, restart.
set -euo pipefail

CORE_DIR="/opt/marrow-core"
DAEMON_DIR="/Library/LaunchDaemons"
HEART_PLIST="com.marrow.heart"
WORKSPACE="/Users/marrow"
PYTHON="/opt/homebrew/bin/python3"

[[ -d "${CORE_DIR}/.git" ]] || git clone --branch main --single-branch \
  "https://github.com/zrr1999/marrow-core.git" "$CORE_DIR"

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
if command -v uv >/dev/null 2>&1; then
  [[ -d .venv ]] || uv venv --python "$PYTHON" >/dev/null
  uv sync --no-dev || true
fi

# Re-link agents (core may have updated agent defs)
for agent_md in "${CORE_DIR}"/agents/*.md; do
  name=$(basename "$agent_md")
  dst="${WORKSPACE}/.opencode/agents/${name}"
  ln -sf "$agent_md" "$dst" 2>/dev/null || true
done

# Restart daemon
src="${CORE_DIR}/${HEART_PLIST}.plist"
dst="${DAEMON_DIR}/${HEART_PLIST}.plist"
[[ -f "$src" ]] && cp "$src" "$dst" && chown root:wheel "$dst" && chmod 644 "$dst"
launchctl bootout "system/${HEART_PLIST}" 2>/dev/null || true
launchctl bootstrap system "$dst"

echo "[marrow-sync] Done."
