"""Workspace — setup and isolation helpers."""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

from marrow_core.contracts import ROLE_DIR, WORKSPACE_DIRS


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
    return []


def load_rules(core_dir: str) -> str:
    """Load the immutable rules prompt from core."""
    rules_path = Path(core_dir) / "prompts" / "rules.md"
    if rules_path.is_file():
        return rules_path.read_text(encoding="utf-8").strip()
    logger.warning("rules file not found: {}", rules_path)
    return ""
