"""CLI entry point — minimal surface: run, run-once, dry-run, validate, setup."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer

from marrow_core.config import load_config
from marrow_core.heartbeat import heartbeat
from marrow_core.log import setup_logging
from marrow_core.sandbox import (
    ensure_workspace_dirs,
    sync_agent_symlinks,
    verify_workspace,
)

app = typer.Typer(
    add_completion=False, help="marrow-core: self-evolving agent scheduler."
)


def _default_config() -> Path:
    return Path("marrow.toml")


async def _run(config: Path, *, once: bool = False, dry_run: bool = False) -> None:
    if not config.is_file():
        typer.echo(f"config not found: {config}", err=True)
        raise SystemExit(1)

    root = load_config(config)
    if not root.agents:
        typer.echo("no agents configured", err=True)
        raise SystemExit(1)

    tasks = [
        asyncio.create_task(
            heartbeat(agent, root.core_dir, once=once, dry_run=dry_run),
            name=agent.name,
        )
        for agent in root.agents
    ]
    await asyncio.gather(*tasks)


@app.callback(invoke_without_command=True)
def _default(
    ctx: typer.Context,
    config: Path = typer.Option(_default_config(), "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    json_logs: bool = typer.Option(False, "--json-logs"),
) -> None:
    """Run all agents (default when no subcommand)."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    setup_logging(verbose=verbose, json_logs=json_logs)
    if ctx.invoked_subcommand is None:
        asyncio.run(_run(config))


@app.command()
def run(ctx: typer.Context) -> None:
    """Run all agents in a persistent heartbeat loop."""
    asyncio.run(_run(Path(ctx.obj["config"])))


@app.command(name="run-once")
def run_once(ctx: typer.Context) -> None:
    """Execute one tick per agent then exit."""
    asyncio.run(_run(Path(ctx.obj["config"]), once=True))


@app.command(name="dry-run")
def dry_run(ctx: typer.Context) -> None:
    """Build and print prompts without running agents."""
    asyncio.run(_run(Path(ctx.obj["config"]), once=True, dry_run=True))


@app.command()
def setup(ctx: typer.Context) -> None:
    """Initialize workspace dirs and sync agent symlinks."""
    config = Path(ctx.obj["config"])
    root = load_config(config)

    for agent in root.agents:
        if not verify_workspace(agent.workspace):
            typer.echo(f"FAIL: workspace invalid for {agent.name}", err=True)
            continue
        ensure_workspace_dirs(agent.workspace)
        sync_agent_symlinks(root.core_dir, agent.workspace)
        typer.echo(f"OK: {agent.name} workspace ready at {agent.workspace}")


@app.command()
def validate(ctx: typer.Context) -> None:
    """Check config and show summary."""
    config = Path(ctx.obj["config"])
    try:
        root = load_config(config)
    except Exception as exc:
        typer.echo(f"FAIL: {exc}", err=True)
        raise typer.Exit(code=2)

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


def main() -> None:
    app()
