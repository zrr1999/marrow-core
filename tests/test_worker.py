"""Tests for supervisor/worker helpers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from marrow_core.config import RootConfig
from marrow_core.worker import (
    SupervisorState,
    build_worker_command,
    build_worker_env,
    build_worker_preexec,
    create_task_request,
    create_wake_request,
    drain_worker_requests,
    group_agents_by_worker,
    publish_worker_state,
    worker_request_dir,
)


def test_group_agents_by_worker_groups_shared_identity() -> None:
    root = RootConfig.model_validate(
        {
            "service": {"mode": "supervisor"},
            "agents": [
                {
                    "name": "curator",
                    "agent_command": "cmd",
                    "workspace": "/Users/marrow",
                    "run_as_user": "marrow",
                    "home": "/Users/marrow",
                },
                {
                    "name": "conductor",
                    "agent_command": "cmd",
                    "workspace": "/Users/marrow",
                    "run_as_user": "marrow",
                    "home": "/Users/marrow",
                },
            ],
        }
    )

    specs = group_agents_by_worker(root)

    assert len(specs) == 1
    assert specs[0].agent_names == ("curator", "conductor")


def test_build_worker_env_sets_identity_overrides() -> None:
    spec = group_agents_by_worker(
        RootConfig.model_validate(
            {
                "service": {"mode": "supervisor"},
                "agents": [
                    {
                        "name": "curator",
                        "agent_command": "cmd",
                        "workspace": "/Users/marrow",
                        "run_as_user": "marrow",
                        "run_as_group": "staff",
                        "home": "/Users/marrow",
                    }
                ],
            }
        )
    )[0]

    env = build_worker_env(spec, {"PATH": "/usr/bin"})

    assert env["HOME"] == "/Users/marrow"
    assert env["USER"] == "marrow"
    assert env["LOGNAME"] == "marrow"
    assert env["MARROW_WORKSPACE"] == "/Users/marrow"
    assert env["PATH"] == "/usr/bin"


def test_build_worker_preexec_is_none_when_not_root(monkeypatch) -> None:
    spec = group_agents_by_worker(
        RootConfig.model_validate(
            {
                "service": {"mode": "supervisor"},
                "agents": [
                    {
                        "name": "curator",
                        "agent_command": "cmd",
                        "workspace": "/Users/marrow",
                        "run_as_user": "marrow",
                        "home": "/Users/marrow",
                    }
                ],
            }
        )
    )[0]
    monkeypatch.setattr("marrow_core.worker.os.geteuid", lambda: 1000)
    assert build_worker_preexec(spec) is None


def test_build_worker_command_writes_user_logs(tmp_path: Path) -> None:
    spec = group_agents_by_worker(
        RootConfig.model_validate(
            {
                "service": {"mode": "supervisor"},
                "agents": [
                    {
                        "name": "curator",
                        "agent_command": "cmd",
                        "workspace": str(tmp_path / "workspace"),
                        "run_as_user": "marrow",
                        "home": str(tmp_path / "workspace"),
                    }
                ],
            }
        )
    )[0]

    cmd = build_worker_command(
        marrow_bin="/opt/marrow-core/.venv/bin/marrow",
        config_path=Path("/opt/marrow-core/marrow.toml"),
        spec=spec,
        status_file=Path("/var/lib/marrow/state/workers/curator.json"),
        request_dir=Path("/var/lib/marrow/control/workers/curator"),
    )

    assert "worker-run" in cmd
    assert "--agent curator" in cmd
    assert str(spec.stdout_log_path) in cmd
    assert str(spec.stderr_log_path) in cmd


def test_supervisor_state_reads_worker_status_files(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime-root"
    state = SupervisorState(runtime_root)
    publish_worker_state(
        runtime_root / "state" / "workers" / "worker-1.json",
        {"worker_id": "worker-1", "pid": 1234},
    )

    payload = state.to_dict()

    assert payload["mode"] == "supervisor"
    assert payload["workers"]["worker-1"]["pid"] == 1234


def test_drain_worker_requests_creates_tasks_and_wakes_agents(tmp_path: Path) -> None:
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


def test_worker_request_dir_uses_runtime_root(tmp_path: Path) -> None:
    spec = group_agents_by_worker(
        RootConfig.model_validate(
            {
                "service": {"mode": "supervisor"},
                "agents": [
                    {
                        "name": "curator",
                        "agent_command": "cmd",
                        "workspace": "/Users/marrow",
                        "run_as_user": "marrow",
                        "home": "/Users/marrow",
                    }
                ],
            }
        )
    )[0]

    path = worker_request_dir(tmp_path / "runtime-root", spec)

    assert json.loads(
        json.dumps({"path": str(path)})
    )["path"].startswith(str(tmp_path / "runtime-root" / "control" / "workers"))
