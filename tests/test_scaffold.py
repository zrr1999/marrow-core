"""Tests for workspace scaffolding helpers."""

from __future__ import annotations

from pathlib import Path

from marrow_core.contracts import AUTONOMOUS_AGENTS, WORKSPACE_DIRS
from marrow_core.scaffold import render_config_template, scaffold_workspace, write_config_template


def test_scaffold_workspace_creates_contract_dirs_and_docs(tmp_path: Path) -> None:
    source_context = tmp_path / "source-context"
    source_context.mkdir()
    (source_context / "queue.py").write_text("print('ok')\n", encoding="utf-8")

    created = scaffold_workspace(tmp_path / "workspace", source_context_dir=source_context)
    workspace = tmp_path / "workspace"

    for directory in WORKSPACE_DIRS:
        assert (workspace / directory).is_dir()
    assert (workspace / "docs").is_dir()
    assert (workspace / "context.d" / "queue.py").exists()
    assert workspace / "docs" in created


def test_render_config_template_includes_all_autonomous_agents(tmp_path: Path) -> None:
    text = render_config_template(core_dir="", workspace=tmp_path / "workspace")

    for name in AUTONOMOUS_AGENTS:
        assert f'name = "{name}"' in text
        assert f'--agent {name}"' in text
    assert "[service]" in text
    assert 'mode = "supervisor"' in text
    assert 'user = "marrow"' in text
    assert "[ipc]" in text
    assert "enabled = true" in text
    assert "[self_check]" in text
    assert 'wake_agent = "orchestrator"' in text


def test_write_config_template_persists_file(tmp_path: Path) -> None:
    path = write_config_template(
        tmp_path / "generated" / "marrow.toml",
        core_dir="",
        workspace=tmp_path / "workspace",
    )

    assert path.exists()
    assert "core_dir =" not in path.read_text(encoding="utf-8")
