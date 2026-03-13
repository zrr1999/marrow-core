"""Tests for role-forge integration."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from marrow_core.caster import CastResult, cast_roles_to_workspace


def _write_roles_toml(core_dir: Path) -> None:
    (core_dir / "roles.toml").write_text(
        textwrap.dedent(
            """
            [project]
            roles_dir = "roles"

            [targets.opencode]
            enabled = true
            output_dir = "."
            output_layout = "preserve"

            [targets.opencode.model_map]
            high = "model-high"
            medium = "model-medium"
            low = "model-low"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _write_role(role_dir: Path, name: str, *, description: str = "Role") -> None:
    (role_dir / f"{name}.md").write_text(
        textwrap.dedent(
            f"""
            ---
            name: {name}
            description: {description}
            role: subagent
            model:
              tier: medium
            ---
            You are {name}.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def test_cast_roles_to_workspace_generates_opencode_outputs(tmp_path: Path) -> None:
    core_dir = tmp_path / "core"
    workspace = tmp_path / "workspace"
    role_dir = core_dir / "roles"
    role_dir.mkdir(parents=True)
    (workspace / ".opencode" / "agents").mkdir(parents=True)
    _write_roles_toml(core_dir)
    (role_dir / "orchestrator.md").write_text(
        textwrap.dedent(
            """
            ---
            name: orchestrator
            description: Top-level orchestrator
            role: primary
            model:
              tier: high
            ---
            You are orchestrator.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    result = cast_roles_to_workspace(str(core_dir), str(workspace))

    target = workspace / ".opencode" / "agents" / "orchestrator.md"
    assert result == CastResult(written=[target], skipped_permission=[], errors=[])
    content = target.read_text(encoding="utf-8")
    assert "description: Top-level orchestrator" in content
    assert "mode: primary" in content
    assert "model: model-high" in content
    assert "You are orchestrator." in content


def test_cast_roles_to_workspace_preserves_custom_role_files(tmp_path: Path) -> None:
    core_dir = tmp_path / "core"
    workspace = tmp_path / "workspace"
    role_dir = core_dir / "roles"
    role_dir.mkdir(parents=True)
    agents_dir = workspace / ".opencode" / "agents"
    agents_dir.mkdir(parents=True)
    _write_roles_toml(core_dir)
    (agents_dir / "custom-local.md").write_text("custom", encoding="utf-8")
    (role_dir / "orchestrator.md").write_text(
        textwrap.dedent(
            """
            ---
            name: orchestrator
            description: Top-level orchestrator
            role: primary
            model:
              tier: high
            ---
            You are orchestrator.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    cast_roles_to_workspace(str(core_dir), str(workspace))

    assert (agents_dir / "custom-local.md").read_text(encoding="utf-8") == "custom"


def test_cast_roles_to_workspace_skips_permission_denied_unlink(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    core_dir = tmp_path / "core"
    workspace = tmp_path / "workspace"
    role_dir = core_dir / "roles"
    agents_dir = workspace / ".opencode" / "agents"
    role_dir.mkdir(parents=True)
    agents_dir.mkdir(parents=True)
    _write_roles_toml(core_dir)
    _write_role(role_dir, "helper")
    stale = agents_dir / "stale.md"
    stale.write_text("old\n", encoding="utf-8")

    original_unlink = Path.unlink

    def fake_unlink(self: Path, *args, **kwargs):
        if self == stale:
            raise PermissionError("denied")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fake_unlink)

    result = cast_roles_to_workspace(str(core_dir), str(workspace))

    assert stale in result.skipped_permission
    assert workspace / ".opencode" / "agents" / "helper.md" in result.written
    assert result.errors == []


def test_cast_roles_to_workspace_skips_permission_denied_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    core_dir = tmp_path / "core"
    workspace = tmp_path / "workspace"
    role_dir = core_dir / "roles"
    agents_dir = workspace / ".opencode" / "agents"
    role_dir.mkdir(parents=True)
    agents_dir.mkdir(parents=True)
    _write_roles_toml(core_dir)
    _write_role(role_dir, "alpha")
    _write_role(role_dir, "beta")

    denied = agents_dir / "alpha.md"
    original_write_text = Path.write_text

    def fake_write_text(self: Path, *args, **kwargs):
        if self == denied:
            raise PermissionError("denied")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fake_write_text)

    result = cast_roles_to_workspace(str(core_dir), str(workspace))

    assert denied in result.skipped_permission
    assert workspace / ".opencode" / "agents" / "beta.md" in result.written
    assert result.errors == []


def test_cast_roles_to_workspace_skips_permission_denied_rmdir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    core_dir = tmp_path / "core"
    workspace = tmp_path / "workspace"
    role_dir = core_dir / "roles"
    nested_dir = workspace / ".opencode" / "agents" / "nested"
    role_dir.mkdir(parents=True)
    nested_dir.mkdir(parents=True)
    _write_roles_toml(core_dir)
    _write_role(role_dir, "helper")
    stale = nested_dir / "stale.md"
    stale.write_text("old\n", encoding="utf-8")

    original_rmdir = Path.rmdir

    def fake_rmdir(self: Path):
        if self == nested_dir:
            raise PermissionError("denied")
        return original_rmdir(self)

    monkeypatch.setattr(Path, "rmdir", fake_rmdir)

    result = cast_roles_to_workspace(str(core_dir), str(workspace))

    assert nested_dir in result.skipped_permission
    assert workspace / ".opencode" / "agents" / "helper.md" in result.written
