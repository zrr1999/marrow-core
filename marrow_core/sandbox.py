"""Sandbox — enforce core/evolution isolation.

Core principle: the agent (user marrow) can only write within its workspace.
This module verifies the boundary and manages symlinks from core -> workspace.
"""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

# Standard workspace subdirectories — single source of truth.
# setup.sh should mirror this list.
WORKSPACE_DIRS = (
    "runtime/state",
    "runtime/handoff/scout-to-artisan",
    "runtime/handoff/artisan-to-scout",
    "runtime/checkpoints",
    "runtime/logs/exec",
    "tasks/queue",
    "tasks/delegated",
    "tasks/done",
    "context.d",
    ".opencode/agents",
)


def verify_workspace(workspace: str) -> bool:
    """Check that workspace exists and is writable."""
    p = Path(workspace)
    if not p.is_dir():
        logger.error("workspace does not exist: {}", workspace)
        return False
    if not os.access(p, os.W_OK):
        logger.error("workspace is not writable: {}", workspace)
        return False
    return True


def ensure_workspace_dirs(workspace: str) -> None:
    """Create standard workspace subdirectories if missing."""
    base = Path(workspace)
    for d in WORKSPACE_DIRS:
        (base / d).mkdir(parents=True, exist_ok=True)


def sync_agent_symlinks(core_dir: str, workspace: str) -> None:
    """Symlink base agent definitions from core into workspace .opencode/agents/.

    Core-owned .md files become read-only symlinks in the agent's config.
    The agent can see them but cannot modify them (targets are root-owned).
    """
    core_agents = Path(core_dir) / "agents"
    ws_agents = Path(workspace) / ".opencode" / "agents"
    ws_agents.mkdir(parents=True, exist_ok=True)

    if not core_agents.is_dir():
        logger.warning("core agents dir not found: {}", core_agents)
        return

    for src in sorted(core_agents.glob("*.md")):
        dst = ws_agents / src.name
        # If dst is a symlink, remove and re-create to ensure correct target.
        if dst.is_symlink():
            if dst.resolve() == src.resolve():
                continue
            dst.unlink()
        elif dst.exists():
            # A real file exists — agent may have created it.
            # Back it up and replace with symlink.
            backup = dst.with_suffix(dst.suffix + ".agent-backup")
            logger.warning("backing up agent-modified {} -> {}", dst, backup)
            dst.rename(backup)
        dst.symlink_to(src)
        logger.info("symlinked {} -> {}", dst, src)


def load_rules(core_dir: str) -> str:
    """Load the immutable rules prompt from core."""
    rules_path = Path(core_dir) / "prompts" / "rules.md"
    if rules_path.is_file():
        return rules_path.read_text(encoding="utf-8").strip()
    return ""
