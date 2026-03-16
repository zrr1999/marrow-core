"""Workspace and profile path helpers."""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

from marrow_core.config import ProfileConfig
from marrow_core.contracts import WORKSPACE_DIRS


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


def _coerce_profile(profile: ProfileConfig | str) -> ProfileConfig:
    if isinstance(profile, ProfileConfig):
        return profile
    return ProfileConfig(root_dir=str(profile))


def profile_rules_path(profile: ProfileConfig | str) -> Path | None:
    profile = _coerce_profile(profile)
    if not profile.rules_path:
        return None
    return Path(profile.rules_path)


def profile_source_context_dir(profile: ProfileConfig | str) -> Path | None:
    profile = _coerce_profile(profile)
    if not profile.source_context_dir:
        return None
    return Path(profile.source_context_dir)


def load_rules(profile: ProfileConfig | str) -> str:
    """Load immutable rules from the configured external profile bundle."""
    rules_path = profile_rules_path(profile)
    if rules_path is None:
        return ""
    if rules_path.is_file():
        return rules_path.read_text(encoding="utf-8").strip()
    logger.warning("rules file not found: {}", rules_path)
    return ""
