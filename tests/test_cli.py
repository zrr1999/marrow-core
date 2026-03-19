"""High-signal CLI tests for the split command surfaces."""

from __future__ import annotations

import asyncio
import contextlib
import json
import stat
import sys
import textwrap
from pathlib import Path

from typer.testing import CliRunner

from marrow_core.cli.__main__ import app
from marrow_core.contracts import AUTONOMOUS_AGENTS

runner = CliRunner()


def _write_config(
    tmp_path: Path,
    *,
    socket_path: Path | None = None,
    service_mode: str = "single_user",
    with_plugin: bool = False,
) -> Path:
    workspace = tmp_path / "workspace"
    context_dir = workspace / "context.d"
    context_dir.mkdir(parents=True)
    script = context_dir / "00_queue.py"
    script.write_text("#!/usr/bin/env python3\nprint('queue ok')\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)

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

    plugin_block = ""
    if with_plugin:
        plugin_block = textwrap.dedent(
            f"""

            [[plugins]]
            name = "gateway"
            kind = "background_service"
            command = "python"
            args = ["-m", "marrow_gateway", "serve"]
            cwd = {json.dumps(str(tmp_path / "gateway"))}
            workspace = {json.dumps(str(workspace))}
            auto_start = true
            capabilities = ["write_work_items"]

            [plugins.env]
            MARROW_WORKSPACE = {json.dumps(str(workspace))}
            """
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
            {plugin_block}

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


def test_doctor_reports_ok_for_valid_workspace(tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    result = runner.invoke(app, ["doctor", "--config", str(config)])
    assert result.exit_code == 0
    assert "DOCTOR OK" in result.stdout


def test_service_run_once_invokes_heartbeat_once(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    calls: list[tuple[str, bool, bool, bool]] = []

    async def fake_heartbeat(
        agent, core_dir, *, once=False, dry_run=False, state=None, trigger_mailbox=None
    ):
        calls.append((agent.name, once, dry_run, state is not None))

    monkeypatch.setattr("marrow_core.cli.service.heartbeat", fake_heartbeat)
    monkeypatch.setattr("marrow_core.cli.service.setup_logging", lambda **_: None)

    result = runner.invoke(app, ["service", "run-once", "--config", str(config)])

    assert result.exit_code == 0
    assert calls == [(name, True, False, True) for name in AUTONOMOUS_AGENTS]


def test_run_once_flag_invokes_heartbeat_once(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    calls: list[tuple[str, bool, bool, bool]] = []

    async def fake_heartbeat(
        agent, core_dir, *, once=False, dry_run=False, state=None, trigger_mailbox=None
    ):
        calls.append((agent.name, once, dry_run, state is not None))

    monkeypatch.setattr("marrow_core.cli.service.heartbeat", fake_heartbeat)
    monkeypatch.setattr("marrow_core.cli.service.setup_logging", lambda **_: None)

    result = runner.invoke(app, ["run", "--once", "--config", str(config)])

    assert result.exit_code == 0
    assert calls == [(name, True, False, True) for name in AUTONOMOUS_AGENTS]


def test_service_dry_run_invokes_heartbeat_in_dry_mode(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    calls: list[tuple[str, bool, bool]] = []

    async def fake_heartbeat(
        agent, core_dir, *, once=False, dry_run=False, state=None, trigger_mailbox=None
    ):
        calls.append((agent.name, once, dry_run))

    monkeypatch.setattr("marrow_core.cli.service.heartbeat", fake_heartbeat)
    monkeypatch.setattr("marrow_core.cli.service.setup_logging", lambda **_: None)

    result = runner.invoke(app, ["service", "dry-run", "--config", str(config)])

    assert result.exit_code == 0
    assert calls == [(name, True, True) for name in AUTONOMOUS_AGENTS]


def test_run_dry_run_flag_invokes_heartbeat_in_dry_mode(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    calls: list[tuple[str, bool, bool]] = []

    async def fake_heartbeat(
        agent, core_dir, *, once=False, dry_run=False, state=None, trigger_mailbox=None
    ):
        calls.append((agent.name, once, dry_run))

    monkeypatch.setattr("marrow_core.cli.service.heartbeat", fake_heartbeat)
    monkeypatch.setattr("marrow_core.cli.service.setup_logging", lambda **_: None)

    result = runner.invoke(app, ["run", "--dry-run", "--config", str(config)])

    assert result.exit_code == 0
    assert calls == [(name, True, True) for name in AUTONOMOUS_AGENTS]


def test_status_prints_ipc_payload(monkeypatch, tmp_path: Path) -> None:
    socket_path = tmp_path / "marrow.sock"
    socket_path.write_text("", encoding="utf-8")
    config = _write_config(tmp_path, socket_path=socket_path)

    def fake_run_ipc_command(config_path: Path, method: str, path: str, body: str = "") -> dict:
        assert config_path == config
        assert method == "GET"
        assert path == "/status"
        assert body == ""
        return {"uptime": 1.2, "agents": {"orchestrator": {"tick_count": 3}}}

    monkeypatch.setattr("marrow_core.cli.ops.run_ipc_command", fake_run_ipc_command)

    result = runner.invoke(app, ["status", "--config", str(config)])

    assert result.exit_code == 0
    assert '"uptime": 1.2' in result.stdout


def test_wake_submits_ipc_request_with_prompt(monkeypatch, tmp_path: Path) -> None:
    socket_path = tmp_path / "marrow.sock"
    socket_path.write_text("", encoding="utf-8")
    config = _write_config(tmp_path, socket_path=socket_path)
    request: dict[str, str] = {}

    def fake_run_ipc_command(config_path: Path, method: str, path: str, body: str = "") -> dict:
        request.update({"method": method, "path": path, "body": body})
        return {"ok": True, "agent": "orchestrator"}

    monkeypatch.setattr("marrow_core.cli.ops.run_ipc_command", fake_run_ipc_command)

    result = runner.invoke(
        app,
        [
            "wake",
            "orchestrator",
            "--reason",
            "manual",
            "--prompt",
            "Focus on repair.",
            "--config",
            str(config),
        ],
    )

    assert result.exit_code == 0
    assert json.loads(request["body"]) == {
        "agent": "orchestrator",
        "reason": "manual",
        "prompt": "Focus on repair.",
    }


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


def test_install_service_renders_units(tmp_path: Path) -> None:
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
    assert "rendered 1 service file(s)" in result.stdout


def test_sync_once_reports_restart_required(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)

    def fake_run_sync_once(**kwargs):
        from marrow_core.sync import SyncOutcome, SyncResult

        return SyncOutcome(SyncResult.RESTART_REQUIRED, "runtime changed")

    monkeypatch.setattr("marrow_core.cli.service.run_sync_once", fake_run_sync_once)
    monkeypatch.setattr("marrow_core.cli.service.setup_logging", lambda **_: None)

    result = runner.invoke(app, ["sync-once", "--config", str(config)])

    assert result.exit_code == 11
    assert '"result": "restart_required"' in result.stdout


def test_workspace_sync_returns_nonzero_on_errors(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    monkeypatch.setattr("marrow_core.cli.service.setup_logging", lambda **_: None)
    monkeypatch.setattr(
        "marrow_core.cli.service.sync_workspace",
        lambda workspace: (_ for _ in ()).throw(RuntimeError("workspace create failed")),
    )

    result = runner.invoke(
        app,
        ["workspace-sync", "--config", str(config), "--workspace", str(tmp_path / "workspace")],
    )

    assert result.exit_code == 1
    assert "workspace create failed" in result.output


def test_sync_supervisor_reloads_after_reloaded_result(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    sleeps: list[int] = []
    reloads: list[str] = []

    async def fake_invoke_sync_once(root, *, config_path=None):
        assert config_path == config
        from marrow_core.sync import SyncOutcome, SyncResult

        return SyncOutcome(SyncResult.RELOADED, "workspace metadata refreshed")

    async def fake_reload_runtime(config_path: Path, root) -> None:
        reloads.extend(agent.name for agent in root.agents)

    async def fake_sleep(seconds: int) -> None:
        sleeps.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr("marrow_core.cli.service._invoke_sync_once", fake_invoke_sync_once)
    monkeypatch.setattr("marrow_core.cli.service._reload_runtime", fake_reload_runtime)
    monkeypatch.setattr("marrow_core.cli.service.asyncio.sleep", fake_sleep)

    with contextlib.suppress(asyncio.CancelledError):
        asyncio.run(__import__("marrow_core.cli.service").cli.service._sync_supervisor(config))

    assert reloads == list(AUTONOMOUS_AGENTS)
    assert sleeps == [3600]
