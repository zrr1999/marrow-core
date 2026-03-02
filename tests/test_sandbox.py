"""Tests for marrow_core.sandbox."""

from __future__ import annotations

from pathlib import Path

from marrow_core.sandbox import (
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
    assert (tmp_path / "runtime" / "state").is_dir()
    assert (tmp_path / "tasks" / "queue").is_dir()
    assert (tmp_path / "context.d").is_dir()
    assert (tmp_path / ".opencode" / "agents").is_dir()


def test_sync_agent_symlinks(tmp_path: Path):
    # Create fake core agents
    core_dir = tmp_path / "core"
    (core_dir / "agents").mkdir(parents=True)
    (core_dir / "agents" / "scout.md").write_text("# Scout")
    (core_dir / "agents" / "artisan.md").write_text("# Artisan")

    # Create fake workspace
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / ".opencode" / "agents").mkdir(parents=True)

    sync_agent_symlinks(str(core_dir), str(ws))

    scout_link = ws / ".opencode" / "agents" / "scout.md"
    assert scout_link.is_symlink()
    assert scout_link.resolve() == (core_dir / "agents" / "scout.md").resolve()
    assert scout_link.read_text() == "# Scout"


def test_sync_replaces_stale_symlink(tmp_path: Path):
    core_dir = tmp_path / "core"
    (core_dir / "agents").mkdir(parents=True)
    (core_dir / "agents" / "scout.md").write_text("# Scout v2")

    ws = tmp_path / "workspace"
    (ws / ".opencode" / "agents").mkdir(parents=True)
    # Create stale symlink pointing elsewhere
    stale_target = tmp_path / "old" / "scout.md"
    stale_target.parent.mkdir()
    stale_target.write_text("old")
    (ws / ".opencode" / "agents" / "scout.md").symlink_to(stale_target)

    sync_agent_symlinks(str(core_dir), str(ws))

    link = ws / ".opencode" / "agents" / "scout.md"
    assert link.read_text() == "# Scout v2"


def test_load_rules(tmp_path: Path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "rules.md").write_text("# Rules\nDo not break things.")
    text = load_rules(str(tmp_path))
    assert "Do not break things" in text


def test_load_rules_missing(tmp_path: Path):
    assert load_rules(str(tmp_path)) == ""
