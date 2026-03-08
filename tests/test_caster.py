"""Tests for agent-caster integration."""

from __future__ import annotations

import textwrap
from pathlib import Path

from marrow_core.caster import cast_roles_to_workspace


def _write_roles_toml(core_dir: Path) -> None:
    (core_dir / "roles.toml").write_text(
        textwrap.dedent(
            """
            [project]
            agents_dir = "roles"

            [targets.opencode]
            enabled = true
            output_dir = "."
            output_layout = "preserve"

            [targets.opencode.model_map]
            routine = "model-routine"
            operational = "model-operational"
            strategic = "model-strategic"
            specialist = "model-specialist"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def test_cast_roles_to_workspace_generates_opencode_outputs(tmp_path: Path) -> None:
    core_dir = tmp_path / "core"
    workspace = tmp_path / "workspace"
    role_dir = core_dir / "roles" / "l1"
    role_dir.mkdir(parents=True)
    (workspace / ".opencode" / "agents").mkdir(parents=True)
    _write_roles_toml(core_dir)
    (role_dir / "scout.md").write_text(
        textwrap.dedent(
            """
            ---
            name: scout
            description: Routine scout
            role: primary
            model:
              tier: routine
            hierarchy:
              level: L1
              class: main
              scheduled: true
              callable: false
              max_delegate_depth: 0
            ---
            You are scout.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    written = cast_roles_to_workspace(str(core_dir), str(workspace))

    target = workspace / ".opencode" / "agents" / "l1" / "scout.md"
    assert written == [target]
    content = target.read_text(encoding="utf-8")
    assert "description: Routine scout" in content
    assert "mode: primary" in content
    assert "model: model-routine" in content
    assert "You are scout." in content


def test_cast_roles_to_workspace_preserves_custom_role_files(tmp_path: Path) -> None:
    core_dir = tmp_path / "core"
    workspace = tmp_path / "workspace"
    role_dir = core_dir / "roles" / "l1"
    role_dir.mkdir(parents=True)
    agents_dir = workspace / ".opencode" / "agents"
    agents_dir.mkdir(parents=True)
    _write_roles_toml(core_dir)
    (agents_dir / "custom-local.md").write_text("custom", encoding="utf-8")
    (role_dir / "scout.md").write_text(
        textwrap.dedent(
            """
            ---
            name: scout
            description: Routine scout
            role: primary
            model:
              tier: routine
            hierarchy:
              level: L1
              class: main
              scheduled: true
              callable: false
              max_delegate_depth: 0
            ---
            You are scout.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    cast_roles_to_workspace(str(core_dir), str(workspace))

    assert (agents_dir / "custom-local.md").read_text(encoding="utf-8") == "custom"
