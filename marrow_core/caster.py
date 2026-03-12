"""Role casting via role-forge."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from marrow_core.contracts import ROLE_DIR, WORKSPACE_AGENT_DIR


@dataclass
class CastResult:
    written: list[Path] = field(default_factory=list)
    skipped_permission: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def degraded(self) -> bool:
        return bool(self.skipped_permission or self.errors)


def cast_roles_to_workspace(
    core_dir: str, workspace: str, *, target: str = "opencode"
) -> CastResult:
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
    result = CastResult()
    try:
        managed_root.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        _record_permission_skip(result, managed_root)
    except OSError as exc:
        _record_error(result, managed_root, exc)
    _clear_generated_outputs(managed_root, result)

    for output in outputs:
        full_path = Path(target_config.output_dir) / output.path
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            _record_permission_skip(result, full_path.parent)
            continue
        except OSError as exc:
            _record_error(result, full_path.parent, exc)
            continue

        try:
            if full_path.is_symlink() or full_path.exists():
                full_path.unlink()
        except PermissionError:
            _record_permission_skip(result, full_path)
            continue
        except OSError as exc:
            _record_error(result, full_path, exc)
            continue

        try:
            full_path.write_text(output.content, encoding="utf-8")
        except PermissionError:
            _record_permission_skip(result, full_path)
            continue
        except OSError as exc:
            _record_error(result, full_path, exc)
            continue

        result.written.append(full_path)
        logger.info("cast wrote {}", full_path)

    _prune_empty_dirs(managed_root, result)
    if result.degraded:
        logger.warning(
            "cast completed with {} skipped files and {} degraded file errors",
            len(result.skipped_permission),
            len(result.errors),
        )
    else:
        logger.info("cast completed with {} written files", len(result.written))
    return result


def _clear_generated_outputs(agents_dir: Path, result: CastResult) -> None:
    for path in sorted(agents_dir.rglob("*.md"), reverse=True):
        if path.name.startswith("custom-"):
            continue
        try:
            path.unlink()
        except PermissionError:
            _record_permission_skip(result, path)
        except OSError as exc:
            _record_error(result, path, exc)


def _prune_empty_dirs(root: Path, result: CastResult) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        try:
            is_empty_dir = path.is_dir() and not any(path.iterdir())
        except OSError:
            continue
        if not is_empty_dir:
            continue
        try:
            path.rmdir()
        except PermissionError:
            _record_permission_skip(result, path)
        except OSError as exc:
            _record_error(result, path, exc)


def _record_permission_skip(result: CastResult, path: Path) -> None:
    result.skipped_permission.append(path)
    logger.warning("cast skipped permission-denied file {}", path)


def _record_error(result: CastResult, path: Path, exc: OSError) -> None:
    message = f"{path}: {exc}"
    result.errors.append(message)
    logger.warning("cast degraded file operation {}: {}", path, exc)
