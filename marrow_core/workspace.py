"""Workspace — setup and isolation helpers.

Core principle: the agent (user marrow) can only write within its workspace.
This module verifies the boundary and manages agent definitions from core -> workspace.

Agent definitions are managed via agent-caster when available (preferred), falling back
to direct symlinks for environments where agent-caster is not installed.
"""

from __future__ import annotations

import os
import shutil
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

    Prefers agent-caster (library API) when available, because it honours the
    canonical ``roles/`` definitions and applies model-mapping from
    ``refit.toml``.  Falls back to direct symlinks for environments where
    agent-caster is not installed.
    """
    core_path = Path(core_dir)

    # --- Preferred: agent-caster library ---
    refit = core_path / "refit.toml"
    roles_dir = core_path / "roles"
    if refit.is_file() and roles_dir.is_dir() and _agent_caster_available():
        _cast_via_agent_caster(core_path, workspace)
        return

    # --- Fallback: direct symlinks ---
    _symlink_agents(core_path, workspace)


def _agent_caster_available() -> bool:
    """Return True if ``agent-caster`` is importable as a library."""
    try:
        import importlib

        importlib.import_module("agent_caster")
        return True
    except ImportError:
        return False


def _cast_via_agent_caster(core_path: Path, workspace: str) -> None:
    """Cast agent definitions to opencode format using the agent-caster library."""
    try:
        from agent_caster.adapters import get_adapter
        from agent_caster.config import load_config
        from agent_caster.loader import load_agents
    except ImportError as exc:
        logger.warning("agent-caster import failed: {}; falling back to symlinks", exc)
        _symlink_agents(core_path, workspace)
        return

    try:
        # Load agent definitions from roles/
        agents_dir = core_path / "roles"
        agents = load_agents(agents_dir)

        # Load refit.toml config and get opencode target config
        project_config = load_config(core_path / "refit.toml")
        target_cfg = project_config.targets.get("opencode")
        if target_cfg is None:
            logger.warning("no 'opencode' target in refit.toml; falling back to symlinks")
            _symlink_agents(core_path, workspace)
            return

        adapter = get_adapter("opencode")
        outputs = adapter.cast(agents, target_cfg)

        ws_agents = Path(workspace) / ".opencode" / "agents"
        ws_agents.mkdir(parents=True, exist_ok=True)

        for out in outputs:
            # agent-caster outputs paths like ".opencode/agents/name.md"
            dst = Path(workspace) / out.path
            dst.parent.mkdir(parents=True, exist_ok=True)
            _install_agent_content(dst, out.content)

        logger.info("deployed {} agents via agent-caster", len(outputs))

    except Exception as exc:  # noqa: BLE001
        logger.warning("agent-caster cast failed: {}; falling back to symlinks", exc)
        _symlink_agents(core_path, workspace)


def _install_agent_content(dst: Path, content: str) -> None:
    """Write content to dst, backing up any existing file first."""
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

    dst.write_text(content, encoding="utf-8")
    logger.info("installed {}", dst.name)


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
