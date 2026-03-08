"""Workspace — setup and isolation helpers.

Core principle: the agent (user marrow) can only write within its workspace.
This module verifies the boundary and manages symlinks from core -> workspace.
"""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

from marrow_core.contracts import LEGACY_AGENT_DIR, ROLE_DIR, WORKSPACE_AGENT_DIR, WORKSPACE_DIRS


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


def _core_definition_files(core_dir: str) -> list[Path]:
    core_path = Path(core_dir)
    role_dir = core_path / ROLE_DIR
    if role_dir.is_dir():
        return sorted(path for path in role_dir.rglob("*.md") if path.is_file())

    legacy_dir = core_path / LEGACY_AGENT_DIR
    if legacy_dir.is_dir():
        return sorted(legacy_dir.glob("*.md"))
    return []


def sync_agent_symlinks(core_dir: str, workspace: str) -> None:
    """Symlink core role definitions into the workspace agent directory.

    Canonical source is ``roles/``. Legacy ``agents/`` is a deliberate fallback
    only for older cores that have not migrated yet.
    """
    sources = _core_definition_files(core_dir)
    ws_agents = Path(workspace) / WORKSPACE_AGENT_DIR
    ws_agents.mkdir(parents=True, exist_ok=True)

    if not sources:
        logger.warning(
            "no core role definitions found under {}/{} or {}/{}",
            core_dir,
            ROLE_DIR,
            core_dir,
            LEGACY_AGENT_DIR,
        )
        return

    for src in sources:
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
