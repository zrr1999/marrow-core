"""Service/runtime command surface."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path

import typer
from loguru import logger

from marrow_core.cli.common import (
    ConfigOpt,
    IpcOpt,
    JsonLogsOpt,
    VerboseOpt,
    load_root_or_exit,
    sync_workspace,
)
from marrow_core.health import collect_health_issues
from marrow_core.heartbeat import HeartbeatState, heartbeat
from marrow_core.ipc import start_ipc_server
from marrow_core.log import setup_logging
from marrow_core.runtime import (
    ensure_service_runtime_dirs,
    marrow_binary,
    resolve_service_runtime_root,
    resolve_socket_path,
    resolve_sync_lock_path,
    resolve_sync_state_path,
)
from marrow_core.sync import SyncError, SyncOutcome, SyncResult, run_sync_once
from marrow_core.triggers import TriggerMailbox
from marrow_core.worker import (
    SupervisorState,
    WorkerSpec,
    build_worker_command,
    build_worker_env,
    build_worker_preexec,
    create_wake_request,
    drain_worker_triggers,
    group_agents_by_worker,
    prepare_worker_runtime_paths,
    publish_worker_state,
    worker_request_dir,
)

app = typer.Typer(help="Long-running service/runtime commands.")


class _WorkerTriggerProxy:
    def __init__(self, request_dir: Path, agent_name: str) -> None:
        self._request_dir = request_dir
        self._agent_name = agent_name

    def trigger(self, reason: str = "", prompt: str = "") -> None:
        create_wake_request(self._request_dir, self._agent_name, reason, prompt)


async def _prepare_worker_workspace(config: Path, root, spec: WorkerSpec) -> None:
    if os.geteuid() == 0 and spec.user:
        proc = await asyncio.create_subprocess_exec(
            marrow_binary(root.core_dir),
            "service",
            "workspace-sync",
            "--config",
            str(config.resolve()),
            "--workspace",
            spec.workspace,
            cwd=str(config.resolve().parent),
            env=build_worker_env(spec),
            preexec_fn=build_worker_preexec(spec),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if stdout_text:
            logger.info("workspace prepare [{}]: {}", spec.worker_id, stdout_text)
        if stderr_text:
            logger.warning("workspace prepare [{}]: {}", spec.worker_id, stderr_text)
        if proc.returncode != 0:
            message = stderr_text or stdout_text or "workspace prepare failed"
            raise RuntimeError(message)
        return
    sync_workspace(spec.workspace)


def _self_check_prompt(agent_name: str, issues: list[str]) -> str:
    lines = [
        f"Run `{agent_name}` in repair mode and resolve the following core health issues.",
        "",
        "Observed issues:",
    ]
    lines.extend(f"- {issue}" for issue in issues)
    return "\n".join(lines) + "\n"


def _wake_agent(
    trigger_mailboxes: dict[str, TriggerMailbox | _WorkerTriggerProxy],
    agent_name: str,
    *,
    reason: str,
    prompt: str = "",
) -> bool:
    mailbox = trigger_mailboxes.get(agent_name)
    if mailbox is None:
        logger.warning('wake requested for unknown agent "{}" ({})', agent_name, reason)
        return False
    mailbox.trigger(reason=reason, prompt=prompt)
    logger.info('wake requested for "{}" ({})', agent_name, reason)
    return True


async def _self_check_supervisor(root, trigger_mailboxes) -> None:
    last_failure_signature = ""
    while True:
        issues = collect_health_issues(root)
        if issues:
            signature = "\n".join(issues)
            if signature != last_failure_signature:
                _wake_agent(
                    trigger_mailboxes,
                    root.self_check.wake_agent,
                    reason="core self-check",
                    prompt=_self_check_prompt(root.self_check.wake_agent, issues),
                )
                logger.warning("core self-check failed with {} issue(s)", len(issues))
                last_failure_signature = signature
        else:
            last_failure_signature = ""
        await asyncio.sleep(root.self_check.interval_seconds)


async def _worker_status_publisher(
    *, status_file: Path, spec: WorkerSpec, state: HeartbeatState, interval: int = 5
) -> None:
    while True:
        publish_worker_state(
            status_file,
            {
                "worker_id": spec.worker_id,
                "user": spec.user,
                "group": spec.group,
                "home": spec.home,
                "workspace": spec.workspace,
                "agents": spec.agent_names,
                "pid": os.getpid(),
                "state": state.to_dict(),
            },
        )
        await asyncio.sleep(interval)


async def _worker_request_poller(
    *, request_dir: Path, trigger_mailboxes: dict[str, TriggerMailbox], interval: int = 1
) -> None:
    while True:
        drain_worker_triggers(request_dir, trigger_mailboxes)
        await asyncio.sleep(interval)


async def _run_single_user(
    config: Path, *, once: bool = False, dry_run: bool = False, ipc: bool | None = None
) -> None:
    root = load_root_or_exit(config)
    if not root.agents:
        typer.echo("no agents configured", err=True)
        raise typer.Exit(code=1)

    state = HeartbeatState()
    trigger_mailboxes = {agent.name: TriggerMailbox() for agent in root.agents}
    ipc_enabled = ipc if ipc is not None else root.ipc.enabled
    server = None
    if ipc_enabled and not dry_run:
        server = await start_ipc_server(resolve_socket_path(root), state, trigger_mailboxes)

    tasks = [
        asyncio.create_task(
            heartbeat(
                agent,
                root.profile,
                once=once,
                dry_run=dry_run,
                state=state,
                trigger_mailbox=trigger_mailboxes[agent.name],
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
            _self_check_supervisor(root, trigger_mailboxes),
            name="self-check-supervisor",
        )
        tasks.append(self_check_task)
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in (sync_task, self_check_task):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        if server is not None:
            server.close()
            await server.wait_closed()
            sock = Path(resolve_socket_path(root))
            if sock.exists():
                sock.unlink()


async def _run_worker(
    config: Path,
    *,
    agent_names: tuple[str, ...],
    status_file: Path,
    request_dir: Path,
) -> None:
    root = load_root_or_exit(config)
    selected_names = set(agent_names)
    selected = [agent for agent in root.agents if agent.name in selected_names]
    if not selected:
        typer.echo("no agents selected", err=True)
        raise typer.Exit(code=2)

    specs = group_agents_by_worker(root.model_copy(update={"agents": selected}, deep=True))
    if len(specs) != 1:
        typer.echo("selected agents must map to exactly one worker", err=True)
        raise typer.Exit(code=2)
    spec = specs[0]

    state = HeartbeatState()
    trigger_mailboxes = {agent.name: TriggerMailbox() for agent in selected}
    tasks = [
        asyncio.create_task(
            heartbeat(
                agent,
                root.profile,
                state=state,
                trigger_mailbox=trigger_mailboxes[agent.name],
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
        _worker_request_poller(request_dir=request_dir, trigger_mailboxes=trigger_mailboxes),
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
                "user": spec.user,
                "workspace": spec.workspace,
                "agents": spec.agent_names,
                "pid": os.getpid(),
                "stopped": True,
                "state": state.to_dict(),
            },
        )


async def _spawn_worker_process(config: Path, root, spec: WorkerSpec):
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


def _supervisor_trigger_mailboxes(root) -> dict[str, _WorkerTriggerProxy]:
    runtime_root = Path(resolve_service_runtime_root(root))
    mailboxes: dict[str, _WorkerTriggerProxy] = {}
    for spec in group_agents_by_worker(root):
        request_dir = worker_request_dir(runtime_root, spec)
        for agent_name in spec.agent_names:
            mailboxes[agent_name] = _WorkerTriggerProxy(request_dir, agent_name)
    return mailboxes


async def _run_supervisor(config: Path, *, ipc: bool | None = None) -> None:
    root = load_root_or_exit(config)
    if not root.agents:
        typer.echo("no agents configured", err=True)
        raise typer.Exit(code=1)

    ensure_service_runtime_dirs(root)
    runtime_root = Path(resolve_service_runtime_root(root))
    state = SupervisorState(runtime_root)
    trigger_mailboxes = _supervisor_trigger_mailboxes(root)
    ipc_enabled = ipc if ipc is not None else root.ipc.enabled
    server = None
    if ipc_enabled:
        server = await start_ipc_server(resolve_socket_path(root), state, trigger_mailboxes)

    worker_specs = group_agents_by_worker(root)
    processes = {}
    for spec in worker_specs:
        await _prepare_worker_workspace(config, root, spec)
        processes[spec.worker_id] = await _spawn_worker_process(config, root, spec)
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
            _self_check_supervisor(root, trigger_mailboxes),
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


async def _reload_runtime(config: Path, root) -> None:
    for spec in group_agents_by_worker(root):
        await _prepare_worker_workspace(config, root, spec)


async def _invoke_sync_once(root, *, config_path: Path | None = None) -> SyncOutcome:
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
            service_config_path=str(config_path) if config_path is not None else "",
            rules_path=root.profile.rules_path,
        )
    except SyncError as exc:
        return SyncOutcome(SyncResult.FAILED, str(exc))


async def _sync_supervisor(config: Path) -> None:
    while True:
        root = load_root_or_exit(config)
        outcome = await _invoke_sync_once(root, config_path=config)
        if outcome.result is SyncResult.NOOP:
            await asyncio.sleep(root.sync.interval_seconds)
            continue
        if outcome.result is SyncResult.RELOADED:
            await _reload_runtime(config, root)
            await asyncio.sleep(root.sync.interval_seconds)
            continue
        if outcome.result is SyncResult.RESTART_REQUIRED:
            if os.getenv("MARROW_RESTART_HEART_AFTER_SYNC") == "1":
                logger.info("sync requested restart; exiting for service manager restart")
                raise typer.Exit(code=0)
            logger.info(
                "sync requested restart but skipped it; "
                "set MARROW_RESTART_HEART_AFTER_SYNC=1 to enable"
            )
            await asyncio.sleep(root.sync.interval_seconds)
            continue
        await asyncio.sleep(root.sync.failure_backoff_seconds)


@app.command()
def run(
    config: ConfigOpt = Path("marrow.toml"),
    verbose: VerboseOpt = False,
    json_logs: JsonLogsOpt = False,
    ipc: IpcOpt = None,
    once: bool = typer.Option(False, "--once", help="Execute one tick then exit."),
    dry_run_flag: bool = typer.Option(
        False, "--dry-run", help="Build and print prompts without running agents."
    ),
) -> None:
    """Run the scheduler service.

    Use --once to execute a single tick per agent then exit.
    Use --dry-run to build prompts without running agents.
    """
    setup_logging(verbose=verbose, json_logs=json_logs)
    if dry_run_flag:
        asyncio.run(_run_single_user(config, once=True, dry_run=True))
        return
    if once:
        asyncio.run(_run_single_user(config, once=True))
        return
    root = load_root_or_exit(config)
    if root.service.mode == "supervisor":
        asyncio.run(_run_supervisor(config, ipc=ipc))
        return
    asyncio.run(_run_single_user(config, ipc=ipc))


@app.command(name="run-once", deprecated=True)
def run_once(
    config: ConfigOpt = Path("marrow.toml"),
    verbose: VerboseOpt = False,
    json_logs: JsonLogsOpt = False,
) -> None:
    """[Deprecated] Use 'run --once' instead."""
    typer.echo("Deprecated: use 'run --once' instead of 'run-once'.", err=True)
    setup_logging(verbose=verbose, json_logs=json_logs)
    asyncio.run(_run_single_user(config, once=True))


@app.command(name="dry-run", deprecated=True)
def dry_run(
    config: ConfigOpt = Path("marrow.toml"),
    verbose: VerboseOpt = False,
    json_logs: JsonLogsOpt = False,
) -> None:
    """[Deprecated] Use 'run --dry-run' instead."""
    typer.echo("Deprecated: use 'run --dry-run' instead of 'dry-run'.", err=True)
    setup_logging(verbose=verbose, json_logs=json_logs)
    asyncio.run(_run_single_user(config, once=True, dry_run=True))


@app.command(name="worker-run", hidden=True)
def worker_run(
    config: ConfigOpt = Path("marrow.toml"),
    agents: list[str] | None = typer.Option(None, "--agent", help="Agent names for this worker"),
    status_file: Path | None = typer.Option(None, "--status-file", help="Worker status file"),
    request_dir: Path | None = typer.Option(
        None, "--request-dir", help="Worker control request directory"
    ),
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


@app.command(name="workspace-sync", hidden=True)
def workspace_sync(
    workspace: Path = typer.Option(..., "--workspace", help="Workspace to prepare"),
    config: ConfigOpt = Path("marrow.toml"),
    verbose: VerboseOpt = False,
    json_logs: JsonLogsOpt = False,
) -> None:
    """Ensure workspace dirs exist."""
    setup_logging(verbose=verbose, json_logs=json_logs)
    root = load_root_or_exit(config)
    workspace_str = str(workspace)
    if not any(agent.workspace == workspace_str for agent in root.agents):
        typer.echo(f"workspace not configured: {workspace_str}", err=True)
        raise typer.Exit(code=2)
    try:
        sync_workspace(workspace_str)
    except (RuntimeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo("workspace sync ok: ensured workspace directories only")


@app.command(name="sync-once")
def sync_once(config: ConfigOpt = Path("marrow.toml"), verbose: VerboseOpt = False) -> None:
    """Run one bounded sync attempt and return a structured result code."""
    setup_logging(verbose=verbose)
    root = load_root_or_exit(config)
    if not root.agents:
        typer.echo("FAIL: no agents configured", err=True)
        raise typer.Exit(code=2)
    try:
        outcome = run_sync_once(
            core_dir=root.core_dir,
            workspace=root.agents[0].workspace,
            state_file=Path(resolve_sync_state_path(root)),
            lock_file=Path(resolve_sync_lock_path(root)),
            refresh_workspace=root.service.mode != "supervisor",
            service_config_path=str(config),
            rules_path=root.profile.rules_path,
        )
    except SyncError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps({"result": outcome.result.value, "reason": outcome.reason}))
    raise typer.Exit(code=outcome.exit_code)
