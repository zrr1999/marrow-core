"""Shared health checks for doctor and core self-check."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

from marrow_core.config import AgentConfig, RootConfig


def check_agent_health(agent: AgentConfig) -> list[str]:
    """Return doctor-style issue strings for one configured agent."""
    issues: list[str] = []
    workspace = Path(agent.workspace)
    if not workspace.is_dir():
        issues.append(f"{agent.name}: workspace missing: {workspace}")
    elif not os.access(workspace, os.W_OK):
        issues.append(f"{agent.name}: workspace not writable: {workspace}")

    for context_dir in agent.context_dirs:
        path = Path(context_dir)
        if not path.is_dir():
            issues.append(f"{agent.name}: context dir missing: {context_dir}")
            continue
        for script in sorted(path.iterdir()):
            if script.is_file() and not os.access(script, os.X_OK):
                issues.append(f"{agent.name}: not executable: {script.name}")

    command_parts = shlex.split(agent.agent_command)
    if command_parts:
        binary = command_parts[0]
        found = shutil.which(binary) or Path(binary).is_file()
        if not found:
            issues.append(f"{agent.name}: command not found: {binary}")

    return issues


def _run_extra_command(command: str) -> str | None:
    argv = shlex.split(command)
    if not argv:
        return None
    try:
        proc = subprocess.run(argv, check=False, capture_output=True, text=True)
    except OSError as exc:
        return f'extra command failed: "{command}" ({exc})'
    if proc.returncode == 0:
        return None
    detail = (proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}").splitlines()[
        0
    ]
    return f'extra command failed: "{command}" ({detail})'


def collect_health_issues(root: RootConfig) -> list[str]:
    """Run built-in and configured extra health checks."""
    issues: list[str] = []
    for agent in root.agents:
        issues.extend(check_agent_health(agent))
    for command in root.self_check.extra_commands:
        failure = _run_extra_command(command)
        if failure:
            issues.append(failure)
    return issues
