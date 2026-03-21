"""Tests for the profile validation and setup utilities."""

from __future__ import annotations

import stat
import sys
import textwrap
from pathlib import Path

from typer.testing import CliRunner

from marrow_core.cli.__main__ import app
from marrow_core.profile import prepare_home, validate_context_providers, validate_role_references

runner = CliRunner()


# ── validate_context_providers ──────────────────────────────────────


def test_validate_context_providers_ok(tmp_path: Path) -> None:
    ctx = tmp_path / "context.d"
    ctx.mkdir()
    (ctx / "work_items.py").write_text("print('ok')\n", encoding="utf-8")

    issues = validate_context_providers(tmp_path)
    assert issues == []


def test_validate_context_providers_missing_dir(tmp_path: Path) -> None:
    issues = validate_context_providers(tmp_path)
    assert len(issues) == 1
    assert "missing context provider directory" in issues[0]


def test_validate_context_providers_empty_dir(tmp_path: Path) -> None:
    (tmp_path / "context.d").mkdir()

    issues = validate_context_providers(tmp_path)
    assert len(issues) == 1
    assert "no Python providers" in issues[0]


def test_validate_context_providers_syntax_error(tmp_path: Path) -> None:
    ctx = tmp_path / "context.d"
    ctx.mkdir()
    (ctx / "bad.py").write_text("def broken(\n", encoding="utf-8")

    issues = validate_context_providers(tmp_path)
    assert len(issues) == 1
    assert "syntax error" in issues[0]


def test_validate_context_providers_multiple_valid(tmp_path: Path) -> None:
    ctx = tmp_path / "context.d"
    ctx.mkdir()
    (ctx / "a.py").write_text("x = 1\n", encoding="utf-8")
    (ctx / "b.py").write_text("y = 2\n", encoding="utf-8")

    issues = validate_context_providers(tmp_path)
    assert issues == []


# ── validate_role_references ────────────────────────────────────────


