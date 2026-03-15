"""Tests for marrow_core.workspace."""

from __future__ import annotations

from pathlib import Path

from marrow_core.config import ProfileConfig
from marrow_core.contracts import WORKSPACE_DIRS
from marrow_core.workspace import (
    ensure_workspace_dirs,
    load_rules,
    verify_workspace,
)


def test_verify_workspace(tmp_path: Path):
    assert verify_workspace(str(tmp_path)) is True
    assert verify_workspace("/nonexistent/path/abc") is False


def test_ensure_workspace_dirs(tmp_path: Path):
    ensure_workspace_dirs(str(tmp_path))
    for directory in WORKSPACE_DIRS:
        assert (tmp_path / directory).is_dir(), f"missing {directory}"


def test_ensure_workspace_dirs_creates_sync_state_parent(tmp_path: Path) -> None:
    ensure_workspace_dirs(str(tmp_path))

    assert (tmp_path / "runtime" / "state").is_dir()


def test_load_rules(tmp_path: Path):
    rules_path = tmp_path / "rules.md"
    rules_path.write_text("# Rules\nDo not break things.", encoding="utf-8")
    text = load_rules(ProfileConfig(rules_path=str(rules_path)))
    assert "Do not break things" in text


def test_load_rules_missing(tmp_path: Path):
    assert load_rules(str(tmp_path)) == ""
