"""High-signal tests for the supervisor/worker runtime split."""

from __future__ import annotations

import asyncio
import json
import sys
import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from marrow_core.cli import app
from marrow_core.config import RootConfig
from marrow_core.runtime import (
    ensure_service_runtime_dirs,
    resolve_service_log_dir,
    resolve_service_runtime_root,
    resolve_service_user,
    resolve_socket_path,
    resolve_sync_state_path,
    resolve_task_dir,
)
from marrow_core.services import render_service_files, resolve_service_config_path
from marrow_core.worker import (
    SupervisorState,
    build_worker_command,
    create_task_request,
    create_wake_request,
    drain_worker_requests,
    group_agents_by_worker,
    publish_worker_state,
)

runner = CliRunner()


def _write_supervisor_config(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    context_dir = workspace / "context.d"
    context_dir.mkdir(parents=True)
    sync_state_file = tmp_path / "service-runtime" / "state" / "sync-status.json"
    sync_lock_file = tmp_path / "service-runtime" / "state" / "sync.lock"
    config = tmp_path / "marrow.toml"
    config.write_text(
        textwrap.dedent(
            f"""
            core_dir = {json.dumps(str(tmp_path / "core"))}

            [service]
            mode = "supervisor"
            runtime_root = {json.dumps(str(tmp_path / "service-runtime"))}

            [ipc]
            enabled = true

            [sync]
            enabled = true
            interval_seconds = 3600
            failure_backoff_seconds = 30
            state_file = {json.dumps(str(sync_state_file))}
            lock_file = {json.dumps(str(sync_lock_file))}

            [self_check]
            enabled = false

            [[agents]]
            user = "marrow"
            name = "curator"
            heartbeat_interval = 300
            heartbeat_timeout = 30
            workspace = {json.dumps(str(workspace))}
            agent_command = {json.dumps(sys.executable)}
            context_dirs = [{json.dumps(str(context_dir))}]
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return config


def test_supervisor_config_requires_user_and_defaults_home() -> None:
    with pytest.raises(ValidationError, match="requires user"):
        RootConfig.model_validate(
            {
                "service": {"mode": "supervisor"},
                "agents": [
                    {
                        "name": "curator",
                        "agent_command": "cmd",
                        "workspace": "/Users/marrow",
                    }
                ],
            }
        )

    root = RootConfig.model_validate(
        {
            "service": {"mode": "supervisor"},
            "agents": [
                {
                    "user": "marrow",
                    "name": "curator",
                    "agent_command": "cmd",
                    "workspace": "/Users/marrow",
                }
            ],
        }
    )

    assert root.agents[0].user == "marrow"
    assert root.agents[0].home == "/Users/marrow"


def test_supervisor_runtime_paths_use_root_runtime(tmp_path: Path) -> None:
    root = RootConfig.model_validate(
        {
            "service": {"mode": "supervisor", "runtime_root": str(tmp_path / "runtime-root")},
            "agents": [
                {
                    "user": "marrow",
                    "name": "curator",
                    "agent_command": "cmd",
                    "workspace": "/Users/marrow",
                }
            ],
        }
    )

    assert resolve_service_runtime_root(root) == str(tmp_path / "runtime-root")
    assert resolve_service_log_dir(root) == str(tmp_path / "runtime-root" / "logs")
    assert resolve_socket_path(root) == str(tmp_path / "runtime-root" / "state" / "marrow.sock")
    assert resolve_sync_state_path(root) == str(
        tmp_path / "runtime-root" / "state" / "sync-status.json"
    )
    assert resolve_task_dir(root) == "/Users/marrow/tasks/queue"

    ensure_service_runtime_dirs(root)
    assert (tmp_path / "runtime-root" / "state" / "workers").is_dir()
    assert (tmp_path / "runtime-root" / "control" / "wake").is_dir()


def test_supervisor_service_render_uses_system_config_path_and_root_logs() -> None:
    root = RootConfig.model_validate(
        {
            "service": {"mode": "supervisor"},
            "agents": [
                {
                    "user": "marrow",
                    "name": "curator",
                    "agent_command": "cmd",
                    "workspace": "/Users/marrow",
                }
            ],
        }
    )

    linux_files = render_service_files(
        platform="linux",
        core_dir="/opt/marrow-core",
        service_config_path=resolve_service_config_path("linux", root.service.config_path),
        service_user=resolve_service_user(root),
        log_dir="/var/lib/marrow/logs",
    )
    darwin_files = render_service_files(
        platform="darwin",
        core_dir="/opt/marrow-core",
        service_config_path=resolve_service_config_path("darwin", root.service.config_path),
        service_user=resolve_service_user(root),
        log_dir="/var/lib/marrow/logs",
    )

    assert "User=" not in linux_files[0].content
    assert "--config /etc/marrow/marrow.toml --json-logs" in linux_files[0].content
    assert "StandardOutput=append:/var/lib/marrow/logs/heart.stdout.log" in linux_files[0].content
    assert "UserName" not in darwin_files[0].content
    assert "/Library/Application Support/marrow/marrow.toml" in darwin_files[0].content


def test_grouped_worker_command_keeps_user_logs_in_workspace(tmp_path: Path) -> None:
    root = RootConfig.model_validate(
        {
            "service": {"mode": "supervisor"},
            "agents": [
                {
                    "user": "marrow",
                    "name": "curator",
                    "agent_command": "cmd",
                    "workspace": str(tmp_path / "workspace"),
                },
                {
                    "user": "marrow",
                    "name": "conductor",
                    "agent_command": "cmd",
                    "workspace": str(tmp_path / "workspace"),
                },
            ],
        }
    )

    specs = group_agents_by_worker(root)
    cmd = build_worker_command(
        marrow_bin="/opt/marrow-core/.venv/bin/marrow",
        config_path=Path("/etc/marrow/marrow.toml"),
        spec=specs[0],
        status_file=Path("/var/lib/marrow/state/workers/worker.json"),
        request_dir=Path("/var/lib/marrow/control/workers/worker"),
    )

    assert len(specs) == 1
    assert specs[0].home == "/Users/marrow"
    assert "--agent curator" in cmd and "--agent conductor" in cmd
    assert str(specs[0].stdout_log_path) in cmd
    assert str(specs[0].stderr_log_path) in cmd


def test_supervisor_state_reads_root_owned_worker_status(tmp_path: Path) -> None:
    state = SupervisorState(tmp_path / "runtime-root")
    publish_worker_state(
        tmp_path / "runtime-root" / "state" / "workers" / "worker-1.json",
        {"worker_id": "worker-1", "pid": 1234},
    )

    payload = state.to_dict()

    assert payload["mode"] == "supervisor"
    assert payload["workers"]["worker-1"]["pid"] == 1234


def test_worker_request_bridge_writes_workspace_tasks_and_wakes_agents(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "tasks" / "queue").mkdir(parents=True)
    request_dir = tmp_path / "runtime-root" / "control" / "workers" / "worker-1"
    create_task_request(request_dir, "Fix bug", "details")
    create_wake_request(request_dir, "curator", "manual")
    wake_events = {"curator": asyncio.Event()}

    drain_worker_requests(request_dir, str(workspace), wake_events)

    tasks = sorted((workspace / "tasks" / "queue").glob("*.md"))
    assert len(tasks) == 1
    assert "Fix bug" in tasks[0].read_text(encoding="utf-8")
    assert wake_events["curator"].is_set()


def test_run_dispatches_to_supervisor(monkeypatch, tmp_path: Path) -> None:
    config = _write_supervisor_config(tmp_path)
    calls: list[tuple[str, bool | None]] = []

    async def fake_run_supervisor(config_path: Path, *, ipc: bool | None = None) -> None:
        calls.append((str(config_path), ipc))

    monkeypatch.setattr("marrow_core.cli._run_supervisor", fake_run_supervisor)
    monkeypatch.setattr("marrow_core.cli.setup_logging", lambda **_: None)

    result = runner.invoke(app, ["run", "--config", str(config)])

    assert result.exit_code == 0
    assert calls == [(str(config), None)]


def test_install_service_and_setup_follow_supervisor_boundaries(
    monkeypatch, tmp_path: Path
) -> None:
    config = _write_supervisor_config(tmp_path)
    output_dir = tmp_path / "service-out"
    calls: list[str] = []

    monkeypatch.setattr("marrow_core.cli.setup_logging", lambda **_: None)
    monkeypatch.setattr(
        "marrow_core.cli.ensure_service_runtime_dirs",
        lambda root: calls.append("service-runtime"),
    )
    monkeypatch.setattr(
        "marrow_core.cli.ensure_workspace_dirs",
        lambda workspace: calls.append(f"workspace:{workspace}"),
    )
    monkeypatch.setattr(
        "marrow_core.cli.cast_roles_to_workspace",
        lambda core_dir, workspace: calls.append(f"cast:{workspace}"),
    )

    setup_result = runner.invoke(app, ["setup", "--config", str(config)])
    install_result = runner.invoke(
        app,
        [
            "install-service",
            "--config",
            str(config),
            "--platform",
            "linux",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert setup_result.exit_code == 0
    assert calls == ["service-runtime"]
    assert install_result.exit_code == 0
    content = (output_dir / "marrow-heart.service").read_text(encoding="utf-8")
    assert "--config /etc/marrow/marrow.toml --json-logs" in content
    assert "User=" not in content


def test_sync_once_defers_workspace_refresh_in_supervisor_mode(monkeypatch, tmp_path: Path) -> None:
    config = _write_supervisor_config(tmp_path)
    seen: dict[str, object] = {}

    def fake_run_sync_once(**kwargs):
        seen.update(kwargs)
        from marrow_core.sync import SyncOutcome, SyncResult

        return SyncOutcome(SyncResult.NOOP, "remote unchanged")

    monkeypatch.setattr("marrow_core.cli.run_sync_once", fake_run_sync_once)
    monkeypatch.setattr("marrow_core.cli.setup_logging", lambda **_: None)

    result = runner.invoke(app, ["sync-once", "--config", str(config)])

    assert result.exit_code == 0
    assert seen["refresh_workspace"] is False
