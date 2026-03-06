"""CLI entry point — run, run-once, dry-run, validate, setup."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from marrow_core.config import load_config
from marrow_core.heartbeat import heartbeat
from marrow_core.log import setup_logging
from marrow_core.workspace import ensure_workspace_dirs, sync_agent_symlinks, verify_workspace

app = typer.Typer(add_completion=False, help="marrow-core: self-evolving agent scheduler.")

# Shared option types
ConfigOpt = Annotated[Path, typer.Option("--config", "-c", help="Path to marrow.toml")]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logging")]
JsonLogsOpt = Annotated[bool, typer.Option("--json-logs", help="Emit JSON log records")]


async def _run(config: Path, *, once: bool = False, dry_run: bool = False) -> None:
    if not config.is_file():
        typer.echo(f"config not found: {config}", err=True)
        raise typer.Exit(code=1)
    root = load_config(config)
    if not root.agents:
        typer.echo("no agents configured", err=True)
        raise typer.Exit(code=1)
    tasks = [
        asyncio.create_task(
            heartbeat(agent, root.core_dir, once=once, dry_run=dry_run),
            name=agent.name,
        )
        for agent in root.agents
    ]
    await asyncio.gather(*tasks)


def _run_heartbeat(
    config: Path,
    verbose: bool,
    json_logs: bool,
    *,
    once: bool = False,
    dry_run: bool = False,
) -> None:
    """Shared logic for run / run-once / dry-run commands."""
    setup_logging(verbose=verbose, json_logs=json_logs)
    asyncio.run(_run(config, once=once, dry_run=dry_run))


@app.command()
def run(
    config: ConfigOpt = Path("marrow.toml"),
    verbose: VerboseOpt = False,
    json_logs: JsonLogsOpt = False,
) -> None:
    """Run all agents in a persistent heartbeat loop."""
    _run_heartbeat(config, verbose, json_logs)


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
) -> None:
    """Check config and show summary."""
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
