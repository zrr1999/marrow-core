"""Runtime path helpers shared by CLI, services, sync, and tests."""

from __future__ import annotations

from pathlib import Path

from marrow_core.config import RootConfig

DEFAULT_SOCKET_PATH = "/tmp/marrow.sock"
DEFAULT_TASK_DIR = "/tmp/marrow-tasks"
DEFAULT_SERVICE_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
DEFAULT_SYNC_STATE_FILE = "runtime/state/sync-status.json"
DEFAULT_SYNC_LOCK_FILE = "runtime/state/sync.lock"


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


def resolve_sync_state_path(root: RootConfig) -> str:
    if root.sync.state_file:
        return root.sync.state_file
    workspace = primary_workspace(root)
    if workspace is not None:
        return str(workspace / DEFAULT_SYNC_STATE_FILE)
    return str(Path("/tmp") / Path(DEFAULT_SYNC_STATE_FILE).name)


def resolve_sync_lock_path(root: RootConfig) -> str:
    if root.sync.lock_file:
        return root.sync.lock_file
    workspace = primary_workspace(root)
    if workspace is not None:
        return str(workspace / DEFAULT_SYNC_LOCK_FILE)
    return str(Path("/tmp") / Path(DEFAULT_SYNC_LOCK_FILE).name)
