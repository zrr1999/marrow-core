"""CLI entry point — run, run-once, dry-run, validate, setup, doctor, status, task."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shlex
import shutil
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

from marrow_core.caster import cast_roles_to_workspace
from marrow_core.config import RootConfig, load_config
from marrow_core.health import collect_health_issues
from marrow_core.heartbeat import HeartbeatState, heartbeat
from marrow_core.ipc import start_ipc_server
from marrow_core.log import setup_logging
from marrow_core.runtime import (
    ensure_service_runtime_dirs,
    marrow_binary,
    resolve_service_log_dir,
    resolve_service_runtime_root,
    resolve_service_user,
    resolve_socket_path,
    resolve_sync_lock_path,
    resolve_sync_state_path,
    resolve_task_dir,
)
from marrow_core.scaffold import scaffold_workspace, write_config_template
from marrow_core.services import render_service_files, write_service_files
from marrow_core.sync import SyncError, SyncOutcome, SyncResult, run_sync_once
from marrow_core.task_queue import create_task_file, list_tasks
from marrow_core.worker import (
    SupervisorState,
    WorkerSpec,
    build_worker_command,
    build_worker_env,
    build_worker_preexec,
    create_task_request,
    create_wake_request,
    drain_worker_requests,
    group_agents_by_worker,
    prepare_worker_runtime_paths,
    publish_worker_state,
    worker_request_dir,
)
from marrow_core.workspace import ensure_workspace_dirs, verify_workspace

app = typer.Typer(add_completion=False, help="marrow-core: self-evolving agent scheduler.")

# Shared option types
ConfigOpt = Annotated[Path, typer.Option("--config", "-c", help="Path to marrow.toml")]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logging")]
JsonLogsOpt = Annotated[bool, typer.Option("--json-logs", help="Emit JSON log records")]
IpcOpt = Annotated[
    bool | None, typer.Option("--ipc/--no-ipc", help="Override IPC server (default: from config)")
]


class _WorkerWakeProxy:
    def __init__(self, request_dir: Path, agent_name: str) -> None:
        self._request_dir = request_dir
        self._agent_name = agent_name

    def set(self) -> None:
        create_wake_request(self._request_dir, self._agent_name, "")


def _load_root_or_exit(config: Path) -> RootConfig:
    if not config.is_file():
        typer.echo(f"config not found: {config}", err=True)
        raise typer.Exit(code=1)
    return load_config(config)


async def _run_single_user(
    config: Path, *, once: bool = False, dry_run: bool = False, ipc: bool | None = None
) -> None:
    root = _load_root_or_exit(config)
    if not root.agents:
        typer.echo("no agents configured", err=True)
        raise typer.Exit(code=1)

    state = HeartbeatState()
    wake_events = {agent.name: asyncio.Event() for agent in root.agents}
    task_dir = resolve_task_dir(root)

    # Determine whether to start IPC server
    ipc_enabled = ipc if ipc is not None else root.ipc.enabled
    server = None
    if ipc_enabled and not dry_run:
        socket_path = resolve_socket_path(root)
        server = await start_ipc_server(socket_path, task_dir, state, wake_events)

    tasks = [
        asyncio.create_task(
            heartbeat(
                agent,
                root.core_dir,
                once=once,
                dry_run=dry_run,
                state=state,
                wake_event=wake_events[agent.name],
            ),
            name=agent.name,
        )
        for agent in root.agents
    ]
    sync_task = None
    self_check_task = None
    if not once and not dry_run and root.sync.enabled:
        sync_task = asyncio.create_task(_sync_supervisor(config), name="sync-supervisor")
        tasks.append(sync_task)
    if not once and not dry_run and root.self_check.enabled:
        self_check_task = asyncio.create_task(
            _self_check_supervisor(
                root,
                lambda title, body: create_task_file(Path(task_dir), title, body),
                wake_events,
            ),
            name="self-check-supervisor",
        )
        tasks.append(self_check_task)
    try:
        await asyncio.gather(*tasks)
    finally:
        if sync_task is not None and not sync_task.done():
            sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sync_task
        if self_check_task is not None and not self_check_task.done():
            self_check_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self_check_task
        if server is not None:
            server.close()
            await server.wait_closed()
            sock = Path(resolve_socket_path(root))
            if sock.exists():
                sock.unlink()


def _run_single_user_command(
    config: Path,
    verbose: bool,
    json_logs: bool,
    *,
    once: bool = False,
    dry_run: bool = False,
    ipc: bool | None = None,
) -> None:
    setup_logging(verbose=verbose, json_logs=json_logs)
    asyncio.run(_run_single_user(config, once=once, dry_run=dry_run, ipc=ipc))


def _supervisor_task_submitter(root: RootConfig):
    specs = group_agents_by_worker(root)
    if len(specs) != 1:
        raise RuntimeError("supervisor task submission requires exactly one worker")
    request_dir = worker_request_dir(Path(resolve_service_runtime_root(root)), specs[0])
    return lambda title, body: create_task_request(request_dir, title, body)


def _supervisor_task_lister(root: RootConfig) -> list[dict]:
    seen: set[str] = set()
    tasks: list[dict] = []
    for agent in root.agents:
        if agent.workspace in seen:
            continue
        seen.add(agent.workspace)
        for item in list_tasks(Path(agent.workspace) / "tasks" / "queue"):
            item = dict(item)
            item["workspace"] = agent.workspace
            tasks.append(item)
    return tasks


def _supervisor_wake_events(root: RootConfig) -> dict[str, _WorkerWakeProxy]:
    runtime_root = Path(resolve_service_runtime_root(root))
    events: dict[str, _WorkerWakeProxy] = {}
    for spec in group_agents_by_worker(root):
        request_dir = worker_request_dir(runtime_root, spec)
        for agent_name in spec.agent_names:
            events[agent_name] = _WorkerWakeProxy(request_dir, agent_name)
    return events


async def _worker_status_publisher(
    *, status_file: Path, spec: WorkerSpec, state: HeartbeatState, interval: int = 5
) -> None:
    while True:
        publish_worker_state(
            status_file,
            {
                "worker_id": spec.worker_id,
                "run_as_user": spec.run_as_user,
                "run_as_group": spec.run_as_group,
                "home": spec.home,
                "workspace": spec.workspace,
                "agents": spec.agent_names,
                "pid": os.getpid(),
                "state": state.to_dict(),
            },
        )
        await asyncio.sleep(interval)


async def _worker_request_poller(
    *, request_dir: Path, workspace: str, wake_events: dict[str, asyncio.Event], interval: int = 1
) -> None:
    while True:
        drain_worker_requests(request_dir, workspace, wake_events)
        await asyncio.sleep(interval)


async def _run_worker(
    config: Path,
    *,
    agent_names: tuple[str, ...],
    status_file: Path,
    request_dir: Path,
) -> None:
    root = _load_root_or_exit(config)
    selected_names = set(agent_names)
    selected = [agent for agent in root.agents if agent.name in selected_names]
    if not selected:
        typer.echo("no agents selected", err=True)
        raise typer.Exit(code=2)

    specs = group_agents_by_worker(
        RootConfig.model_validate(
            {
                "core_dir": root.core_dir,
                "service": root.service.model_dump(),
                "ipc": root.ipc.model_dump(),
                "sync": root.sync.model_dump(),
                "self_check": root.self_check.model_dump(),
                "agents": [agent.model_dump() for agent in selected],
            }
        )
    )
    if len(specs) != 1:
        typer.echo("selected agents must map to exactly one worker", err=True)
        raise typer.Exit(code=2)
    spec = specs[0]

    ensure_workspace_dirs(spec.workspace)
    cast_roles_to_workspace(root.core_dir, spec.workspace)

    state = HeartbeatState()
    wake_events = {agent.name: asyncio.Event() for agent in selected}
    tasks = [
        asyncio.create_task(
            heartbeat(
                agent,
                root.core_dir,
                state=state,
                wake_event=wake_events[agent.name],
            ),
            name=agent.name,
        )
        for agent in selected
    ]
    publisher = asyncio.create_task(
        _worker_status_publisher(status_file=status_file, spec=spec, state=state),
        name="worker-status-publisher",
    )
    poller = asyncio.create_task(
        _worker_request_poller(
            request_dir=request_dir,
            workspace=spec.workspace,
            wake_events=wake_events,
        ),
        name="worker-request-poller",
    )
    try:
        await asyncio.gather(*tasks)
    finally:
        publisher.cancel()
        poller.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await publisher
        with contextlib.suppress(asyncio.CancelledError):
            await poller
        publish_worker_state(
            status_file,
            {
                "worker_id": spec.worker_id,
                "run_as_user": spec.run_as_user,
                "workspace": spec.workspace,
                "agents": spec.agent_names,
                "pid": os.getpid(),
                "stopped": True,
                "state": state.to_dict(),
            },
        )


async def _spawn_worker_process(config: Path, root: RootConfig, spec: WorkerSpec):
    runtime_root = Path(resolve_service_runtime_root(root))
    status_file, request_dir = prepare_worker_runtime_paths(runtime_root, spec)
    cmd = build_worker_command(
        marrow_bin=marrow_binary(root.core_dir),
        config_path=config.resolve(),
        spec=spec,
        status_file=status_file,
        request_dir=request_dir,
    )
    return await asyncio.create_subprocess_shell(
        cmd,
        cwd=spec.home or spec.workspace,
        env=build_worker_env(spec),
        preexec_fn=build_worker_preexec(spec),
    )


async def _run_supervisor(config: Path, *, ipc: bool | None = None) -> None:
    root = _load_root_or_exit(config)
    if not root.agents:
        typer.echo("no agents configured", err=True)
        raise typer.Exit(code=1)

    ensure_service_runtime_dirs(root)
    runtime_root = Path(resolve_service_runtime_root(root))
    state = SupervisorState(runtime_root)
    wake_events = _supervisor_wake_events(root)
    ipc_enabled = ipc if ipc is not None else root.ipc.enabled
    server = None
    if ipc_enabled:
        server = await start_ipc_server(
            resolve_socket_path(root),
            resolve_task_dir(root),
            state,
            wake_events,
            task_submitter=_supervisor_task_submitter(root),
            task_lister=lambda: _supervisor_task_lister(root),
        )

    worker_specs = group_agents_by_worker(root)
    processes = {
        spec.worker_id: await _spawn_worker_process(config, root, spec) for spec in worker_specs
    }
    waiters = {
        worker_id: asyncio.create_task(proc.wait(), name=f"worker:{worker_id}")
        for worker_id, proc in processes.items()
    }
    sync_task = None
    self_check_task = None
    if root.sync.enabled:
        sync_task = asyncio.create_task(_sync_supervisor(config), name="sync-supervisor")
    if root.self_check.enabled:
        self_check_task = asyncio.create_task(
            _self_check_supervisor(root, _supervisor_task_submitter(root), wake_events),
            name="self-check-supervisor",
        )

    tracked = list(waiters.values())
    if sync_task is not None:
        tracked.append(sync_task)
    if self_check_task is not None:
        tracked.append(self_check_task)

    try:
        done, pending = await asyncio.wait(tracked, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exc = task.exception()
            if exc is not None:
                raise exc
        worker_exit = next((task for task in done if task in waiters.values()), None)
        if worker_exit is not None:
            raise typer.Exit(code=1)
        for task in pending:
            await task
    finally:
        for task in [sync_task, self_check_task, *waiters.values()]:
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        for proc in processes.values():
            if proc.returncode is None:
                proc.terminate()
                with contextlib.suppress(ProcessLookupError):
                    await proc.wait()
        if server is not None:
            server.close()
            await server.wait_closed()
            sock = Path(resolve_socket_path(root))
            if sock.exists():
                sock.unlink()


async def _sync_supervisor(config: Path) -> None:
    while True:
        root = load_config(config)
        outcome = await _invoke_sync_once(root)
        if outcome.result is SyncResult.NOOP:
            await asyncio.sleep(root.sync.interval_seconds)
            continue
        if outcome.result is SyncResult.RELOADED:
            await _reload_runtime(root)
            await asyncio.sleep(root.sync.interval_seconds)
            continue
        if outcome.result is SyncResult.RESTART_REQUIRED:
            raise typer.Exit(code=0)
        await asyncio.sleep(root.sync.failure_backoff_seconds)


async def _invoke_sync_once(root: RootConfig) -> SyncOutcome:
    if not root.agents:
        return SyncOutcome(SyncResult.FAILED, "no agents configured")
    try:
        return await asyncio.to_thread(
            run_sync_once,
            core_dir=root.core_dir,
            workspace=root.agents[0].workspace,
            state_file=Path(resolve_sync_state_path(root)),
            lock_file=Path(resolve_sync_lock_path(root)),
            refresh_workspace=root.service.mode != "supervisor",
        )
    except SyncError as exc:
        return SyncOutcome(SyncResult.FAILED, str(exc))


async def _reload_runtime(root: RootConfig) -> None:
    for agent in root.agents:
        ensure_workspace_dirs(agent.workspace)
        cast_roles_to_workspace(root.core_dir, agent.workspace)


def _wake_agent(wake_events: dict[str, asyncio.Event], agent_name: str, *, reason: str) -> bool:
    event = wake_events.get(agent_name)
    if event is None:
        logger.warning('wake requested for unknown agent "{}" ({})', agent_name, reason)
        return False
    event.set()
    logger.info('wake requested for "{}" ({})', agent_name, reason)
    return True


def _self_check_task_body(agent_name: str, issues: list[str]) -> str:
    lines = [
        f"Run `{agent_name}` in repair mode and resolve the following core health issues.",
        "",
        "Observed issues:",
    ]
    lines.extend(f"- {issue}" for issue in issues)
    return "\n".join(lines) + "\n"


async def _self_check_supervisor(
    root: RootConfig,
    submit_task,
    wake_events,
) -> None:
    last_failure_signature = ""
    while True:
        issues = collect_health_issues(root)
        if issues:
            signature = "\n".join(issues)
            if signature != last_failure_signature:
                task = submit_task(
                    "Core self-check requires repair",
                    _self_check_task_body(root.self_check.wake_agent, issues),
                )
                logger.warning(
                    "core self-check failed with {} issue(s); queued {}",
                    len(issues),
                    task.name,
                )
                _wake_agent(wake_events, root.self_check.wake_agent, reason="core self-check")
                last_failure_signature = signature
        else:
            last_failure_signature = ""
        await asyncio.sleep(root.self_check.interval_seconds)


@app.command()
def run(
    config: ConfigOpt = Path("marrow.toml"),
    verbose: VerboseOpt = False,
    json_logs: JsonLogsOpt = False,
    ipc: IpcOpt = None,
) -> None:
    """Run all agents in a persistent heartbeat loop."""
    setup_logging(verbose=verbose, json_logs=json_logs)
    root = _load_root_or_exit(config)
    if root.service.mode == "supervisor":
        asyncio.run(_run_supervisor(config, ipc=ipc))
        return
    asyncio.run(_run_single_user(config, ipc=ipc))


@app.command(name="run-once")
def run_once(
    config: ConfigOpt = Path("marrow.toml"),
    verbose: VerboseOpt = False,
    json_logs: JsonLogsOpt = False,
) -> None:
    """Execute one tick per agent then exit."""
    _run_single_user_command(config, verbose, json_logs, once=True)


@app.command(name="dry-run")
def dry_run(
    config: ConfigOpt = Path("marrow.toml"),
    verbose: VerboseOpt = False,
    json_logs: JsonLogsOpt = False,
) -> None:
    """Build and print prompts without running agents."""
    _run_single_user_command(config, verbose, json_logs, once=True, dry_run=True)


@app.command(name="worker-run", hidden=True)
def worker_run(
    config: ConfigOpt = Path("marrow.toml"),
    agents: Annotated[
        list[str] | None, typer.Option("--agent", help="Agent names for this worker")
    ] = None,
    status_file: Annotated[
        Path | None, typer.Option("--status-file", help="Worker status file")
    ] = None,
    request_dir: Annotated[
        Path | None, typer.Option("--request-dir", help="Worker control request directory")
    ] = None,
    verbose: VerboseOpt = False,
    json_logs: JsonLogsOpt = False,
) -> None:
    """Run one grouped worker under the target user identity."""
    setup_logging(verbose=verbose, json_logs=json_logs)
    if not agents:
        typer.echo("at least one --agent is required", err=True)
        raise typer.Exit(code=2)
    if status_file is None or request_dir is None:
        typer.echo("--status-file and --request-dir are required", err=True)
        raise typer.Exit(code=2)
    asyncio.run(
        _run_worker(
            config,
            agent_names=tuple(agents),
            status_file=status_file,
            request_dir=request_dir,
        )
    )


@app.command()
def setup(
    config: ConfigOpt = Path("marrow.toml"),
    verbose: VerboseOpt = False,
) -> None:
    """Initialize workspace dirs and cast roles into runtime agent configs."""
    setup_logging(verbose=verbose)
    root = load_config(config)
    if root.service.mode == "supervisor":
        ensure_service_runtime_dirs(root)
        typer.echo(f"OK: supervisor runtime ready at {resolve_service_runtime_root(root)}")
        return
    for agent in root.agents:
        if not verify_workspace(agent.workspace):
            typer.echo(f"FAIL: workspace invalid for {agent.name}", err=True)
            continue
        ensure_workspace_dirs(agent.workspace)
        cast_roles_to_workspace(root.core_dir, agent.workspace)
        typer.echo(f"OK: {agent.name} workspace ready at {agent.workspace}")


@app.command()
def validate(
    config: ConfigOpt = Path("marrow.toml"),
    verbose: VerboseOpt = False,
) -> None:
    """Check config and show summary."""
    setup_logging(verbose=verbose)
    try:
        root = load_config(config)
    except Exception as exc:
        typer.echo(f"FAIL: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if not root.agents:
        typer.echo("FAIL: no agents configured", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"Service mode: {root.service.mode}")
    for agent in root.agents:
        typer.echo(f"\n  Agent: {agent.name}")
        typer.echo(f"    interval : {agent.heartbeat_interval}s")
        typer.echo(f"    timeout  : {agent.heartbeat_timeout}s")
        typer.echo(f"    command  : {agent.agent_command}")
        typer.echo(f"    workspace: {agent.workspace}")
        if agent.run_as_user:
            typer.echo(f"    run_as   : {agent.run_as_user}")
        if agent.home:
            typer.echo(f"    home     : {agent.home}")
        typer.echo(f"    ctx_dirs : {agent.context_dirs}")
    typer.echo("\nVALIDATE OK")


@app.command()
def doctor(
    config: ConfigOpt = Path("marrow.toml"),
) -> None:
    """Check workspace, context scripts, and agent command availability."""
    try:
        root = load_config(config)
    except Exception as exc:
        typer.echo(f"FAIL config: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    issues: list[str] = []

    for agent in root.agents:
        typer.echo(f"\n[{agent.name}]")

        # Workspace
        ws = Path(agent.workspace)
        if not ws.is_dir():
            issues.append(f"{agent.name}: workspace missing: {ws}")
            typer.echo(f"  ✗ workspace: {ws} (missing)")
        elif not os.access(ws, os.W_OK):
            issues.append(f"{agent.name}: workspace not writable: {ws}")
            typer.echo(f"  ✗ workspace: {ws} (not writable)")
        else:
            typer.echo(f"  ✓ workspace: {ws}")

        # Context dirs and scripts
        for d in agent.context_dirs:
            dp = Path(d)
            if not dp.is_dir():
                issues.append(f"{agent.name}: context dir missing: {d}")
                typer.echo(f"  ✗ context dir: {d} (missing)")
                continue
            typer.echo(f"  ✓ context dir: {d}")
            for script in sorted(dp.iterdir()):
                if script.is_file() and not os.access(script, os.X_OK):
                    issues.append(f"{agent.name}: not executable: {script.name}")
                    typer.echo(f"    ✗ {script.name} (not executable)")
                elif script.is_file():
                    typer.echo(f"    ✓ {script.name}")

        # Agent command binary
        cmd_parts = shlex.split(agent.agent_command)
        if cmd_parts:
            binary = cmd_parts[0]
            found = shutil.which(binary) or Path(binary).is_file()
            if not found:
                issues.append(f"{agent.name}: command not found: {binary}")
                typer.echo(f"  ✗ command: {binary} (not found)")
            else:
                typer.echo(f"  ✓ command: {binary}")

    typer.echo("")
    if issues:
        typer.echo(f"DOCTOR: {len(issues)} issue(s) found:", err=True)
        for issue in issues:
            typer.echo(f"  - {issue}", err=True)
        raise typer.Exit(code=1)
    typer.echo("DOCTOR OK")


# ---------------------------------------------------------------------------
# IPC client helpers — used by `marrow status` and `marrow task` commands
# ---------------------------------------------------------------------------


async def _ipc_request(socket_path: str, method: str, path: str, body: str = "") -> dict:
    """Send an HTTP request to the IPC socket and return parsed JSON."""
    reader, writer = await asyncio.open_unix_connection(socket_path)
    req = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\n"
    if body:
        req += f"Content-Length: {len(body)}\r\n"
    req += "\r\n"
    if body:
        req += body
    writer.write(req.encode())
    await writer.drain()
    resp = await asyncio.wait_for(reader.read(65536), timeout=5)
    writer.close()
    await writer.wait_closed()
    text = resp.decode("utf-8", errors="replace")
    # Extract JSON body after the blank line
    idx = text.find("\r\n\r\n")
    json_str = text[idx + 4 :] if idx >= 0 else text
    return json.loads(json_str)


def _get_socket(config: Path) -> str:
    """Resolve the IPC socket path from config."""
    root = load_config(config)
    return resolve_socket_path(root)


def _require_socket(config: Path) -> str:
    sock = _get_socket(config)
    if not Path(sock).exists():
        typer.echo(f"socket not found: {sock} (is marrow running with --ipc?)", err=True)
        raise typer.Exit(code=1)
    return sock


def _run_ipc_command(config: Path, method: str, path: str, body: str = "") -> dict:
    sock = _require_socket(config)
    try:
        return asyncio.run(_ipc_request(sock, method, path, body))
    except Exception as exc:
        typer.echo(f"failed to connect: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command(name="scaffold")
def scaffold_cmd(
    workspace: Annotated[Path, typer.Option("--workspace", help="Workspace root to scaffold")],
    config_out: Annotated[
        Path, typer.Option("--config-out", help="Where to write starter marrow.toml")
    ],
    core_dir: Annotated[
        str, typer.Option("--core-dir", help="Core directory to reference in config")
    ] = "/opt/marrow-core",
    source_context_dir: Annotated[
        Path | None,
        typer.Option(
            "--source-context-dir", help="Optional default context.d to copy into workspace"
        ),
    ] = None,
) -> None:
    """Create a workspace skeleton and a starter config file."""
    scaffold_workspace(workspace, source_context_dir=source_context_dir)
    write_config_template(config_out, core_dir=core_dir, workspace=workspace)
    typer.echo(f"scaffolded workspace: {workspace}")
    typer.echo(f"wrote config: {config_out}")


@app.command(name="install-service")
def install_service(
    config: ConfigOpt = Path("marrow.toml"),
    output_dir: Annotated[
        Path, typer.Option("--output-dir", help="Directory to write service files into")
    ] = Path("service-out"),
    platform: Annotated[str, typer.Option("--platform", help="auto, darwin, or linux")] = "auto",
) -> None:
    """Render service definitions for launchd or systemd into an output directory."""
    root = load_config(config)
    if not root.agents:
        typer.echo("FAIL: no agents configured", err=True)
        raise typer.Exit(code=2)
    files = render_service_files(
        platform=platform,
        core_dir=root.core_dir,
        config_path=config.resolve(),
        service_user=resolve_service_user(root),
        log_dir=resolve_service_log_dir(root),
    )
    written = write_service_files(files, output_dir)
    typer.echo(f"rendered {len(written)} service file(s) to {output_dir}")
    for path in written:
        typer.echo(f"  {path.name}")


@app.command(name="sync-once")
def sync_once(
    config: ConfigOpt = Path("marrow.toml"),
    verbose: VerboseOpt = False,
) -> None:
    """Run one bounded sync attempt and return a structured result code."""
    setup_logging(verbose=verbose)
    root = load_config(config)
    if not root.agents:
        typer.echo("FAIL: no agents configured", err=True)
        raise typer.Exit(code=2)
    workspace = root.agents[0].workspace
    try:
        outcome = run_sync_once(
            core_dir=root.core_dir,
            workspace=workspace,
            state_file=Path(resolve_sync_state_path(root)),
            lock_file=Path(resolve_sync_lock_path(root)),
            refresh_workspace=root.service.mode != "supervisor",
        )
    except SyncError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps({"result": outcome.result.value, "reason": outcome.reason}))
    raise typer.Exit(code=outcome.exit_code)


@app.command()
def status(
    config: ConfigOpt = Path("marrow.toml"),
) -> None:
    """Query heartbeat status via IPC socket."""
    data = _run_ipc_command(config, "GET", "/status")
    typer.echo(json.dumps(data, indent=2))


@app.command()
def wake(
    agent: Annotated[str, typer.Argument(help="Configured agent name to wake immediately")],
    config: ConfigOpt = Path("marrow.toml"),
    reason: Annotated[str, typer.Option("--reason", help="Optional wake reason")] = "",
) -> None:
    """Wake one configured agent early via IPC."""
    data = _run_ipc_command(
        config,
        "POST",
        "/wake",
        json.dumps({"agent": agent, "reason": reason}),
    )
    if data.get("ok"):
        typer.echo(f'wake submitted for "{agent}"')
        return
    typer.echo(f"❌ {data.get('error', 'unknown error')}", err=True)
    raise typer.Exit(code=1)


# Task subcommand group
task_app = typer.Typer(help="Manage tasks via IPC.")
app.add_typer(task_app, name="task")


@task_app.command("add")
def task_add(
    title: Annotated[str, typer.Argument(help="Task title")],
    body: Annotated[str, typer.Option("--body", "-b", help="Task description")] = "",
    config: ConfigOpt = Path("marrow.toml"),
) -> None:
    """Submit a new task to the queue."""
    payload = json.dumps({"title": title, "body": body})
    data = _run_ipc_command(config, "POST", "/tasks", payload)
    if data.get("ok"):
        typer.echo(f"✅ task submitted: {data.get('file', '')}")
    else:
        typer.echo(f"❌ {data.get('error', 'unknown error')}", err=True)
        raise typer.Exit(code=1)


@task_app.command("list")
def task_list(
    config: ConfigOpt = Path("marrow.toml"),
) -> None:
    """List tasks in the queue."""
    data = _run_ipc_command(config, "GET", "/tasks")
    tasks = data.get("tasks", [])
    if not tasks:
        typer.echo("(no tasks in queue)")
        return
    for t in tasks:
        typer.echo(f"  {t.get('file', '?')}  {t.get('title', '?')}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
