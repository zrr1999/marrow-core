"""CLI entry point — run, run-once, dry-run, validate, setup, doctor, status, task."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
from pathlib import Path
from typing import Annotated

import typer

from marrow_core.config import load_config
from marrow_core.heartbeat import HeartbeatState, heartbeat
from marrow_core.ipc import start_ipc_server
from marrow_core.log import setup_logging
from marrow_core.runtime import resolve_socket_path, resolve_task_dir
from marrow_core.scaffold import scaffold_workspace, write_config_template
from marrow_core.services import render_service_files, write_service_files
from marrow_core.workspace import ensure_workspace_dirs, sync_agent_symlinks, verify_workspace

app = typer.Typer(add_completion=False, help="marrow-core: self-evolving agent scheduler.")

# Shared option types
ConfigOpt = Annotated[Path, typer.Option("--config", "-c", help="Path to marrow.toml")]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logging")]
JsonLogsOpt = Annotated[bool, typer.Option("--json-logs", help="Emit JSON log records")]
IpcOpt = Annotated[
    bool | None, typer.Option("--ipc/--no-ipc", help="Override IPC server (default: from config)")
]


async def _run(
    config: Path, *, once: bool = False, dry_run: bool = False, ipc: bool | None = None
) -> None:
    if not config.is_file():
        typer.echo(f"config not found: {config}", err=True)
        raise typer.Exit(code=1)
    root = load_config(config)
    if not root.agents:
        typer.echo("no agents configured", err=True)
        raise typer.Exit(code=1)

    state = HeartbeatState()

    # Determine whether to start IPC server
    ipc_enabled = ipc if ipc is not None else root.ipc.enabled
    server = None
    if ipc_enabled and not dry_run:
        socket_path = resolve_socket_path(root)
        task_dir = resolve_task_dir(root)
        server = await start_ipc_server(socket_path, task_dir, state)

    tasks = [
        asyncio.create_task(
            heartbeat(agent, root.core_dir, once=once, dry_run=dry_run, state=state),
            name=agent.name,
        )
        for agent in root.agents
    ]
    try:
        await asyncio.gather(*tasks)
    finally:
        if server is not None:
            server.close()
            await server.wait_closed()
            # Clean up socket file
            sock = Path(resolve_socket_path(root))
            if sock.exists():
                sock.unlink()


def _run_heartbeat(
    config: Path,
    verbose: bool,
    json_logs: bool,
    *,
    once: bool = False,
    dry_run: bool = False,
    ipc: bool | None = None,
) -> None:
    """Shared logic for run / run-once / dry-run commands."""
    setup_logging(verbose=verbose, json_logs=json_logs)
    asyncio.run(_run(config, once=once, dry_run=dry_run, ipc=ipc))


@app.command()
def run(
    config: ConfigOpt = Path("marrow.toml"),
    verbose: VerboseOpt = False,
    json_logs: JsonLogsOpt = False,
    ipc: IpcOpt = None,
) -> None:
    """Run all agents in a persistent heartbeat loop."""
    _run_heartbeat(config, verbose, json_logs, ipc=ipc)


@app.command(name="run-once")
def run_once(
    config: ConfigOpt = Path("marrow.toml"),
    verbose: VerboseOpt = False,
    json_logs: JsonLogsOpt = False,
) -> None:
    """Execute one tick per agent then exit."""
    _run_heartbeat(config, verbose, json_logs, once=True)


@app.command(name="dry-run")
def dry_run(
    config: ConfigOpt = Path("marrow.toml"),
    verbose: VerboseOpt = False,
    json_logs: JsonLogsOpt = False,
) -> None:
    """Build and print prompts without running agents."""
    _run_heartbeat(config, verbose, json_logs, once=True, dry_run=True)


@app.command()
def setup(
    config: ConfigOpt = Path("marrow.toml"),
    verbose: VerboseOpt = False,
) -> None:
    """Initialize workspace dirs and sync agent symlinks."""
    setup_logging(verbose=verbose)
    root = load_config(config)
    for agent in root.agents:
        if not verify_workspace(agent.workspace):
            typer.echo(f"FAIL: workspace invalid for {agent.name}", err=True)
            continue
        ensure_workspace_dirs(agent.workspace)
        sync_agent_symlinks(root.core_dir, agent.workspace)
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
    for agent in root.agents:
        typer.echo(f"\n  Agent: {agent.name}")
        typer.echo(f"    interval : {agent.heartbeat_interval}s")
        typer.echo(f"    timeout  : {agent.heartbeat_timeout}s")
        typer.echo(f"    command  : {agent.agent_command}")
        typer.echo(f"    workspace: {agent.workspace}")
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
        workspace=root.agents[0].workspace,
    )
    written = write_service_files(files, output_dir)
    typer.echo(f"rendered {len(written)} service file(s) to {output_dir}")
    for path in written:
        typer.echo(f"  {path.name}")


@app.command()
def status(
    config: ConfigOpt = Path("marrow.toml"),
) -> None:
    """Query heartbeat status via IPC socket."""
    data = _run_ipc_command(config, "GET", "/status")
    typer.echo(json.dumps(data, indent=2))


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
