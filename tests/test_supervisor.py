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

from marrow_core.cli.__main__ import app
from marrow_core.config import RootConfig
from marrow_core.runtime import (
    ensure_service_runtime_dirs,
    resolve_service_log_dir,
    resolve_service_runtime_root,
    resolve_service_user,
    resolve_socket_path,
    resolve_sync_state_path,
)
from marrow_core.services import render_service_files, resolve_service_config_path
from marrow_core.triggers import TriggerMailbox
from marrow_core.worker import (
    SupervisorState,
    build_worker_command,
    create_wake_request,
    drain_worker_triggers,
    group_agents_by_worker,
    publish_worker_state,
)

runner = CliRunner()
EXPECTED_HOME = "/Users/marrow" if sys.platform == "darwin" else "/home/marrow"


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
            name = "orchestrator"
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
                        "name": "orchestrator",
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
                    "name": "orchestrator",
                    "agent_command": "cmd",
                    "workspace": "/Users/marrow",
                }
            ],
        }
    )

    assert root.agents[0].user == "marrow"
    assert root.agents[0].home == EXPECTED_HOME


def test_supervisor_runtime_paths_use_root_runtime(tmp_path: Path) -> None:
    root = RootConfig.model_validate(
        {
            "service": {"mode": "supervisor", "runtime_root": str(tmp_path / "runtime-root")},
            "agents": [
                {
                    "user": "marrow",
                    "name": "orchestrator",
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
                    "name": "orchestrator",
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
        agent_home=root.agents[0].home,
        log_dir="/var/lib/marrow/logs",
    )
    darwin_files = render_service_files(
        platform="darwin",
        core_dir="/opt/marrow-core",
        service_config_path=resolve_service_config_path("darwin", root.service.config_path),
        service_user=resolve_service_user(root),
        agent_home=root.agents[0].home,
        log_dir="/var/lib/marrow/logs",
    )

    assert "User=" not in linux_files[0].content
    assert "service run --config /etc/marrow/marrow.toml --json-logs" in linux_files[0].content
    assert "UserName" not in darwin_files[0].content


def test_grouped_worker_command_keeps_user_logs_in_workspace(tmp_path: Path) -> None:
    root = RootConfig.model_validate(
        {
            "service": {"mode": "supervisor"},
            "agents": [
                {
                    "user": "marrow",
                    "name": "orchestrator",
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
    assert specs[0].home == EXPECTED_HOME
    assert "service worker-run" in cmd
    assert "--agent orchestrator" in cmd and "--agent conductor" in cmd


def test_supervisor_state_reads_root_owned_worker_status(tmp_path: Path) -> None:
    state = SupervisorState(tmp_path / "runtime-root")
    publish_worker_state(
        tmp_path / "runtime-root" / "state" / "workers" / "worker-1.json",
        {"worker_id": "worker-1", "pid": 1234},
    )
    payload = state.to_dict()
    assert payload["workers"]["worker-1"]["pid"] == 1234


def test_worker_trigger_bridge_wakes_agents_with_prompt(tmp_path: Path) -> None:
    request_dir = tmp_path / "runtime-root" / "control" / "workers" / "worker-1"
    create_wake_request(request_dir, "orchestrator", "manual", "Focus on repair")
    trigger_mailboxes = {"orchestrator": TriggerMailbox()}

    drain_worker_triggers(request_dir, trigger_mailboxes)

    trigger = trigger_mailboxes["orchestrator"].consume_pending()
    assert trigger is not None
    assert trigger.reason == "manual"
    assert trigger.prompt == "Focus on repair"


def test_run_dispatches_to_supervisor(monkeypatch, tmp_path: Path) -> None:
    config = _write_supervisor_config(tmp_path)
    calls: list[tuple[str, bool | None]] = []

    async def fake_run_supervisor(config_path: Path, *, ipc: bool | None = None) -> None:
        calls.append((str(config_path), ipc))

    monkeypatch.setattr("marrow_core.cli.service._run_supervisor", fake_run_supervisor)
    monkeypatch.setattr("marrow_core.cli.service.setup_logging", lambda **_: None)

    result = runner.invoke(app, ["run", "--config", str(config)])

    assert result.exit_code == 0
    assert calls == [(str(config), None)]


def test_run_worker_does_not_prepare_workspace(monkeypatch, tmp_path: Path) -> None:
    config = _write_supervisor_config(tmp_path)

    async def fake_heartbeat(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr("marrow_core.cli.service.heartbeat", fake_heartbeat)

    asyncio.run(
        __import__("marrow_core.cli.service").cli.service._run_worker(
            config,
            agent_names=("orchestrator",),
            status_file=tmp_path / "worker.json",
            request_dir=tmp_path / "requests",
        )
    )


def test_supervisor_prepares_workspace_before_spawning_worker(monkeypatch, tmp_path: Path) -> None:
    order: list[str] = []
    root = RootConfig.model_validate(
        {
            "service": {"mode": "supervisor"},
            "sync": {"enabled": False},
            "self_check": {"enabled": False},
            "agents": [
                {
                    "user": "marrow",
                    "name": "orchestrator",
                    "agent_command": "cmd",
                    "workspace": str(tmp_path / "workspace"),
                }
            ],
        }
    )

    class FakeProc:
        returncode = 0

        async def wait(self) -> int:
            return 0

        def terminate(self) -> None:
            self.returncode = 0

    async def fake_prepare(config_path: Path, loaded_root: RootConfig, spec) -> None:
        assert loaded_root is root
        order.append(f"prepare:{spec.worker_id}")

    async def fake_spawn(config_path: Path, loaded_root: RootConfig, spec):
        assert loaded_root is root
        order.append(f"spawn:{spec.worker_id}")
        return FakeProc()

    monkeypatch.setattr("marrow_core.cli.service.load_root_or_exit", lambda path: root)
    monkeypatch.setattr(
        "marrow_core.cli.service.ensure_service_runtime_dirs", lambda loaded_root: None
    )
    monkeypatch.setattr(
        "marrow_core.cli.service._supervisor_trigger_mailboxes",
        lambda loaded_root: {},
    )
    monkeypatch.setattr("marrow_core.cli.service._prepare_worker_workspace", fake_prepare)
    monkeypatch.setattr("marrow_core.cli.service._spawn_worker_process", fake_spawn)

    with pytest.raises(__import__("typer").Exit):
        asyncio.run(
            __import__("marrow_core.cli.service").cli.service._run_supervisor(
                Path("cfg.toml"), ipc=False
            )
        )

    assert order[0].startswith("prepare:")
    assert order[1].startswith("spawn:")


def test_prepare_worker_workspace_permission_skip_is_nonfatal(monkeypatch, tmp_path: Path) -> None:
    config = _write_supervisor_config(tmp_path)
    root = __import__("marrow_core.config").config.load_config(config)
    spec = group_agents_by_worker(root)[0]
    seen: dict[str, tuple[object, ...] | dict[str, object]] = {}

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return (b"workspace sync ok\n", b"")

    async def fake_exec(*argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return FakeProc()

    monkeypatch.setattr("marrow_core.cli.service.os.geteuid", lambda: 0)
    monkeypatch.setattr(
        "marrow_core.cli.service.marrow_binary",
        lambda core_dir: "/opt/marrow-core/.venv/bin/marrow",
    )
    monkeypatch.setattr(
        "marrow_core.cli.service.build_worker_env", lambda spec: {"HOME": spec.home}
    )
    monkeypatch.setattr(
        "marrow_core.cli.service.build_worker_preexec",
        lambda spec: "drop-privileges",
    )
    monkeypatch.setattr("marrow_core.cli.service.asyncio.create_subprocess_exec", fake_exec)

    asyncio.run(
        __import__("marrow_core.cli.service").cli.service._prepare_worker_workspace(
            config, root, spec
        )
    )

    argv = seen["argv"]
    assert isinstance(argv, tuple)
    assert argv[:5] == (
        "/opt/marrow-core/.venv/bin/marrow",
        "service",
        "workspace-sync",
        "--config",
        str(config.resolve()),
    )