def _build_roles(tmp_path: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = tmp_path / "roles" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def test_validate_role_references_ok(tmp_path: Path) -> None:
    _build_roles(
        tmp_path,
        {
            "orchestrator.md": "See leaders/builder for build tasks.",
            "leaders/builder.md": "I build things.",
            "specialists/coder.md": "I code.",
        },
    )

    issues = validate_role_references(tmp_path)
    assert issues == []


def test_validate_role_references_missing_ref(tmp_path: Path) -> None:
    _build_roles(
        tmp_path,
        {
            "orchestrator.md": "Delegate to leaders/phantom for magic.",
            "leaders/builder.md": "I build.",
        },
    )

    issues = validate_role_references(tmp_path)
    assert len(issues) == 1
    assert "leaders/phantom" in issues[0]


def test_validate_role_references_no_roles_dir(tmp_path: Path) -> None:
    issues = validate_role_references(tmp_path)
    assert issues == []


def test_validate_role_references_no_subdirs(tmp_path: Path) -> None:
    _build_roles(tmp_path, {"orchestrator.md": "Top-level only."})

    issues = validate_role_references(tmp_path)
    assert issues == []


# ── prepare_home ────────────────────────────────────────────────────


def test_prepare_home_creates_structure(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / ".opencode").mkdir()
    ctx = profile / "context.d"
    ctx.mkdir()
    (ctx / "work_items.py").write_text("print('ok')\n", encoding="utf-8")

    home = tmp_path / "home"
    prepare_home(profile, home)

    assert home.is_dir()
    assert (home / ".opencode").is_symlink()
    assert (home / ".opencode").resolve() == (profile / ".opencode").resolve()
    assert (home / "context.d" / "work_items.py").is_file()
    mode = (home / "context.d" / "work_items.py").stat().st_mode
    assert mode & stat.S_IXUSR


def test_prepare_home_idempotent(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / ".opencode").mkdir()
    ctx = profile / "context.d"
    ctx.mkdir()
    (ctx / "a.py").write_text("x = 1\n", encoding="utf-8")

    home = tmp_path / "home"
    prepare_home(profile, home)
    prepare_home(profile, home)  # second call should not fail

    assert (home / "context.d" / "a.py").is_file()


def test_prepare_home_no_opencode(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "context.d").mkdir()
    (profile / "context.d" / "p.py").write_text("pass\n", encoding="utf-8")

    home = tmp_path / "home"
    prepare_home(profile, home)

    assert not (home / ".opencode").exists()
    assert (home / "context.d" / "p.py").is_file()


# ── profile-setup CLI command ───────────────────────────────────────


def _write_profile_setup_config(
    tmp_path: Path,
    *,
    profile_root: Path | None = None,
) -> Path:
    workspace = tmp_path / "workspace"
    context_dir = workspace / "context.d"
    context_dir.mkdir(parents=True)
    script = context_dir / "00_queue.py"
    script.write_text("#!/usr/bin/env python3\nprint('queue ok')\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)

    home = tmp_path / "bot-home"
    home.mkdir(parents=True, exist_ok=True)
    pr = profile_root or tmp_path / "profile"

    config = tmp_path / "marrow.toml"
    config.write_text(
        textwrap.dedent(f"""\
            [profile]
            root_dir = {str(pr)!r}

            [service]
            mode = "single_user"

            [ipc]
            enabled = false

            [self_check]
            enabled = false

            [sync]
            enabled = false

            [[agents]]
            user = "testbot"
            name = "orchestrator"
            heartbeat_interval = 300
            heartbeat_timeout = 30
            workspace = {str(workspace)!r}
            home = {str(home)!r}
            agent_command = {sys.executable!r}
            context_dirs = [{str(context_dir)!r}]
        """),
        encoding="utf-8",
    )
    return config


def test_profile_setup_full_pass(monkeypatch, tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    ctx = profile / "context.d"
    ctx.mkdir()
    (ctx / "work_items.py").write_text("print('ok')\n", encoding="utf-8")
    (profile / ".opencode").mkdir()

    config = _write_profile_setup_config(tmp_path, profile_root=profile)
    home = tmp_path / "bot-home"

    # Stub dry-run to avoid real heartbeat execution.
    async def fake_run_single_user(config_path, *, once=False, dry_run=False, ipc=None):
        pass

    monkeypatch.setattr("marrow_core.cli.service._run_single_user", fake_run_single_user)

    result = runner.invoke(
        app,
        ["profile-setup", "--config", str(config), "--home", str(home)],
    )

    assert result.exit_code == 0, result.output
    assert "Profile setup complete" in result.output
    assert "[1/5]" in result.output
    assert "[5/5]" in result.output
    # Home directory should have .opencode symlink and context providers.
    assert (home / ".opencode").is_symlink()
    assert (home / "context.d" / "work_items.py").is_file()


def test_profile_setup_fails_on_missing_context_dir(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    # No context.d/ directory

    config = _write_profile_setup_config(tmp_path, profile_root=profile)

    result = runner.invoke(
        app,
        ["profile-setup", "--config", str(config), "--home", str(tmp_path / "bot-home")],
    )

    assert result.exit_code != 0
    assert "FAIL" in result.output


def test_profile_setup_no_home_option_uses_config(monkeypatch, tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    ctx = profile / "context.d"
    ctx.mkdir()
    (ctx / "p.py").write_text("pass\n", encoding="utf-8")

    config = _write_profile_setup_config(tmp_path, profile_root=profile)

    async def fake_run_single_user(config_path, *, once=False, dry_run=False, ipc=None):
        pass

    monkeypatch.setattr("marrow_core.cli.service._run_single_user", fake_run_single_user)

    result = runner.invoke(app, ["profile-setup", "--config", str(config)])

    assert result.exit_code == 0, result.output
    assert "Profile setup complete" in result.output
