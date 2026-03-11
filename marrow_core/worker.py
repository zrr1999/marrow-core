"""Supervisor/worker process helpers."""

from __future__ import annotations

import json
import os
import pwd
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from marrow_core.config import RootConfig
from marrow_core.task_queue import create_task_file


def _safe_token(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value).strip("-") or "worker"


@dataclass(frozen=True)
class WorkerSpec:
    """One long-running worker identity group."""

    user: str
    group: str
    home: str
    workspace: str
    agent_names: tuple[str, ...]

    @property
    def worker_id(self) -> str:
        return "__".join(
            (
                _safe_token(self.user or "current"),
                _safe_token(Path(self.workspace).name or "workspace"),
                _safe_token("-".join(self.agent_names)),
            )
        )

    @property
    def stdout_log_path(self) -> Path:
        return Path(self.workspace) / "runtime" / "logs" / f"worker.{self.worker_id}.stdout.log"

    @property
    def stderr_log_path(self) -> Path:
        return Path(self.workspace) / "runtime" / "logs" / f"worker.{self.worker_id}.stderr.log"


@dataclass
class SupervisorState:
    """Aggregate worker status files for IPC consumers."""

    runtime_root: Path
    started_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        workers: dict[str, Any] = {}
        state_dir = self.runtime_root / "state" / "workers"
        if state_dir.is_dir():
            for path in sorted(state_dir.glob("*.json")):
                try:
                    workers[path.stem] = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
        return {
            "mode": "supervisor",
            "started_at": self.started_at,
            "uptime": round(time.time() - self.started_at, 1),
            "workers": workers,
        }


def group_agents_by_worker(root: RootConfig) -> list[WorkerSpec]:
    grouped: dict[tuple[str, str, str, str], list[str]] = {}
    for agent in root.agents:
        key = (agent.user, agent.run_as_group, agent.home, agent.workspace)
        grouped.setdefault(key, []).append(agent.name)
    return [
        WorkerSpec(
            user=user,
            group=group,
            home=home,
            workspace=workspace,
            agent_names=tuple(agent_names),
        )
        for (user, group, home, workspace), agent_names in grouped.items()
    ]


def build_worker_env(spec: WorkerSpec, base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ)
    if spec.home:
        env["HOME"] = spec.home
    if spec.user:
        env["USER"] = spec.user
        env["LOGNAME"] = spec.user
    env["MARROW_WORKSPACE"] = spec.workspace
    env["MARROW_WORKER_ID"] = spec.worker_id
    return env


def build_worker_preexec(spec: WorkerSpec):
    if os.geteuid() != 0 or not spec.user:
        return None

    def _drop_privileges() -> None:
        user_info = pwd.getpwnam(spec.user)
        gid = user_info.pw_gid
        if spec.group:
            import grp

            gid = grp.getgrnam(spec.group).gr_gid
        os.initgroups(spec.user, gid)
        os.setgid(gid)
        os.setuid(user_info.pw_uid)

    return _drop_privileges


def worker_state_path(runtime_root: Path, spec: WorkerSpec) -> Path:
    return runtime_root / "state" / "workers" / f"{spec.worker_id}.json"


def worker_request_dir(runtime_root: Path, spec: WorkerSpec) -> Path:
    return runtime_root / "control" / "workers" / spec.worker_id


def prepare_worker_runtime_paths(runtime_root: Path, spec: WorkerSpec) -> tuple[Path, Path]:
    state_path = worker_state_path(runtime_root, spec)
    request_dir = worker_request_dir(runtime_root, spec)
    (request_dir / "tasks").mkdir(parents=True, exist_ok=True)
    (request_dir / "wake").mkdir(parents=True, exist_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.touch(exist_ok=True)
    if os.geteuid() == 0 and spec.user:
        user_info = pwd.getpwnam(spec.user)
        gid = user_info.pw_gid
        if spec.group:
            import grp

            gid = grp.getgrnam(spec.group).gr_gid
        for path in (state_path, request_dir, request_dir / "tasks", request_dir / "wake"):
            os.chown(path, user_info.pw_uid, gid)
    return state_path, request_dir


def build_worker_command(
    *,
    marrow_bin: str,
    config_path: Path,
    spec: WorkerSpec,
    status_file: Path,
    request_dir: Path,
) -> str:
    argv = [
        marrow_bin,
        "worker-run",
        "--config",
        str(config_path),
        "--status-file",
        str(status_file),
        "--request-dir",
        str(request_dir),
    ]
    for agent_name in spec.agent_names:
        argv.extend(["--agent", agent_name])
    cmd = shlex.join(argv)
    return (
        f"{cmd} >> {shlex.quote(str(spec.stdout_log_path))} "
        f"2>> {shlex.quote(str(spec.stderr_log_path))}"
    )


def publish_worker_state(status_file: Path, payload: dict[str, Any]) -> None:
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def create_task_request(request_dir: Path, title: str, body: str) -> Path:
    tasks_dir = request_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    path = tasks_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{_safe_token(title)}.json"
    path.write_text(json.dumps({"title": title, "body": body}) + "\n", encoding="utf-8")
    return path


def create_wake_request(request_dir: Path, agent: str, reason: str) -> Path:
    wake_dir = request_dir / "wake"
    wake_dir.mkdir(parents=True, exist_ok=True)
    path = wake_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{_safe_token(agent)}.json"
    path.write_text(json.dumps({"agent": agent, "reason": reason}) + "\n", encoding="utf-8")
    return path


def drain_worker_requests(request_dir: Path, workspace: str, wake_events: dict[str, Any]) -> None:
    task_dir = Path(workspace) / "tasks" / "queue"
    for task_path in sorted((request_dir / "tasks").glob("*.json")):
        try:
            payload = json.loads(task_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            task_path.unlink(missing_ok=True)
            continue
        create_task_file(task_dir, payload.get("title", "task"), payload.get("body", ""))
        task_path.unlink(missing_ok=True)

    for wake_path in sorted((request_dir / "wake").glob("*.json")):
        try:
            payload = json.loads(wake_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            wake_path.unlink(missing_ok=True)
            continue
        agent_name = str(payload.get("agent", "")).strip()
        event = wake_events.get(agent_name)
        if event is not None:
            event.set()
        wake_path.unlink(missing_ok=True)
