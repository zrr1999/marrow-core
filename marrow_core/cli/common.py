"""Shared CLI helpers and option types."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer

from marrow_core.config import RootConfig, load_config
from marrow_core.workspace import ensure_workspace_dirs

ConfigOpt = Annotated[Path, typer.Option("--config", "-c", help="Path to runtime config TOML")]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logging")]
JsonLogsOpt = Annotated[bool, typer.Option("--json-logs", help="Emit JSON log records")]
IpcOpt = Annotated[
    bool | None,
    typer.Option("--ipc/--no-ipc", help="Override IPC server (default: from config)"),
]


def load_root_or_exit(config: Path) -> RootConfig:
    if not config.is_file():
        typer.echo(f"config not found: {config}", err=True)
        raise typer.Exit(code=1)
    return load_config(config)


def sync_workspace(workspace: str) -> None:
    ensure_workspace_dirs(workspace)


async def ipc_request(socket_path: str, method: str, path: str, body: str = "") -> dict:
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
    idx = text.find("\r\n\r\n")
    json_str = text[idx + 4 :] if idx >= 0 else text
    return json.loads(json_str)
