"""Workspace — setup and isolation helpers.

Core principle: the agent (user marrow) can only write within its workspace.
This module verifies the boundary and manages agent definitions from core -> workspace.

Agent definitions are managed via agent-caster when available (preferred), falling back
to direct symlinks for environments where agent-caster is not installed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
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
    """Deploy base agent definitions from core into workspace .opencode/agents/.

    Prefers agent-caster (``agent-caster cast --target opencode``) when
    available, because it honours the canonical ``roles/`` definitions and
    applies model-mapping from ``refit.toml``.  Falls back to direct symlinks
    for environments where agent-caster is not installed.
    """
    core_path = Path(core_dir)

    # --- Preferred: agent-caster cast ---
    refit = core_path / "refit.toml"
    roles_dir = core_path / "roles"
    if refit.is_file() and roles_dir.is_dir() and _agent_caster_available():
        _cast_via_agent_caster(core_path, workspace)
        return

    # --- Fallback: direct symlinks ---
    _symlink_agents(core_path, workspace)


def _agent_caster_available() -> bool:
    """Return True if ``agent-caster`` is importable / on PATH."""
    try:
        result = subprocess.run(
            ["agent-caster", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _cast_via_agent_caster(core_path: Path, workspace: str) -> None:
    """Run ``agent-caster cast --target opencode`` in the core directory."""
    result = subprocess.run(
        ["agent-caster", "cast", "--target", "opencode", "--project-dir", str(core_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        logger.warning(
            "agent-caster cast failed (rc={}): {}; falling back to symlinks",
            result.returncode,
            result.stderr.strip(),
        )
        _symlink_agents(core_path, workspace)
        return

    # agent-caster writes to core_path/.opencode/agents/*.md — copy to workspace
    cast_agents = core_path / ".opencode" / "agents"
    ws_agents = Path(workspace) / ".opencode" / "agents"
    ws_agents.mkdir(parents=True, exist_ok=True)

    for src in sorted(cast_agents.glob("*.md")):
        dst = ws_agents / src.name
        _install_agent_file(src, dst)

    logger.info("deployed {} agents via agent-caster", len(list(cast_agents.glob("*.md"))))


def _install_agent_file(src: Path, dst: Path) -> None:
    """Copy src to dst, backing up any agent-modified file already at dst."""
    if dst.is_symlink():
        dst.unlink()
    elif dst.is_file():
        backup = dst.with_suffix(dst.suffix + ".agent-backup")
        if backup.exists():
            i = 1
            while True:
                alt = dst.with_suffix(dst.suffix + f".agent-backup-{i}")
                if not alt.exists():
                    backup = alt
                    break
                i += 1
        logger.warning("backing up agent-modified {} -> {}", dst, backup)
        dst.rename(backup)

    shutil.copy2(src, dst)
    logger.info("installed {} -> {}", src.name, dst)


def _symlink_agents(core_path: Path, workspace: str) -> None:
    """Symlink base agent definitions from core into workspace .opencode/agents/.

    Core-owned .md files become read-only symlinks in the agent's config.
    The agent can see them but cannot modify them (targets are root-owned).
    """
    core_agents = core_path / "agents"
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
            if backup.exists():
                # Avoid clobbering an existing backup.
                i = 1
                while True:
                    alt = dst.with_suffix(dst.suffix + f".agent-backup-{i}")
                    if not alt.exists():
                        backup = alt
                        break
                    i += 1
            logger.warning("backing up agent-modified {} -> {}", dst, backup)
            dst.rename(backup)
        dst.symlink_to(src)
        logger.info("symlinked {} -> {}", dst, src)


def load_rules(core_dir: str) -> str:
    """Load the immutable rules prompt from core."""
    rules_path = Path(core_dir) / "prompts" / "rules.md"
    if rules_path.is_file():
        return rules_path.read_text(encoding="utf-8").strip()
    logger.warning("rules file not found: {}", rules_path)
    return ""
