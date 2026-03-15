"""Black-box tests for marrow_core.cli."""

from __future__ import annotations

import asyncio
import contextlib
import json
import stat
import sys
import textwrap
from pathlib import Path

from typer.testing import CliRunner

from marrow_core.caster import CastResult
from marrow_core.cli import app
from marrow_core.config import RootConfig
from marrow_core.contracts import AUTONOMOUS_AGENTS
from marrow_core.task_queue import create_task_file

runner = CliRunner()


def _write_config(
    tmp_path: Path,
    *,
    socket_path: Path | None = None,
    service_mode: str = "single_user",
) -> Path:
    workspace = tmp_path / "workspace"
    context_dir = workspace / "context.d"
    context_dir.mkdir(parents=True)
    script = context_dir / "00_queue.py"
    script.write_text("#!/usr/bin/env python3\nprint('queue ok')\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)

    task_dir = workspace / "tasks" / "queue"
    ipc_block = textwrap.dedent(
        """

        [ipc]
        enabled = false
        """
    )
    if socket_path is not None:
        ipc_block = textwrap.dedent(
            f"""

            [ipc]
            enabled = true
            socket_path = {json.dumps(str(socket_path))}
            task_dir = {json.dumps(str(task_dir))}
            """
        )

    sync_block = textwrap.dedent(
        f"""

        [sync]
        enabled = true
        interval_seconds = 3600
        failure_backoff_seconds = 30
        state_file = {json.dumps(str(workspace / "runtime" / "state" / "sync-status.json"))}
        lock_file = {json.dumps(str(workspace / "runtime" / "state" / "sync.lock"))}
        """
    )
    self_check_block = textwrap.dedent(
        """

        [self_check]
        enabled = false
        interval_seconds = 900
        wake_agent = "orchestrator"
        """
    )
    service_block = textwrap.dedent(
        f"""

        [service]
        mode = {json.dumps(service_mode)}
        runtime_root = {json.dumps(str(tmp_path / "service-runtime"))}
        """
    )

    agents = "\n\n".join(
        textwrap.dedent(
            f"""
            [[agents]]
            user = "marrow"
            name = {json.dumps(name)}
            heartbeat_interval = 300
            heartbeat_timeout = 30
            workspace = {json.dumps(str(workspace))}
            agent_command = {json.dumps(sys.executable)}
            context_dirs = [{json.dumps(str(context_dir))}]
            """
        ).strip()
        for name in AUTONOMOUS_AGENTS
    )

    config = tmp_path / "marrow.toml"
    config.write_text(
        textwrap.dedent(
            f"""
            core_dir = {json.dumps(str(tmp_path / "core"))}
            {service_block}
            {ipc_block}
            {self_check_block}
            {sync_block}

            {agents}
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return config


def test_validate_lists_all_autonomous_agents(tmp_path: Path) -> None:
    config = _write_config(tmp_path)

    result = runner.invoke(app, ["validate", "--config", str(config)])

    assert result.exit_code == 0
    for name in AUTONOMOUS_AGENTS:
        assert f"Agent: {name}" in result.stdout
    assert "VALIDATE OK" in result.stdout


def test_doctor_reports_ok_for_valid_workspace(tmp_path: Path) -> None:
    config = _write_config(tmp_path)

    result = runner.invoke(app, ["doctor", "--config", str(config)])

    assert result.exit_code == 0
    assert "DOCTOR OK" in result.stdout


def test_doctor_reports_missing_context_dir(tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    broken = config.read_text(encoding="utf-8").replace("context.d", "missing-context")
    config.write_text(broken, encoding="utf-8")

    result = runner.invoke(app, ["doctor", "--config", str(config)])

    assert result.exit_code == 1
    assert "missing-context (missing)" in result.stdout


def test_run_once_invokes_heartbeat_once(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    calls: list[tuple[str, bool, bool, bool]] = []

    async def fake_heartbeat(
        agent, core_dir, *, once=False, dry_run=False, state=None, wake_event=None
    ):
        calls.append((agent.name, once, dry_run, state is not None))

    monkeypatch.setattr("marrow_core.cli.heartbeat", fake_heartbeat)
    monkeypatch.setattr("marrow_core.cli.setup_logging", lambda **_: None)

    result = runner.invoke(app, ["run-once", "--config", str(config)])

    assert result.exit_code == 0
    assert calls == [(name, True, False, True) for name in AUTONOMOUS_AGENTS]


def test_dry_run_invokes_heartbeat_in_dry_mode(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    calls: list[tuple[str, bool, bool]] = []

    async def fake_heartbeat(
        agent, core_dir, *, once=False, dry_run=False, state=None, wake_event=None
    ):
        calls.append((agent.name, once, dry_run))

    monkeypatch.setattr("marrow_core.cli.heartbeat", fake_heartbeat)
    monkeypatch.setattr("marrow_core.cli.setup_logging", lambda **_: None)

    result = runner.invoke(app, ["dry-run", "--config", str(config)])

    assert result.exit_code == 0
    assert calls == [(name, True, True) for name in AUTONOMOUS_AGENTS]


def test_status_prints_ipc_payload(monkeypatch, tmp_path: Path) -> None:
    socket_path = tmp_path / "marrow.sock"
    socket_path.write_text("", encoding="utf-8")
    config = _write_config(tmp_path, socket_path=socket_path)

    async def fake_ipc_request(socket: str, method: str, path: str, body: str = "") -> dict:
        assert socket == str(socket_path)
        assert method == "GET"
        assert path == "/status"
        assert body == ""
        return {"uptime": 1.2, "agents": {"orchestrator": {"tick_count": 3}}}

    monkeypatch.setattr("marrow_core.cli._ipc_request", fake_ipc_request)

    result = runner.invoke(app, ["status", "--config", str(config)])

    assert result.exit_code == 0
    assert '"uptime": 1.2' in result.stdout
    assert '"tick_count": 3' in result.stdout


def test_wake_submits_ipc_request(monkeypatch, tmp_path: Path) -> None:
    socket_path = tmp_path / "marrow.sock"
    socket_path.write_text("", encoding="utf-8")
    config = _write_config(tmp_path, socket_path=socket_path)
    request: dict[str, str] = {}

    async def fake_ipc_request(socket: str, method: str, path: str, body: str = "") -> dict:
        request.update({"socket": socket, "method": method, "path": path, "body": body})
        return {"ok": True, "agent": "orchestrator"}

    monkeypatch.setattr("marrow_core.cli._ipc_request", fake_ipc_request)

    result = runner.invoke(
        app,
        ["wake", "orchestrator", "--reason", "manual", "--config", str(config)],
    )

    assert result.exit_code == 0
    assert 'wake submitted for "orchestrator"' in result.stdout
    assert request["socket"] == str(socket_path)
    assert request["method"] == "POST"
    assert request["path"] == "/wake"
    assert json.loads(request["body"]) == {"agent": "orchestrator", "reason": "manual"}


def test_task_add_submits_json_payload(monkeypatch, tmp_path: Path) -> None:
    socket_path = tmp_path / "marrow.sock"
    socket_path.write_text("", encoding="utf-8")
    config = _write_config(tmp_path, socket_path=socket_path)
    request: dict[str, str] = {}

    async def fake_ipc_request(socket: str, method: str, path: str, body: str = "") -> dict:
        request.update({"socket": socket, "method": method, "path": path, "body": body})
        return {"ok": True, "file": "20260308-fix-bug.md"}

    monkeypatch.setattr("marrow_core.cli._ipc_request", fake_ipc_request)

    result = runner.invoke(
        app,
        ["task", "add", "Fix bug", "--body", "details", "--config", str(config)],
    )

    assert result.exit_code == 0
    assert "task submitted" in result.stdout
    assert request["socket"] == str(socket_path)
    assert request["method"] == "POST"
    assert request["path"] == "/tasks"
    assert json.loads(request["body"]) == {"title": "Fix bug", "body": "details"}


def test_task_list_prints_queue_entries(monkeypatch, tmp_path: Path) -> None:
    socket_path = tmp_path / "marrow.sock"
    socket_path.write_text("", encoding="utf-8")
    config = _write_config(tmp_path, socket_path=socket_path)

    async def fake_ipc_request(socket: str, method: str, path: str, body: str = "") -> dict:
        assert socket == str(socket_path)
        assert method == "GET"
        assert path == "/tasks"
        assert body == ""
        return {"tasks": [{"file": "task-1.md", "title": "First task"}]}

    monkeypatch.setattr("marrow_core.cli._ipc_request", fake_ipc_request)

    result = runner.invoke(app, ["task", "list", "--config", str(config)])

    assert result.exit_code == 0
    assert "task-1.md" in result.stdout
    assert "First task" in result.stdout


def test_scaffold_creates_workspace_and_config(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    config_out = tmp_path / "generated" / "marrow.toml"
    source_context = tmp_path / "defaults"
    source_context.mkdir()
    (source_context / "queue.py").write_text("print('ok')\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "scaffold",
            "--workspace",
            str(workspace),
            "--config-out",
            str(config_out),
            "--source-context-dir",
            str(source_context),
            "--core-dir",
            "/opt/marrow-core",
        ],
    )

    assert result.exit_code == 0
    assert (workspace / "context.d" / "queue.py").exists()
    assert config_out.exists()
    assert 'core_dir = "/opt/marrow-core"' in config_out.read_text(encoding="utf-8")
    assert "[self_check]" in config_out.read_text(encoding="utf-8")


def test_install_service_renders_units(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    output_dir = tmp_path / "service-out"

    result = runner.invoke(
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

    assert result.exit_code == 0
    assert (output_dir / "marrow-heart.service").exists()
    assert not (output_dir / "marrow-heart-sync.timer").exists()
    assert "rendered 1 service file(s)" in result.stdout


def test_install_service_uses_configured_service_config_path(tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    output_dir = tmp_path / "service-out"
    text = config.read_text(encoding="utf-8").replace(
        '[service]\nmode = "single_user"\nruntime_root = '
        + json.dumps(str(tmp_path / "service-runtime")),
        '[service]\nmode = "single_user"\nruntime_root = '
        + json.dumps(str(tmp_path / "service-runtime"))
        + '\nconfig_path = "/opt/marrow-bot/marrow.toml"',
        1,
    )
    config.write_text(text, encoding="utf-8")

    result = runner.invoke(
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

    service_text = (output_dir / "marrow-heart.service").read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "--config /opt/marrow-bot/marrow.toml --json-logs" in service_text


def test_sync_once_reports_noop(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)

    def fake_run_sync_once(**kwargs):
        assert kwargs["workspace"].endswith("workspace")
        from marrow_core.sync import SyncOutcome, SyncResult

        return SyncOutcome(SyncResult.NOOP, "remote unchanged")

    monkeypatch.setattr("marrow_core.cli.run_sync_once", fake_run_sync_once)
    monkeypatch.setattr("marrow_core.cli.setup_logging", lambda **_: None)

    result = runner.invoke(app, ["sync-once", "--config", str(config)])

    assert result.exit_code == 0
    assert '"result": "noop"' in result.stdout


def test_sync_once_reports_restart_required(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)

    def fake_run_sync_once(**kwargs):
        from marrow_core.sync import SyncOutcome, SyncResult

        return SyncOutcome(SyncResult.RESTART_REQUIRED, "runtime changed")

    monkeypatch.setattr("marrow_core.cli.run_sync_once", fake_run_sync_once)
    monkeypatch.setattr("marrow_core.cli.setup_logging", lambda **_: None)

    result = runner.invoke(app, ["sync-once", "--config", str(config)])

    assert result.exit_code == 11
    assert '"result": "restart_required"' in result.stdout


def test_sync_supervisor_reloads_after_reloaded_result(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    sleeps: list[int] = []
    reloads: list[str] = []

    async def fake_invoke_sync_once(root):
        assert root.sync.interval_seconds == 3600
        from marrow_core.sync import SyncOutcome, SyncResult

        return SyncOutcome(SyncResult.RELOADED, "workspace metadata refreshed")

    async def fake_reload_runtime(config_path: Path, root) -> None:
        assert config_path == config
        reloads.extend(agent.name for agent in root.agents)

    async def fake_sleep(seconds: int) -> None:
        sleeps.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr("marrow_core.cli._invoke_sync_once", fake_invoke_sync_once)
    monkeypatch.setattr("marrow_core.cli._reload_runtime", fake_reload_runtime)
    monkeypatch.setattr("marrow_core.cli.asyncio.sleep", fake_sleep)

    with contextlib.suppress(asyncio.CancelledError):
        asyncio.run(__import__("marrow_core.cli").cli._sync_supervisor(config))

    assert reloads == list(AUTONOMOUS_AGENTS)
    assert sleeps == [3600]


def test_workspace_sync_runs_prepare_for_single_workspace(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr("marrow_core.cli.setup_logging", lambda **_: None)
    monkeypatch.setattr(
        "marrow_core.cli.ensure_workspace_dirs",
        lambda workspace: calls.append(("ensure", workspace)),
    )
    monkeypatch.setattr(
        "marrow_core.cli.cast_roles_to_workspace",
        lambda core_dir, workspace: (
            calls.append(("cast", workspace))
            or CastResult(
                written=[Path(workspace) / ".opencode" / "agents" / "orchestrator.md"],
                skipped_permission=[],
                errors=[],
            )
        ),
    )

    result = runner.invoke(
        app,
        ["workspace-sync", "--config", str(config), "--workspace", str(tmp_path / "workspace")],
    )

    assert result.exit_code == 0
    assert calls == [("ensure", str(tmp_path / "workspace")), ("cast", str(tmp_path / "workspace"))]
    assert "workspace sync ok: written=1 skipped=0 errors=0" in result.stdout


def test_workspace_sync_returns_zero_on_permission_skips(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)

    monkeypatch.setattr("marrow_core.cli.setup_logging", lambda **_: None)
    monkeypatch.setattr(
        "marrow_core.cli.cast_roles_to_workspace",
        lambda core_dir, workspace: CastResult(
            written=[],
            skipped_permission=[Path(workspace) / ".opencode" / "agents" / "orchestrator.md"],
            errors=[],
        ),
    )

    result = runner.invoke(
        app,
        ["workspace-sync", "--config", str(config), "--workspace", str(tmp_path / "workspace")],
    )

    assert result.exit_code == 0
    assert "workspace sync ok: written=0 skipped=1 errors=0" in result.stdout


def test_workspace_sync_returns_nonzero_on_config_errors(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)

    monkeypatch.setattr("marrow_core.cli.setup_logging", lambda **_: None)
    monkeypatch.setattr(
        "marrow_core.cli.cast_roles_to_workspace",
        lambda core_dir, workspace: (_ for _ in ()).throw(
            FileNotFoundError("roles.toml not found")
        ),
    )

    result = runner.invoke(
        app,
        ["workspace-sync", "--config", str(config), "--workspace", str(tmp_path / "workspace")],
    )

    assert result.exit_code == 1
    assert "roles.toml not found" in result.output


def test_sync_supervisor_uses_failure_backoff(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    sleeps: list[int] = []

    async def fake_invoke_sync_once(root):
        assert root.sync.failure_backoff_seconds == 30
        from marrow_core.sync import SyncOutcome, SyncResult

        return SyncOutcome(SyncResult.FAILED, "git fetch failed")

    async def fake_sleep(seconds: int) -> None:
        sleeps.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr("marrow_core.cli._invoke_sync_once", fake_invoke_sync_once)
    monkeypatch.setattr("marrow_core.cli.asyncio.sleep", fake_sleep)

    with contextlib.suppress(asyncio.CancelledError):
        asyncio.run(__import__("marrow_core.cli").cli._sync_supervisor(config))

    assert sleeps == [30]


def test_sync_supervisor_restarts_only_when_env_enabled(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)

    async def fake_invoke_sync_once(root):
        from marrow_core.sync import SyncOutcome, SyncResult

        return SyncOutcome(SyncResult.RESTART_REQUIRED, "runtime changed")

    monkeypatch.setattr("marrow_core.cli._invoke_sync_once", fake_invoke_sync_once)
    monkeypatch.setenv("MARROW_RESTART_HEART_AFTER_SYNC", "1")

    result: object | None = None
    try:
        asyncio.run(__import__("marrow_core.cli").cli._sync_supervisor(config))
    except BaseException as exc:  # pragma: no branch - expected exit path
        result = exc

    assert result is not None
    assert isinstance(result, __import__("typer").Exit)
    assert getattr(result, "exit_code", None) == 0


def test_sync_supervisor_skips_restart_when_env_disabled(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    sleeps: list[int] = []

    async def fake_invoke_sync_once(root):
        from marrow_core.sync import SyncOutcome, SyncResult

        return SyncOutcome(SyncResult.RESTART_REQUIRED, "runtime changed")

    async def fake_sleep(seconds: int) -> None:
        sleeps.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr("marrow_core.cli._invoke_sync_once", fake_invoke_sync_once)
    monkeypatch.delenv("MARROW_RESTART_HEART_AFTER_SYNC", raising=False)
    monkeypatch.setattr("marrow_core.cli.asyncio.sleep", fake_sleep)

    with contextlib.suppress(asyncio.CancelledError):
        asyncio.run(__import__("marrow_core.cli").cli._sync_supervisor(config))

    assert sleeps == [3600]


def test_self_check_supervisor_creates_repair_task_and_wakes_agent(
    monkeypatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    task_dir = workspace / "tasks" / "queue"
    task_dir.mkdir(parents=True)
    root = RootConfig.model_validate(
        {
            "core_dir": str(tmp_path / "core"),
            "self_check": {
                "enabled": True,
                "interval_seconds": 900,
                "wake_agent": "orchestrator",
            },
            "agents": [
                {
                    "name": "orchestrator",
                    "agent_command": str(tmp_path / "missing-binary"),
                    "workspace": str(workspace),
                    "context_dirs": [str(workspace / "missing-context")],
                }
            ],
        }
    )
    wake_events = {"orchestrator": asyncio.Event()}

    async def fake_sleep(seconds: int) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr("marrow_core.cli.asyncio.sleep", fake_sleep)

    with contextlib.suppress(asyncio.CancelledError):
        asyncio.run(
            __import__("marrow_core.cli").cli._self_check_supervisor(
                root,
                lambda title, body: create_task_file(task_dir, title, body),
                wake_events,
            )
        )

    files = list(task_dir.glob("*.md"))
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    assert "Run `orchestrator` in repair mode" in body
    assert wake_events["orchestrator"].is_set()


def test_invoke_sync_once_calls_run_sync_once_in_thread(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    root = __import__("marrow_core.cli").cli.load_config(config)
    call: dict[str, object] = {}

    async def fake_to_thread(func, /, *args, **kwargs):
        call["func"] = func
        call["args"] = args
        call["kwargs"] = kwargs
        return func(*args, **kwargs)

    def fake_run_sync_once(**kwargs):
        call["run_sync_once_kwargs"] = kwargs
        from marrow_core.sync import SyncOutcome, SyncResult

        return SyncOutcome(SyncResult.RELOADED, "workspace metadata refreshed")

    monkeypatch.setattr("marrow_core.cli.asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr("marrow_core.cli.run_sync_once", fake_run_sync_once)

    outcome = asyncio.run(__import__("marrow_core.cli").cli._invoke_sync_once(root))

    assert outcome.result.value == "reloaded"
    assert call["func"] is fake_run_sync_once
    assert call["args"] == ()
    assert call["kwargs"] == {
        "core_dir": str(tmp_path / "core"),
        "workspace": str(tmp_path / "workspace"),
        "state_file": tmp_path / "workspace" / "runtime" / "state" / "sync-status.json",
        "lock_file": tmp_path / "workspace" / "runtime" / "state" / "sync.lock",
        "refresh_workspace": True,
    }
    assert call["run_sync_once_kwargs"] == call["kwargs"]


def test_invoke_sync_once_wraps_sync_errors(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    root = __import__("marrow_core.cli").cli.load_config(config)

    async def fake_to_thread(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    def fake_run_sync_once(**kwargs):
        raise __import__("marrow_core.sync").sync.SyncError("git fetch failed")

    monkeypatch.setattr("marrow_core.cli.asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr("marrow_core.cli.run_sync_once", fake_run_sync_once)

    outcome = asyncio.run(__import__("marrow_core.cli").cli._invoke_sync_once(root))

    assert outcome.result.value == "failed"
    assert outcome.reason == "git fetch failed"
