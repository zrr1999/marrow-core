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

from marrow_core.cli import app
from marrow_core.contracts import AUTONOMOUS_AGENTS

runner = CliRunner()


def _write_config(tmp_path: Path, *, socket_path: Path | None = None) -> Path:
    workspace = tmp_path / "workspace"
    context_dir = workspace / "context.d"
    context_dir.mkdir(parents=True)
    script = context_dir / "00_queue.py"
    script.write_text("#!/usr/bin/env python3\nprint('queue ok')\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)

    ipc_block = ""
    if socket_path is not None:
        task_dir = workspace / "tasks" / "queue"
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

    agents = "\n\n".join(
        textwrap.dedent(
            f"""
            [[agents]]
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
            {ipc_block}
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

    async def fake_heartbeat(agent, core_dir, *, once=False, dry_run=False, state=None):
        calls.append((agent.name, once, dry_run, state is not None))

    monkeypatch.setattr("marrow_core.cli.heartbeat", fake_heartbeat)
    monkeypatch.setattr("marrow_core.cli.setup_logging", lambda **_: None)

    result = runner.invoke(app, ["run-once", "--config", str(config)])

    assert result.exit_code == 0
    assert calls == [(name, True, False, True) for name in AUTONOMOUS_AGENTS]


def test_dry_run_invokes_heartbeat_in_dry_mode(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    calls: list[tuple[str, bool, bool]] = []

    async def fake_heartbeat(agent, core_dir, *, once=False, dry_run=False, state=None):
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
        return {"uptime": 1.2, "agents": {"scout": {"tick_count": 3}}}

    monkeypatch.setattr("marrow_core.cli._ipc_request", fake_ipc_request)

    result = runner.invoke(app, ["status", "--config", str(config)])

    assert result.exit_code == 0
    assert '"uptime": 1.2' in result.stdout
    assert '"tick_count": 3' in result.stdout


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
    assert "[project]" in config_out.read_text(encoding="utf-8")
    assert 'roles_dir = "roles"' in config_out.read_text(encoding="utf-8")


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

    async def fake_invoke_sync_once_subprocess(path: Path) -> int:
        assert path == config
        return 10

    async def fake_reload_runtime(root) -> None:
        reloads.extend(agent.name for agent in root.agents)

    async def fake_sleep(seconds: int) -> None:
        sleeps.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(
        "marrow_core.cli._invoke_sync_once_subprocess", fake_invoke_sync_once_subprocess
    )
    monkeypatch.setattr("marrow_core.cli._reload_runtime", fake_reload_runtime)
    monkeypatch.setattr("marrow_core.cli.asyncio.sleep", fake_sleep)

    with contextlib.suppress(asyncio.CancelledError):
        asyncio.run(__import__("marrow_core.cli").cli._sync_supervisor(config))

    assert reloads == list(AUTONOMOUS_AGENTS)
    assert sleeps == [3600]


def test_sync_supervisor_uses_failure_backoff(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    sleeps: list[int] = []

    async def fake_invoke_sync_once_subprocess(path: Path) -> int:
        assert path == config
        return 1

    async def fake_sleep(seconds: int) -> None:
        sleeps.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(
        "marrow_core.cli._invoke_sync_once_subprocess", fake_invoke_sync_once_subprocess
    )
    monkeypatch.setattr("marrow_core.cli.asyncio.sleep", fake_sleep)

    with contextlib.suppress(asyncio.CancelledError):
        asyncio.run(__import__("marrow_core.cli").cli._sync_supervisor(config))

    assert sleeps == [30]


def test_invoke_sync_once_subprocess_uses_resolved_python(monkeypatch, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    call: dict[str, object] = {}

    class FakeProc:
        async def wait(self) -> int:
            return 10

    async def fake_create_subprocess_exec(*argv, **kwargs):
        call["argv"] = argv
        call["kwargs"] = kwargs
        return FakeProc()

    monkeypatch.setattr(
        "marrow_core.cli.resolve_python_executable", lambda: "/venv/bin/python3.14"
    )
    monkeypatch.setattr("marrow_core.cli.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    exit_code = asyncio.run(__import__("marrow_core.cli").cli._invoke_sync_once_subprocess(config))

    assert exit_code == 10
    assert call["argv"] == (
        "/venv/bin/python3.14",
        "-m",
        "marrow_core.cli",
        "sync-once",
        "--config",
        str(config),
    )
    assert call["kwargs"] == {
        "stdout": asyncio.subprocess.DEVNULL,
        "stderr": asyncio.subprocess.DEVNULL,
    }
