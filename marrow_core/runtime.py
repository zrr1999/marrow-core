"""Runtime path helpers shared by CLI, services, sync, and workers."""

from __future__ import annotations

import shutil
from pathlib import Path

from marrow_core.config import RootConfig

DEFAULT_SOCKET_PATH = "/tmp/marrow.sock"
DEFAULT_TASK_DIR = "/tmp/marrow-tasks"
DEFAULT_SERVICE_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
DEFAULT_SYNC_STATE_FILE = "runtime/state/sync-status.json"
DEFAULT_SYNC_LOCK_FILE = "runtime/state/sync.lock"
DEFAULT_SUPERVISOR_RUNTIME_ROOT = "/var/lib/marrow"


def primary_workspace(root: RootConfig) -> Path | None:
    if not root.agents:
        return None
    return Path(root.agents[0].workspace)


def resolve_service_runtime_root(root: RootConfig) -> str:
    if root.service.runtime_root:
        return root.service.runtime_root
    if root.service.mode == "supervisor":
        return DEFAULT_SUPERVISOR_RUNTIME_ROOT
    workspace = primary_workspace(root)
    if workspace is not None:
        return str(workspace / "runtime")
    return str(Path("/tmp") / "marrow-runtime")


def resolve_service_log_dir(root: RootConfig) -> str:
    if root.service.log_dir:
        return root.service.log_dir
    if root.service.mode == "supervisor":
        return str(Path(resolve_service_runtime_root(root)) / "logs")
    workspace = primary_workspace(root)
    if workspace is not None:
        return str(workspace / "runtime" / "logs")
    return str(Path("/tmp") / "marrow-logs")


def resolve_service_user(root: RootConfig) -> str:
    if root.service.mode == "supervisor":
        return ""
    if root.agents and root.agents[0].user:
        return root.agents[0].user
    return "marrow"


def resolve_worker_state_dir(root: RootConfig) -> str:
    return str(Path(resolve_service_runtime_root(root)) / "state" / "workers")


def resolve_control_root(root: RootConfig) -> str:
    return str(Path(resolve_service_runtime_root(root)) / "control")


def resolve_socket_path(root: RootConfig) -> str:
    if root.ipc.socket_path:
        return root.ipc.socket_path
    if root.service.mode == "supervisor":
        return str(Path(resolve_service_runtime_root(root)) / "state" / "marrow.sock")
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
    if root.service.mode == "supervisor":
        return str(Path(resolve_service_runtime_root(root)) / "control" / "tasks")
    return DEFAULT_TASK_DIR


def marrow_binary(core_dir: str) -> str:
    if not core_dir:
        return shutil.which("marrow-core") or shutil.which("marrow") or "marrow-core"
    return str(Path(core_dir) / ".venv" / "bin" / "marrow")


def build_service_path(home_dir: str = "") -> str:
    parts: list[str] = []
    if home_dir:
        home = Path(home_dir)
        parts.extend(
            [
                str(home / ".bun" / "bin"),
                str(home / ".local" / "bin"),
                str(home / "bin"),
            ]
        )
    parts.extend(DEFAULT_SERVICE_PATH.split(":"))

    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        if not part or part in seen:
            continue
        seen.add(part)
        ordered.append(part)
    return ":".join(ordered)


def resolve_sync_state_path(root: RootConfig) -> str:
    if root.sync.state_file:
        return root.sync.state_file
    if root.service.mode == "supervisor":
        return str(Path(resolve_service_runtime_root(root)) / "state" / "sync-status.json")
    workspace = primary_workspace(root)
    if workspace is not None:
        return str(workspace / DEFAULT_SYNC_STATE_FILE)
    return str(Path("/tmp") / Path(DEFAULT_SYNC_STATE_FILE).name)


def resolve_sync_lock_path(root: RootConfig) -> str:
    if root.sync.lock_file:
        return root.sync.lock_file
    if root.service.mode == "supervisor":
        return str(Path(resolve_service_runtime_root(root)) / "state" / "sync.lock")
    workspace = primary_workspace(root)
    if workspace is not None:
        return str(workspace / DEFAULT_SYNC_LOCK_FILE)
    return str(Path("/tmp") / Path(DEFAULT_SYNC_LOCK_FILE).name)


def ensure_service_runtime_dirs(root: RootConfig) -> list[Path]:
    runtime_root = Path(resolve_service_runtime_root(root))
    log_dir = Path(resolve_service_log_dir(root))
    paths = [
        runtime_root / "state",
        runtime_root / "state" / "workers",
        runtime_root / "control" / "tasks",
        runtime_root / "control" / "wake",
        log_dir,
    ]
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
    return paths
