"""Tests for marrow_core.workspace."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from marrow_core.workspace import (
    _agent_caster_available,
    _install_agent_content,
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
    # Create fake core agents (legacy agents/ dir for symlink fallback)
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
    """_agent_caster_available returns False when agent_caster is not importable."""
    with patch("importlib.import_module", side_effect=ImportError("no module")):
        assert _agent_caster_available() is False


def test_agent_caster_available_when_present():
    """_agent_caster_available returns True when agent_caster is importable."""
    with patch("importlib.import_module", return_value=MagicMock()):
        assert _agent_caster_available() is True


def test_install_agent_content_writes(tmp_path: Path):
    """_install_agent_content writes content to the destination file."""
    dst = tmp_path / "agents" / "scout.md"
    dst.parent.mkdir()

    _install_agent_content(dst, "# Scout generated")

    assert dst.is_file()
    assert not dst.is_symlink()
    assert dst.read_text() == "# Scout generated"


def test_install_agent_content_replaces_symlink(tmp_path: Path):
    """_install_agent_content removes existing symlink before writing."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    dst = agents_dir / "scout.md"
    # Create a stale symlink
    stale = tmp_path / "old.md"
    stale.write_text("old")
    dst.symlink_to(stale)

    _install_agent_content(dst, "new content")

    assert dst.is_file()
    assert not dst.is_symlink()
    assert dst.read_text() == "new content"


def test_sync_uses_agent_caster_when_available(tmp_path: Path):
    """sync_agent_symlinks delegates to _cast_via_agent_caster when conditions are met."""
    core_dir = tmp_path / "core"
    (core_dir / "roles").mkdir(parents=True)
    (core_dir / "roles" / "scout.md").write_text("# Scout role")
    (core_dir / "refit.toml").write_text("[project]\nagents_dir = 'roles'\n")

    ws = tmp_path / "workspace"
    ws.mkdir()

    cast_called_with: list[tuple] = []

    def fake_cast(core_path: Path, workspace: str) -> None:
        cast_called_with.append((core_path, workspace))
        # Simulate what _cast_via_agent_caster would write
        dst = Path(workspace) / ".opencode" / "agents" / "scout.md"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("# Cast scout")

    with (
        patch("marrow_core.workspace._agent_caster_available", return_value=True),
        patch("marrow_core.workspace._cast_via_agent_caster", side_effect=fake_cast),
    ):
        sync_agent_symlinks(str(core_dir), str(ws))

    assert len(cast_called_with) == 1
    # Result should be a regular file (written from cast output), not a symlink
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

    with patch("marrow_core.workspace._agent_caster_available", return_value=False):
        sync_agent_symlinks(str(core_dir), str(ws))

    scout = ws / ".opencode" / "agents" / "scout.md"
    assert scout.is_symlink()
    assert scout.read_text() == "# Scout legacy"
