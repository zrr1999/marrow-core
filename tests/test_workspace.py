"""Tests for marrow_core.workspace."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from marrow_core.workspace import (
    _agent_caster_available,
    _install_agent_file,
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


def test_agent_caster_not_available_when_missing():
    """_agent_caster_available returns False when the binary is not found."""
    with patch("marrow_core.workspace.subprocess.run", side_effect=FileNotFoundError):
        assert _agent_caster_available() is False


def test_agent_caster_available_when_present():
    """_agent_caster_available returns True when the binary exits 0."""
    import subprocess

    mock_result = subprocess.CompletedProcess(args=[], returncode=0)
    with patch("marrow_core.workspace.subprocess.run", return_value=mock_result):
        assert _agent_caster_available() is True


def test_install_agent_file_copies(tmp_path: Path):
    """_install_agent_file copies file and overwrites symlinks."""
    src = tmp_path / "scout.md"
    src.write_text("# Scout generated")
    dst = tmp_path / "agents" / "scout.md"
    dst.parent.mkdir()

    _install_agent_file(src, dst)

    assert dst.is_file()
    assert not dst.is_symlink()
    assert dst.read_text() == "# Scout generated"


def test_install_agent_file_replaces_symlink(tmp_path: Path):
    """_install_agent_file removes existing symlink before copying."""
    src = tmp_path / "scout.md"
    src.write_text("new content")
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    dst = agents_dir / "scout.md"
    # Create a stale symlink
    stale = tmp_path / "old.md"
    stale.write_text("old")
    dst.symlink_to(stale)

    _install_agent_file(src, dst)

    assert dst.is_file()
    assert not dst.is_symlink()
    assert dst.read_text() == "new content"


def test_sync_uses_agent_caster_when_available(tmp_path: Path):
    """sync_agent_symlinks calls agent-caster when refit.toml and roles/ exist."""
    core_dir = tmp_path / "core"
    (core_dir / "roles").mkdir(parents=True)
    (core_dir / "roles" / "scout.md").write_text("# Scout role")
    (core_dir / "refit.toml").write_text("[project]\nagents_dir = 'roles'\n")

    ws = tmp_path / "workspace"
    ws.mkdir()

    # Simulate agent-caster being available and writing the cast output
    def fake_run(cmd, **kwargs):
        import subprocess

        # Write the "cast" output that agent-caster would produce
        cast_out = core_dir / ".opencode" / "agents"
        cast_out.mkdir(parents=True, exist_ok=True)
        (cast_out / "scout.md").write_text("# Cast scout")
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    with patch("marrow_core.workspace.subprocess.run", side_effect=fake_run):
        sync_agent_symlinks(str(core_dir), str(ws))

    # Result should be a regular file (copied from cast output), not a symlink
    scout = ws / ".opencode" / "agents" / "scout.md"
    assert scout.is_file()
    assert scout.read_text() == "# Cast scout"


def test_sync_falls_back_to_symlinks_when_agent_caster_missing(tmp_path: Path):
    """sync_agent_symlinks falls back to symlinks when agent-caster is absent."""
    core_dir = tmp_path / "core"
    (core_dir / "roles").mkdir(parents=True)
    (core_dir / "roles" / "scout.md").write_text("# Scout role")
    (core_dir / "refit.toml").write_text("[project]\nagents_dir = 'roles'\n")
    # Also provide legacy agents/ dir for the symlink fallback
    (core_dir / "agents").mkdir(parents=True)
    (core_dir / "agents" / "scout.md").write_text("# Scout legacy")

    ws = tmp_path / "workspace"
    (ws / ".opencode" / "agents").mkdir(parents=True)

    with patch("marrow_core.workspace.subprocess.run", side_effect=FileNotFoundError):
        sync_agent_symlinks(str(core_dir), str(ws))

    scout = ws / ".opencode" / "agents" / "scout.md"
    assert scout.is_symlink()
    assert scout.read_text() == "# Scout legacy"
