"""Single-shot sync helpers and result contract."""

from __future__ import annotations

import json
import os
import subprocess
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from marrow_core.caster import cast_roles_to_workspace
from marrow_core.runtime import marrow_binary
from marrow_core.workspace import ensure_workspace_dirs


class SyncResult(StrEnum):
    NOOP = "noop"
    RELOADED = "reloaded"
    RESTART_REQUIRED = "restart_required"
    FAILED = "failed"


@dataclass(frozen=True)
class SyncOutcome:
    result: SyncResult
    reason: str
    changed_files: tuple[str, ...] = ()
    last_attempt_at: str = ""
    last_success_at: str = ""

    @property
    def exit_code(self) -> int:
        return {
            SyncResult.NOOP: 0,
            SyncResult.RELOADED: 10,
            SyncResult.RESTART_REQUIRED: 11,
            SyncResult.FAILED: 1,
        }[self.result]


@dataclass(frozen=True)
class SyncObservation:
    update_available: bool
    worktree_dirty: bool
    changed_files: tuple[str, ...] = ()
    dependency_changed: bool = False
    service_changed: bool = False
    code_changed: bool = False
    role_changed: bool = False
    workspace_changed: bool = False


class SyncError(RuntimeError):
    pass


def classify_sync_result(observation: SyncObservation) -> SyncOutcome:
    now = _utc_now()
    if observation.worktree_dirty:
        return SyncOutcome(SyncResult.FAILED, "dirty worktree", observation.changed_files, now, "")
    if not observation.update_available:
        return SyncOutcome(SyncResult.NOOP, "remote unchanged", observation.changed_files, now, now)
    if observation.code_changed or observation.dependency_changed or observation.service_changed:
        return SyncOutcome(
            SyncResult.RESTART_REQUIRED,
            "runtime or dependency update requires restart",
            observation.changed_files,
            now,
            now,
        )
    if observation.role_changed or observation.workspace_changed:
        return SyncOutcome(
            SyncResult.RELOADED,
            "workspace metadata refreshed",
            observation.changed_files,
            now,
            now,
        )
    return SyncOutcome(
        SyncResult.NOOP, "update produced no effective changes", observation.changed_files, now, now
    )


def write_sync_state(path: Path, outcome: SyncOutcome) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(outcome)
    payload["result"] = outcome.result.value
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_sync_once(
    *,
    core_dir: str,
    workspace: str,
    state_file: Path,
    lock_file: Path,
    refresh_workspace: bool = True,
) -> SyncOutcome:
    if not _acquire_lock(lock_file):
        outcome = SyncOutcome(SyncResult.FAILED, "sync already in progress", (), _utc_now(), "")
        write_sync_state(state_file, outcome)
        return outcome
    try:
        outcome = _run_sync_once_locked(
            core_dir=core_dir,
            workspace=workspace,
            refresh_workspace=refresh_workspace,
        )
        write_sync_state(state_file, outcome)
        return outcome
    finally:
        _release_lock(lock_file)


def _run_sync_once_locked(*, core_dir: str, workspace: str, refresh_workspace: bool) -> SyncOutcome:
    _run_git(core_dir, "fetch", "origin", "main")

    if _git_status_short(core_dir):
        outcome = classify_sync_result(SyncObservation(update_available=True, worktree_dirty=True))
        return outcome

    local_rev = _run_git(core_dir, "rev-parse", "HEAD")
    remote_rev = _run_git(core_dir, "rev-parse", "origin/main")
    if local_rev == remote_rev:
        return classify_sync_result(SyncObservation(update_available=False, worktree_dirty=False))

    changed_files = _changed_files_since_head(core_dir)
    _run_git(core_dir, "merge", "--ff-only", "origin/main")

    deps_changed = _paths_require_restart(changed_files)
    services_changed = _paths_require_service_rerender(changed_files)
    role_changed = any(path.startswith("roles/") for path in changed_files)
    workspace_changed = role_changed

    if refresh_workspace:
        ensure_workspace_dirs(workspace)
        cast_roles_to_workspace(core_dir, workspace)

    if deps_changed:
        _run_uv_sync(core_dir)
    if services_changed:
        _render_services(core_dir)

    if not refresh_workspace and (role_changed or workspace_changed):
        return SyncOutcome(
            SyncResult.RESTART_REQUIRED,
            "workspace refresh deferred to worker restart",
            changed_files,
            _utc_now(),
            _utc_now(),
        )

    return classify_sync_result(
        SyncObservation(
            update_available=True,
            worktree_dirty=False,
            changed_files=changed_files,
            dependency_changed=deps_changed,
            service_changed=services_changed,
            code_changed=_paths_touch_runtime(changed_files),
            role_changed=role_changed,
            workspace_changed=workspace_changed,
        )
    )


def _run_git(core_dir: str, *args: str) -> str:
    return _run_command(["git", "-C", core_dir, *args])


def _run_uv_sync(core_dir: str) -> None:
    _run_command(["uv", "sync", "--no-dev", "--directory", core_dir])


def _render_services(core_dir: str) -> None:
    _run_command(
        [
            marrow_binary(core_dir),
            "install-service",
            "--config",
            f"{core_dir}/marrow.toml",
            "--output-dir",
            core_dir,
        ]
    )


def _run_command(argv: list[str]) -> str:
    proc = subprocess.run(argv, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or proc.stdout.strip() or "command failed"
        raise SyncError(stderr)
    return proc.stdout.strip()


def _git_status_short(core_dir: str) -> str:
    return _run_git(core_dir, "status", "--short")


def _changed_files_since_head(core_dir: str) -> tuple[str, ...]:
    output = _run_git(core_dir, "diff", "--name-only", "HEAD..origin/main")
    return tuple(line for line in output.splitlines() if line)


def _paths_touch_runtime(paths: tuple[str, ...]) -> bool:
    runtime_prefixes = ("marrow_core/", "pyproject.toml", "uv.lock")
    return any(path.startswith(runtime_prefixes) or path == "marrow.toml" for path in paths)


def _paths_require_restart(paths: tuple[str, ...]) -> bool:
    restart_paths = {"pyproject.toml", "uv.lock", "marrow.toml"}
    return any(path in restart_paths or path.startswith("marrow_core/") for path in paths)


def _paths_require_service_rerender(paths: tuple[str, ...]) -> bool:
    service_prefixes = ("lib.sh", "setup.sh", "com.marrow.", "marrow-heart")
    return any(
        path == prefix or path.startswith(prefix) for path in paths for prefix in service_prefixes
    )


def _acquire_lock(lock_file: Path) -> bool:
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    os.close(fd)
    return True


def _release_lock(lock_file: Path) -> None:
    with suppress(FileNotFoundError):
        lock_file.unlink()


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
