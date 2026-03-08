"""Runtime path helpers shared by CLI, services, and tests."""

from __future__ import annotations

from pathlib import Path

from marrow_core.config import RootConfig

DEFAULT_SOCKET_PATH = "/tmp/marrow.sock"
DEFAULT_TASK_DIR = "/tmp/marrow-tasks"
DEFAULT_SERVICE_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def primary_workspace(root: RootConfig) -> Path | None:
    if not root.agents:
        return None
    return Path(root.agents[0].workspace)


def resolve_socket_path(root: RootConfig) -> str:
    if root.ipc.socket_path:
        return root.ipc.socket_path
    workspace = primary_workspace(root)
    if workspace is not None:
        return str(workspace / "runtime" / "marrow.sock")
    return DEFAULT_SOCKET_PATH


def resolve_task_dir(root: RootConfig) -> str:
    if root.ipc.task_dir:
        return root.ipc.task_dir
    workspace = primary_workspace(root)
    if workspace is not None:
        return str(workspace / "tasks" / "queue")
    return DEFAULT_TASK_DIR


def marrow_binary(core_dir: str) -> str:
    return str(Path(core_dir) / ".venv" / "bin" / "marrow")
