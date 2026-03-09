"""Tests for runtime path helpers."""

from __future__ import annotations

from pathlib import Path

from marrow_core.config import RootConfig
from marrow_core.runtime import (
    marrow_binary,
    resolve_python_executable,
    resolve_socket_path,
    resolve_task_dir,
)


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


def test_resolve_python_executable_prefers_running_interpreter(monkeypatch, tmp_path: Path) -> None:
    current = tmp_path / "bin" / "python3.14"
    current.parent.mkdir(parents=True)
    current.write_text("", encoding="utf-8")

    monkeypatch.setattr("marrow_core.runtime.sys.executable", str(current))
    monkeypatch.setattr("marrow_core.runtime.shutil.which", lambda name: None)

    assert resolve_python_executable() == str(current)


def test_resolve_python_executable_falls_back_to_python3(monkeypatch) -> None:
    lookup = {
        "python3": "/usr/local/bin/python3",
        "python": None,
    }

    monkeypatch.setattr("marrow_core.runtime.sys.executable", "")
    monkeypatch.setattr("marrow_core.runtime.shutil.which", lambda name: lookup.get(name))

    assert resolve_python_executable() == "/usr/local/bin/python3"
