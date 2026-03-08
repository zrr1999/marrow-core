"""Tests for marrow_core.workspace."""

from __future__ import annotations

from pathlib import Path

from marrow_core.contracts import ROLE_PATHS, SYNCED_ROLE_FILES, WORKSPACE_DIRS
from marrow_core.workspace import (
    _core_definition_files,
    ensure_workspace_dirs,
    load_rules,
    sync_agent_symlinks,
    verify_workspace,
)


def test_verify_workspace(tmp_path: Path):
    assert verify_workspace(str(tmp_path)) is True
    assert verify_workspace("/nonexistent/path/abc") is False


def test_ensure_workspace_dirs(tmp_path: Path):
    ensure_workspace_dirs(str(tmp_path))
    for directory in WORKSPACE_DIRS:
        assert (tmp_path / directory).is_dir(), f"missing {directory}"


def test_core_definition_files_prefer_roles(tmp_path: Path) -> None:
    core_dir = tmp_path / "core"
    (core_dir / "roles" / "l1").mkdir(parents=True)
    (core_dir / "roles" / "l1" / "scout.md").write_text("# Scout", encoding="utf-8")

    files = _core_definition_files(str(core_dir))

    assert files == [core_dir / "roles" / "l1" / "scout.md"]


def test_core_definition_files_require_roles(tmp_path: Path) -> None:
    core_dir = tmp_path / "core"
    assert _core_definition_files(str(core_dir)) == []


def test_sync_agent_symlinks_from_roles(tmp_path: Path):
    core_dir = tmp_path / "core"
    for role, rel_path in ROLE_PATHS.items():
        path = core_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {role}\n", encoding="utf-8")

    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / ".opencode" / "agents").mkdir(parents=True)

    sync_agent_symlinks(str(core_dir), str(ws))

    ws_agents = ws / ".opencode" / "agents"
    for role in SYNCED_ROLE_FILES:
        link = ws_agents / f"{role}.md"
        assert link.is_symlink(), f"{role} should be symlinked"
        assert link.resolve() == (core_dir / ROLE_PATHS[role]).resolve()


def test_sync_agent_symlinks_does_not_overwrite_existing_backup(tmp_path: Path) -> None:
    core_dir = tmp_path / "core"
    role_file = core_dir / "roles" / "l1" / "scout.md"
    role_file.parent.mkdir(parents=True, exist_ok=True)
    role_file.write_text("# Scout", encoding="utf-8")

    ws = tmp_path / "workspace"
    (ws / ".opencode" / "agents").mkdir(parents=True)
    dst = ws / ".opencode" / "agents" / "scout.md"
    dst.write_text("local agent override", encoding="utf-8")
    (ws / ".opencode" / "agents" / "scout.md.agent-backup").write_text(
        "older backup", encoding="utf-8"
    )

    sync_agent_symlinks(str(core_dir), str(ws))

    assert dst.is_symlink()
    assert (ws / ".opencode" / "agents" / "scout.md.agent-backup").read_text(
        encoding="utf-8"
    ) == "older backup"
    assert (ws / ".opencode" / "agents" / "scout.md.agent-backup-1").read_text(
        encoding="utf-8"
    ) == "local agent override"


def test_load_rules(tmp_path: Path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "rules.md").write_text(
        "# Rules\nDo not break things.", encoding="utf-8"
    )
    text = load_rules(str(tmp_path))
    assert "Do not break things" in text


def test_load_rules_missing(tmp_path: Path):
    assert load_rules(str(tmp_path)) == ""
