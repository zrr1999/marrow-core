"""Tests for single-shot sync behavior."""

from __future__ import annotations

import json
from pathlib import Path

from marrow_core.sync import (
    SyncObservation,
    SyncOutcome,
    SyncResult,
    classify_sync_result,
    run_sync_once,
    write_sync_state,
)


def test_classify_sync_result_noop_when_remote_unchanged() -> None:
    outcome = classify_sync_result(SyncObservation(update_available=False, worktree_dirty=False))

    assert outcome.result is SyncResult.NOOP
    assert outcome.exit_code == 0


def test_classify_sync_result_restart_required_for_runtime_change() -> None:
    outcome = classify_sync_result(
        SyncObservation(
            update_available=True,
            worktree_dirty=False,
            changed_files=("marrow_core/cli.py",),
            code_changed=True,
        )
    )

    assert outcome.result is SyncResult.RESTART_REQUIRED
    assert outcome.exit_code == 11


def test_classify_sync_result_failed_for_dirty_worktree() -> None:
    outcome = classify_sync_result(SyncObservation(update_available=True, worktree_dirty=True))

    assert outcome.result is SyncResult.FAILED
    assert outcome.exit_code == 1


def test_write_sync_state_persists_json(tmp_path: Path) -> None:
    state_file = tmp_path / "runtime" / "state" / "sync-status.json"
    outcome = SyncOutcome(SyncResult.NOOP, "remote unchanged")

    write_sync_state(state_file, outcome)

    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert payload["result"] == "noop"
    assert payload["reason"] == "remote unchanged"


def test_run_sync_once_refuses_dirty_worktree(monkeypatch, tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    lock_file = tmp_path / "sync.lock"

    def fake_run_git(core_dir: str, *args: str) -> str:
        if args == ("fetch", "origin", "main"):
            return ""
        if args == ("status", "--short"):
            return " M marrow_core/cli.py"
        raise AssertionError(args)

    monkeypatch.setattr("marrow_core.sync._run_git", fake_run_git)

    outcome = run_sync_once(
        core_dir=str(tmp_path / "core"),
        workspace=str(tmp_path / "workspace"),
        state_file=state_file,
        lock_file=lock_file,
    )

    assert outcome.result is SyncResult.FAILED
    assert outcome.reason == "dirty worktree"


def test_run_sync_once_refreshes_workspace_for_role_only_changes(
    monkeypatch, tmp_path: Path
) -> None:
    state_file = tmp_path / "state.json"
    lock_file = tmp_path / "sync.lock"
    calls: list[tuple[str, str]] = []

    def fake_run_git(core_dir: str, *args: str) -> str:
        responses = {
            ("fetch", "origin", "main"): "",
            ("status", "--short"): "",
            ("rev-parse", "HEAD"): "abc",
            ("rev-parse", "origin/main"): "def",
            ("diff", "--name-only", "HEAD..origin/main"): "roles/orchestrator.md\n",
            ("merge", "--ff-only", "origin/main"): "updated",
        }
        return responses[args]

    monkeypatch.setattr("marrow_core.sync._run_git", fake_run_git)
    monkeypatch.setattr(
        "marrow_core.sync.ensure_workspace_dirs",
        lambda workspace: calls.append(("ensure_workspace_dirs", workspace)),
    )
    monkeypatch.setattr(
        "marrow_core.sync.cast_roles_to_workspace",
        lambda core_dir, workspace: calls.append(("cast_roles_to_workspace", workspace)),
    )

    outcome = run_sync_once(
        core_dir=str(tmp_path / "core"),
        workspace=str(tmp_path / "workspace"),
        state_file=state_file,
        lock_file=lock_file,
    )

    assert outcome.result is SyncResult.RELOADED
    assert calls == [
        ("ensure_workspace_dirs", str(tmp_path / "workspace")),
        ("cast_roles_to_workspace", str(tmp_path / "workspace")),
    ]


def test_run_sync_once_requests_restart_for_runtime_changes(monkeypatch, tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    lock_file = tmp_path / "sync.lock"
    commands: list[str] = []

    def fake_run_git(core_dir: str, *args: str) -> str:
        responses = {
            ("fetch", "origin", "main"): "",
            ("status", "--short"): "",
            ("rev-parse", "HEAD"): "abc",
            ("rev-parse", "origin/main"): "def",
            ("diff", "--name-only", "HEAD..origin/main"): "marrow_core/cli.py\npyproject.toml\n",
            ("merge", "--ff-only", "origin/main"): "updated",
        }
        return responses[args]

    monkeypatch.setattr("marrow_core.sync._run_git", fake_run_git)
    monkeypatch.setattr("marrow_core.sync.ensure_workspace_dirs", lambda workspace: None)
    monkeypatch.setattr("marrow_core.sync.cast_roles_to_workspace", lambda core_dir, workspace: [])
    monkeypatch.setattr("marrow_core.sync._run_uv_sync", lambda core_dir: commands.append("uv"))
    monkeypatch.setattr(
        "marrow_core.sync._render_services", lambda core_dir: commands.append("services")
    )

    outcome = run_sync_once(
        core_dir=str(tmp_path / "core"),
        workspace=str(tmp_path / "workspace"),
        state_file=state_file,
        lock_file=lock_file,
    )

    assert outcome.result is SyncResult.RESTART_REQUIRED
    assert commands == ["uv"]


def test_run_sync_once_fails_when_lock_exists(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    lock_file = tmp_path / "sync.lock"
    lock_file.write_text("busy", encoding="utf-8")

    outcome = run_sync_once(
        core_dir=str(tmp_path / "core"),
        workspace=str(tmp_path / "workspace"),
        state_file=state_file,
        lock_file=lock_file,
    )

    assert outcome.result is SyncResult.FAILED
    assert outcome.reason == "sync already in progress"
