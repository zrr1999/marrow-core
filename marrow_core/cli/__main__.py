"""Unified CLI assembly."""

from __future__ import annotations

from typing import Any, cast

import typer
from typer.main import get_command

import marrow_core.cli.ops as ops_module
import marrow_core.cli.service as service_module
from marrow_core.cli.service import app as service_app

app = typer.Typer(add_completion=False, help="marrow-core runtime commands.")
app.add_typer(service_app, name="service", hidden=True)


def _mirror(command_name: str, source_app: typer.Typer, callback) -> None:
    source_commands = cast(dict[str, Any], cast(Any, get_command(source_app)).commands)
    source_command = source_commands[command_name]
    app.command(
        name=command_name,
        help=source_command.help,
        deprecated=source_command.deprecated,
        hidden=source_command.hidden,
    )(callback)


_mirror("run", service_module.app, service_module.run)
_mirror("run-once", service_module.app, service_module.run_once)
_mirror("dry-run", service_module.app, service_module.dry_run)
_mirror("sync-once", service_module.app, service_module.sync_once)
_mirror("install", ops_module.app, ops_module.install)
_mirror("setup", ops_module.app, ops_module.setup)
_mirror("validate", ops_module.app, ops_module.validate)
_mirror("doctor", ops_module.app, ops_module.doctor)
_mirror("scaffold", ops_module.app, ops_module.scaffold_cmd)
_mirror("install-service", ops_module.app, ops_module.install_service)
_mirror("profile-setup", ops_module.app, ops_module.profile_setup)
_mirror("status", ops_module.app, ops_module.status)
_mirror("wake", ops_module.app, ops_module.wake)

_mirror("worker-run", service_module.app, service_module.worker_run)
_mirror("workspace-sync", service_module.app, service_module.workspace_sync)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
