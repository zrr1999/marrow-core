from __future__ import annotations

from pathlib import Path

from marrow_core.config import AgentConfig, RootConfig
from marrow_core.health import check_agent_health, collect_health_issues


def test_check_agent_health_reports_missing_workspace_context_and_binary(tmp_path: Path) -> None:
    agent = AgentConfig(
        name="orchestrator",
        agent_command=str(tmp_path / "missing-binary"),
        workspace=str(tmp_path / "missing-workspace"),
        context_dirs=[str(tmp_path / "missing-context")],
    )

    issues = check_agent_health(agent)

    assert f"orchestrator: workspace missing: {tmp_path / 'missing-workspace'}" in issues
    assert f"orchestrator: context dir missing: {tmp_path / 'missing-context'}" in issues
    assert f"orchestrator: command not found: {tmp_path / 'missing-binary'}" in issues


def test_collect_health_issues_includes_extra_command_failures(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    context_dir = workspace / "context.d"
    context_dir.mkdir()
    script = context_dir / "queue.py"
    script.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
    script.chmod(0o755)

    root = RootConfig.model_validate(
        {
            "agents": [
                {
                    "name": "orchestrator",
                    "agent_command": str(Path("/bin/echo")),
                    "workspace": str(workspace),
                    "context_dirs": [str(context_dir)],
                }
            ],
            "self_check": {
                "extra_commands": ["python3 -c 'import sys; sys.exit(3)'"],
            },
        }
    )

    issues = collect_health_issues(root)

    assert len(issues) == 1
    assert 'extra command failed: "python3 -c' in issues[0]
