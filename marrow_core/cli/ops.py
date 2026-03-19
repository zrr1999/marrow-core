"""Unified operational commands."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
from pathlib import Path

import typer

from marrow_core.cli.common import (
    ConfigOpt,
    VerboseOpt,
    ipc_request,
    load_root_or_exit,
    sync_workspace,
)
from marrow_core.config import load_config
from marrow_core.log import setup_logging
from marrow_core.plugin_host import render_plugin_service_files, write_plugin_manifest
from marrow_core.runtime import (
    ensure_service_runtime_dirs,
    primary_workspace,
    resolve_service_log_dir,
    resolve_service_runtime_root,
    resolve_service_user,
    resolve_socket_path,
)
from marrow_core.scaffold import scaffold_workspace, write_config_template
from marrow_core.services import (
    render_service_files,
    resolve_service_config_path,
    write_service_files,
)
from marrow_core.workspace import profile_source_context_dir, verify_workspace

app = typer.Typer(help="Unified operational command surface.")


def get_socket(config: Path) -> str:
    root = load_config(config)
    return resolve_socket_path(root)


def require_socket(config: Path) -> str:
    sock = get_socket(config)
    if not Path(sock).exists():
        typer.echo(f"socket not found: {sock} (is marrow running with IPC enabled?)", err=True)
        raise typer.Exit(code=1)
    return sock


def run_ipc_command(config: Path, method: str, path: str, body: str = "") -> dict:
    sock = require_socket(config)
    try:
        return asyncio.run(ipc_request(sock, method, path, body))
    except Exception as exc:
        typer.echo(f"failed to connect: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _run_prepare(root) -> None:  # type: ignore[no-untyped-def]
    """Initialize runtime dirs and ensure configured workspaces exist."""
    if root.service.mode == "supervisor":
        ensure_service_runtime_dirs(root)
        typer.echo(f"OK: supervisor runtime ready at {resolve_service_runtime_root(root)}")
        return
    seen: set[str] = set()
    for agent in root.agents:
        if agent.workspace in seen:
            continue
        seen.add(agent.workspace)
        if Path(agent.workspace).exists() and not verify_workspace(agent.workspace):
            typer.echo(f"FAIL: workspace invalid for {agent.name}", err=True)
            continue
        try:
            sync_workspace(agent.workspace)
        except (RuntimeError, ValueError) as exc:
            typer.echo(f"FAIL: {exc}", err=True)
            continue
        typer.echo(f"OK: workspace ready at {agent.workspace}")


@app.command()
def install(
    config: ConfigOpt = Path("marrow.toml"),
    output_dir: Path = typer.Option(Path("service-out"), "--output-dir"),
    platform: str = typer.Option("auto", "--platform", help="auto, darwin, or linux"),
    prepare: bool = typer.Option(
        False, "--prepare", help="Initialize runtime dirs instead of rendering service files."
    ),
    verbose: VerboseOpt = False,
) -> None:
    """Render service definitions, or initialize runtime dirs with --prepare."""
    setup_logging(verbose=verbose)
    root = load_root_or_exit(config)
    if prepare:
        _run_prepare(root)
        return
    if not root.agents:
        typer.echo("FAIL: no agents configured", err=True)
        raise typer.Exit(code=2)
    files = render_service_files(
        platform=platform,
        core_dir=root.core_dir,
        service_config_path=resolve_service_config_path(platform, root.service.config_path),
        service_user=resolve_service_user(root),
        agent_home=root.agents[0].home,
        log_dir=resolve_service_log_dir(root),
    )
    workspace = primary_workspace(root)
    manifest_path: Path | None = None
    if root.plugins:
        if workspace is None:
            typer.echo("FAIL: plugin manifest requires a primary workspace", err=True)
            raise typer.Exit(code=2)
        manifest_path = write_plugin_manifest(
            root.plugins,
            workspace=workspace,
            destination=workspace / "runtime" / "plugins" / "manifest.json",
        )
        files.extend(
            render_plugin_service_files(
                platform=platform, plugins=root.plugins, workspace=workspace
            )
        )
    written = write_service_files(files, output_dir)
    typer.echo(f"rendered {len(written)} service file(s) to {output_dir}")
    for path in written:
        typer.echo(f"  {path.name}")
    if manifest_path is not None:
        typer.echo(f"wrote plugin manifest: {manifest_path}")


@app.command(deprecated=True)
def setup(config: ConfigOpt = Path("marrow.toml"), verbose: VerboseOpt = False) -> None:
    """[Deprecated] Use 'install --prepare' instead."""
    typer.echo("Deprecated: use 'install --prepare' instead of 'setup'.", err=True)
    setup_logging(verbose=verbose)
    root = load_root_or_exit(config)
    _run_prepare(root)


@app.command()
def validate(
    config: ConfigOpt = Path("marrow.toml"),
    verbose: VerboseOpt = False,
    doctor_flag: bool = typer.Option(
        False, "--doctor", help="Also run deep workspace health checks."
    ),
) -> None:
    """Check config and show summary. Use --doctor for deep health checks."""
    setup_logging(verbose=verbose)
    try:
        root = load_root_or_exit(config)
    except Exception as exc:
        typer.echo(f"FAIL: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if not root.agents:
        typer.echo("FAIL: no agents configured", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"Service mode: {root.service.mode}")
    if root.profile.root_dir:
        typer.echo(f"Profile root: {root.profile.root_dir}")
    for agent in root.agents:
        typer.echo(f"\n  Agent: {agent.name}")
        typer.echo(f"    interval : {agent.heartbeat_interval}s")
        typer.echo(f"    timeout  : {agent.heartbeat_timeout}s")
        typer.echo(f"    command  : {agent.agent_command}")
        typer.echo(f"    workspace: {agent.workspace}")
        if agent.user:
            typer.echo(f"    user     : {agent.user}")
        if agent.home:
            typer.echo(f"    home     : {agent.home}")
        typer.echo(f"    ctx_dirs : {agent.context_dirs}")
    typer.echo("\nVALIDATE OK")
    if doctor_flag:
        _run_doctor_checks(root)


def _run_doctor_checks(root) -> None:  # type: ignore[no-untyped-def]
    issues: list[str] = []
    for agent in root.agents:
        typer.echo(f"\n[{agent.name}]")
        ws = Path(agent.workspace)
        if not ws.is_dir():
            issues.append(f"{agent.name}: workspace missing: {ws}")
            typer.echo(f"  workspace: {ws} (missing)")
        elif not os.access(ws, os.W_OK):
            issues.append(f"{agent.name}: workspace not writable: {ws}")
            typer.echo(f"  workspace: {ws} (not writable)")
        else:
            typer.echo(f"  workspace: {ws}")

        for d in agent.context_dirs:
            dp = Path(d)
            if not dp.is_dir():
                issues.append(f"{agent.name}: context dir missing: {d}")
                typer.echo(f"  context dir: {d} (missing)")
                continue
            typer.echo(f"  context dir: {d}")
            for script in sorted(dp.iterdir()):
                if script.is_file() and not os.access(script, os.X_OK):
                    issues.append(f"{agent.name}: not executable: {script.name}")
                    typer.echo(f"    {script.name} (not executable)")
                elif script.is_file():
                    typer.echo(f"    {script.name}")

        cmd_parts = shlex.split(agent.agent_command)
        if cmd_parts:
            binary = cmd_parts[0]
            found = shutil.which(binary) or Path(binary).is_file()
            if not found:
                issues.append(f"{agent.name}: command not found: {binary}")
                typer.echo(f"  command: {binary} (not found)")
            else:
                typer.echo(f"  command: {binary}")

    typer.echo("")
    if issues:
        typer.echo(f"DOCTOR: {len(issues)} issue(s) found:", err=True)
        for issue in issues:
            typer.echo(f"  - {issue}", err=True)
        raise typer.Exit(code=1)
    typer.echo("DOCTOR OK")


@app.command(deprecated=True)
def doctor(config: ConfigOpt = Path("marrow.toml")) -> None:
    """[Deprecated] Use 'validate --doctor' instead."""
    typer.echo("Deprecated: use 'validate --doctor' instead of 'doctor'.", err=True)
    try:
        root = load_root_or_exit(config)
    except Exception as exc:
        typer.echo(f"FAIL config: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    _run_doctor_checks(root)


@app.command(name="scaffold")
def scaffold_cmd(
    workspace: Path = typer.Option(..., "--workspace", help="Workspace root to scaffold"),
    config_out: Path = typer.Option(..., "--config-out", help="Where to write starter marrow.toml"),
    core_dir: str = typer.Option("", "--core-dir", help="Core directory to reference in config"),
    source_context_dir: Path | None = typer.Option(
        None,
        "--source-context-dir",
        help="Optional default context.d to copy into workspace",
    ),
    profile_root: Path | None = typer.Option(
        None,
        "--profile-root",
        help="Optional external profile root for scaffold defaults",
    ),
) -> None:
    """Create a workspace skeleton and a starter config file."""
    if source_context_dir is None and profile_root is not None:
        resolved = profile_source_context_dir(str(profile_root))
        if resolved is not None and resolved.is_dir():
            source_context_dir = resolved
    scaffold_workspace(workspace, source_context_dir=source_context_dir)
    write_config_template(config_out, core_dir=core_dir, workspace=workspace)
    typer.echo(f"scaffolded workspace: {workspace}")
    typer.echo(f"wrote config: {config_out}")


@app.command(name="install-service", deprecated=True)
def install_service(
    config: ConfigOpt = Path("marrow.toml"),
    output_dir: Path = typer.Option(Path("service-out"), "--output-dir"),
    platform: str = typer.Option("auto", "--platform", help="auto, darwin, or linux"),
) -> None:
    """[Deprecated] Use 'install' instead."""
    typer.echo("Deprecated: use 'install' instead of 'install-service'.", err=True)
    root = load_root_or_exit(config)
    if not root.agents:
        typer.echo("FAIL: no agents configured", err=True)
        raise typer.Exit(code=2)
    files = render_service_files(
        platform=platform,
        core_dir=root.core_dir,
        service_config_path=resolve_service_config_path(platform, root.service.config_path),
        service_user=resolve_service_user(root),
        agent_home=root.agents[0].home,
        log_dir=resolve_service_log_dir(root),
    )
    workspace = primary_workspace(root)
    manifest_path: Path | None = None
    if root.plugins:
        if workspace is None:
            typer.echo("FAIL: plugin manifest requires a primary workspace", err=True)
            raise typer.Exit(code=2)
        manifest_path = write_plugin_manifest(
            root.plugins,
            workspace=workspace,
            destination=workspace / "runtime" / "plugins" / "manifest.json",
        )
        files.extend(
            render_plugin_service_files(
                platform=platform, plugins=root.plugins, workspace=workspace
            )
        )
    written = write_service_files(files, output_dir)
    typer.echo(f"rendered {len(written)} service file(s) to {output_dir}")
    for path in written:
        typer.echo(f"  {path.name}")
    if manifest_path is not None:
        typer.echo(f"wrote plugin manifest: {manifest_path}")


@app.command()
def status(config: ConfigOpt = Path("marrow.toml")) -> None:
    """Pretty-print runtime state via IPC."""
    data = run_ipc_command(config, "GET", "/status")
    typer.echo(json.dumps(data, indent=2))


@app.command()
def wake(
    agent: str = typer.Argument(help="Configured agent name to wake immediately"),
    config: ConfigOpt = Path("marrow.toml"),
    reason: str = typer.Option("", "--reason", help="Optional wake reason"),
    prompt: str = typer.Option("", "--prompt", help="One-shot prompt for the next run"),
) -> None:
    """Wake one configured agent early via IPC."""
    data = run_ipc_command(
        config,
        "POST",
        "/wake",
        json.dumps({"agent": agent, "reason": reason, "prompt": prompt}),
    )
    if data.get("ok"):
        typer.echo(f'wake submitted for "{agent}"')
        return
    typer.echo(f"FAIL: {data.get('error', 'unknown error')}", err=True)
    raise typer.Exit(code=1)
