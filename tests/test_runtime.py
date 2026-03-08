"""Tests for runtime path helpers."""

from __future__ import annotations

from marrow_core.config import RootConfig
from marrow_core.runtime import marrow_binary, resolve_socket_path, resolve_task_dir


def test_runtime_paths_default_to_primary_workspace() -> None:
    root = RootConfig.model_validate(
        {
            "core_dir": "/opt/marrow-core",
            "agents": [
                {
                    "name": "scout",
                    "agent_command": "cmd",
                    "workspace": "/Users/marrow",
                    "context_dirs": ["/Users/marrow/context.d"],
                }
            ],
        }
    )

    assert resolve_socket_path(root) == "/Users/marrow/runtime/marrow.sock"
    assert resolve_task_dir(root) == "/Users/marrow/tasks/queue"


def test_runtime_paths_respect_ipc_overrides() -> None:
    root = RootConfig.model_validate(
        {
            "core_dir": "/opt/marrow-core",
            "ipc": {"socket_path": "/tmp/custom.sock", "task_dir": "/tmp/tasks"},
            "agents": [
                {
                    "name": "scout",
                    "agent_command": "cmd",
                    "workspace": "/Users/marrow",
                    "context_dirs": ["/Users/marrow/context.d"],
                }
            ],
        }
    )

    assert resolve_socket_path(root) == "/tmp/custom.sock"
    assert resolve_task_dir(root) == "/tmp/tasks"


def test_marrow_binary_uses_core_virtualenv() -> None:
    assert marrow_binary("/opt/marrow-core") == "/opt/marrow-core/.venv/bin/marrow"
