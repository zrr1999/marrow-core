"""Tests for marrow_core.workspace."""

from __future__ import annotations

from pathlib import Path

from marrow_core.workspace import (
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
    assert (tmp_path / "runtime" / "handoff" / "scout-to-conductor").is_dir()
    assert (tmp_path / "runtime" / "handoff" / "conductor-to-scout").is_dir()
    assert (tmp_path / "tasks" / "queue").is_dir()
    assert (tmp_path / "context.d").is_dir()
    assert (tmp_path / ".opencode" / "agents").is_dir()


def test_sync_agent_symlinks(tmp_path: Path):
    # Create fake core agents
    core_dir = tmp_path / "core"
    (core_dir / "agents").mkdir(parents=True)
    (core_dir / "agents" / "scout.md").write_text("# Scout")
    (core_dir / "agents" / "conductor.md").write_text("# Conductor")

    # Create fake workspace
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / ".opencode" / "agents").mkdir(parents=True)

    sync_agent_symlinks(str(core_dir), str(ws))

    scout_link = ws / ".opencode" / "agents" / "scout.md"
    assert scout_link.is_symlink()
    assert scout_link.resolve() == (core_dir / "agents" / "scout.md").resolve()
    assert scout_link.read_text() == "# Scout"


def test_sync_agent_symlinks_does_not_overwrite_existing_backup(tmp_path: Path) -> None:
    core_dir = tmp_path / "core"
    (core_dir / "agents").mkdir(parents=True)
    (core_dir / "agents" / "scout.md").write_text("# Scout")

    ws = tmp_path / "workspace"
    (ws / ".opencode" / "agents").mkdir(parents=True)
    dst = ws / ".opencode" / "agents" / "scout.md"
    dst.write_text("local agent override")
    # Pre-existing backup file should be preserved.
    (ws / ".opencode" / "agents" / "scout.md.agent-backup").write_text("older backup")

    sync_agent_symlinks(str(core_dir), str(ws))

    assert dst.is_symlink()
    # ensure a new backup was created without clobbering the old one
    assert (ws / ".opencode" / "agents" / "scout.md.agent-backup").read_text() == "older backup"
    assert (
        ws / ".opencode" / "agents" / "scout.md.agent-backup-1"
    ).read_text() == "local agent override"


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


def test_sync_agent_symlinks_includes_subagents(tmp_path: Path):
    """All agent definitions (autonomous + sub-agents) are symlinked to workspace."""
    core_dir = tmp_path / "core"
    (core_dir / "agents").mkdir(parents=True)
    # Autonomous agents
    (core_dir / "agents" / "scout.md").write_text("# Scout")
    (core_dir / "agents" / "conductor.md").write_text("# Conductor")
    (core_dir / "agents" / "refit.md").write_text("# Refit")
    # Sub-agents
    (core_dir / "agents" / "analyst.md").write_text("# Analyst")
    (core_dir / "agents" / "researcher.md").write_text("# Researcher")
    (core_dir / "agents" / "coder.md").write_text("# Coder")
    (core_dir / "agents" / "tester.md").write_text("# Tester")
    (core_dir / "agents" / "writer.md").write_text("# Writer")
    (core_dir / "agents" / "ops.md").write_text("# Ops")
    (core_dir / "agents" / "reviewer.md").write_text("# Reviewer")
    (core_dir / "agents" / "git-ops.md").write_text("# Git-Ops")
    (core_dir / "agents" / "filer.md").write_text("# Filer")

    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / ".opencode" / "agents").mkdir(parents=True)

    sync_agent_symlinks(str(core_dir), str(ws))

    ws_agents = ws / ".opencode" / "agents"
    expected = [
        "analyst.md",
        "conductor.md",
        "coder.md",
        "filer.md",
        "git-ops.md",
        "ops.md",
        "refit.md",
        "researcher.md",
        "reviewer.md",
        "scout.md",
        "tester.md",
        "writer.md",
    ]
    for name in expected:
        link = ws_agents / name
        assert link.is_symlink(), f"{name} should be symlinked"
        assert link.resolve() == (core_dir / "agents" / name).resolve()
