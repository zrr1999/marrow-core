"""Unified CLI assembly."""

from __future__ import annotations

import typer

import marrow_core.cli.ops as ops_module
import marrow_core.cli.service as service_module
from marrow_core.cli.service import app as service_app

app = typer.Typer(add_completion=False, help="marrow-core runtime commands.")
app.add_typer(service_app, name="service", hidden=True)


def _public(command_name: str, callback, help_text: str) -> None:
    app.command(name=command_name, help=help_text)(callback)


def _deprecated(command_name: str, callback, help_text: str) -> None:
    app.command(name=command_name, help=help_text, deprecated=True)(callback)


def _hidden(command_name: str, callback, help_text: str) -> None:
    app.command(name=command_name, hidden=True, help=help_text)(callback)


_public("run", service_module.run, "Run the scheduler service.")
_deprecated("run-once", service_module.run_once, "[Deprecated] Use 'run --once' instead.")
_deprecated("dry-run", service_module.dry_run, "[Deprecated] Use 'run --dry-run' instead.")
_public("sync-once", service_module.sync_once, "Run one bounded sync attempt.")
_public("setup", ops_module.setup, "Initialize runtime directories and workspaces.")
_public("validate", ops_module.validate, "Validate config and show summary.")
_public("doctor", ops_module.doctor, "Check workspace and command health.")
_public("scaffold", ops_module.scaffold_cmd, "Create a starter workspace and config.")
_public("install-service", ops_module.install_service, "Render service definitions.")
_public("status", ops_module.status, "Query runtime state via IPC.")
_public("wake", ops_module.wake, "Wake an agent with optional one-shot prompt.")

_hidden("worker-run", service_module.worker_run, "Internal worker entrypoint.")
_hidden("workspace-sync", service_module.workspace_sync, "Internal workspace preparation.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
