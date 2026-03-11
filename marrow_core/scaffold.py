"""Workspace and config scaffolding helpers."""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

from marrow_core.contracts import AUTONOMOUS_AGENTS, WORKSPACE_DIRS

DEFAULT_AGENT_SCHEDULES = {
    "curator": (10800, 7200),
}


def scaffold_workspace(destination: Path, *, source_context_dir: Path | None = None) -> list[Path]:
    """Create a writable workspace skeleton and copy default context scripts."""
    destination.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for directory in WORKSPACE_DIRS:
        path = destination / directory
        path.mkdir(parents=True, exist_ok=True)
        created.append(path)

    docs_dir = destination / "docs"
    docs_dir.mkdir(exist_ok=True)
    created.append(docs_dir)

    if source_context_dir is not None and source_context_dir.is_dir():
        target_context_dir = destination / "context.d"
        for script in sorted(source_context_dir.iterdir()):
            if not script.is_file():
                continue
            target = target_context_dir / script.name
            if not target.exists():
                shutil.copy2(script, target)
                created.append(target)
    return created


def render_config_template(*, core_dir: str, workspace: Path) -> str:
    blocks = []
    for name in AUTONOMOUS_AGENTS:
        interval, timeout = DEFAULT_AGENT_SCHEDULES[name]
        blocks.append(
            textwrap.dedent(
                f"""
                [[agents]]
                user = "marrow"
                name = "{name}"
                heartbeat_interval = {interval}
                heartbeat_timeout = {timeout}
                workspace = "{workspace}"
                agent_command = "{workspace}/.opencode/bin/opencode run --agent {name}"
                context_dirs = ["{workspace}/context.d"]
                """
            ).strip()
        )
    return (
        textwrap.dedent(
            f"""
            core_dir = "{core_dir}"

            [service]
            mode = "supervisor"
            runtime_root = "/var/lib/marrow"

            [ipc]
            enabled = true

            [self_check]
            enabled = true
            interval_seconds = 900
            wake_agent = "curator"

            {"\n\n".join(blocks)}
            """
        ).strip()
        + "\n"
    )


def write_config_template(path: Path, *, core_dir: str, workspace: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_config_template(core_dir=core_dir, workspace=workspace), encoding="utf-8"
    )
    return path
