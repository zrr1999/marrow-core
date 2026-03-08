"""Role casting via role-forge."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from marrow_core.contracts import ROLE_DIR, WORKSPACE_AGENT_DIR


def cast_roles_to_workspace(
    core_dir: str, workspace: str, *, target: str = "opencode"
) -> list[Path]:
    """Cast canonical roles into workspace runtime config using role-forge."""
    from role_forge.adapters import get_adapter
    from role_forge.config import load_config
    from role_forge.loader import load_agents

    roles_dir = Path(core_dir) / ROLE_DIR
    config_path = Path(core_dir) / "roles.toml"

    if not roles_dir.is_dir():
        raise FileNotFoundError(f"roles directory not found: {roles_dir}")
    if not config_path.is_file():
        raise FileNotFoundError(f"roles.toml not found: {config_path}")

    project_config = load_config(config_path)
    target_config = project_config.targets.get(target)
    if target_config is None:
        raise ValueError(f"target config not found in roles.toml: {target}")

    target_config = target_config.model_copy(update={"output_dir": str(Path(workspace))})
    agents = load_agents(roles_dir, strict=True)
    adapter = get_adapter(target)
    outputs = adapter.cast(agents, target_config)

    managed_root = Path(workspace) / WORKSPACE_AGENT_DIR
    managed_root.mkdir(parents=True, exist_ok=True)
    _clear_generated_outputs(managed_root)

    written: list[Path] = []
    for output in outputs:
        full_path = Path(target_config.output_dir) / output.path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        if full_path.is_symlink() or full_path.exists():
            full_path.unlink()
        full_path.write_text(output.content, encoding="utf-8")
        written.append(full_path)
        logger.info("cast role output {}", full_path)

    _prune_empty_dirs(managed_root)
    return written


def _clear_generated_outputs(agents_dir: Path) -> None:
    for path in sorted(agents_dir.rglob("*.md"), reverse=True):
        if path.name.startswith("custom-"):
            continue
        path.unlink()


def _prune_empty_dirs(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
