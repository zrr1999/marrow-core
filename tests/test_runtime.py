"""Tests for runtime path helpers."""

from __future__ import annotations

from marrow_core.config import RootConfig
from marrow_core.runtime import (
    ensure_service_runtime_dirs,
    marrow_binary,
    resolve_service_log_dir,
    resolve_service_runtime_root,
    resolve_socket_path,
    resolve_sync_state_path,
    resolve_task_dir,
)


def test_runtime_paths_default_to_primary_workspace() -> None:
    root = RootConfig.model_validate(
        {
            "core_dir": "/opt/marrow-core",
            "agents": [
                {
                    "name": "curator",
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
                    "name": "curator",
                    "agent_command": "cmd",
                    "workspace": "/Users/marrow",
                    "context_dirs": ["/Users/marrow/context.d"],
                }
            ],
        }
    )

    assert resolve_socket_path(root) == "/tmp/custom.sock"
    assert resolve_task_dir(root) == "/tmp/tasks"


def test_supervisor_runtime_paths_use_service_runtime_root(tmp_path) -> None:
    root = RootConfig.model_validate(
        {
            "service": {
                "mode": "supervisor",
                "runtime_root": str(tmp_path / "runtime-root"),
            },
            "agents": [
                {
                    "name": "curator",
                    "agent_command": "cmd",
                    "workspace": "/Users/marrow",
                    "run_as_user": "marrow",
                    "home": "/Users/marrow",
                }
            ],
        }
    )

    assert resolve_service_runtime_root(root) == str(tmp_path / "runtime-root")
    assert resolve_service_log_dir(root) == str(tmp_path / "runtime-root" / "logs")
    assert resolve_socket_path(root) == str(tmp_path / "runtime-root" / "state" / "marrow.sock")
    assert resolve_sync_state_path(root) == str(
        tmp_path / "runtime-root" / "state" / "sync-status.json"
    )
    assert resolve_task_dir(root) == "/Users/marrow/tasks/queue"


def test_ensure_service_runtime_dirs_creates_supervisor_tree(tmp_path) -> None:
    root = RootConfig.model_validate(
        {
            "service": {
                "mode": "supervisor",
                "runtime_root": str(tmp_path / "runtime-root"),
            },
            "agents": [
                {
                    "name": "curator",
                    "agent_command": "cmd",
                    "workspace": "/Users/marrow",
                    "run_as_user": "marrow",
                    "home": "/Users/marrow",
                }
            ],
        }
    )

    ensure_service_runtime_dirs(root)

    assert (tmp_path / "runtime-root" / "state").is_dir()
    assert (tmp_path / "runtime-root" / "state" / "workers").is_dir()
    assert (tmp_path / "runtime-root" / "control" / "tasks").is_dir()
    assert (tmp_path / "runtime-root" / "control" / "wake").is_dir()
    assert (tmp_path / "runtime-root" / "logs").is_dir()


def test_marrow_binary_uses_core_virtualenv() -> None:
    assert marrow_binary("/opt/marrow-core") == "/opt/marrow-core/.venv/bin/marrow"
