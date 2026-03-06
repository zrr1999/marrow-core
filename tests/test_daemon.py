"""Tests for marrow_core.daemon — launchd / systemd service generation."""

from __future__ import annotations

import platform
from pathlib import Path

import pytest

from marrow_core.daemon import (
    generate_launchd_plist,
    generate_systemd_unit,
    is_linux,
    is_macos,
)


@pytest.fixture
def fake_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "marrow.toml"
    cfg.write_text("[core]\n")
    return cfg


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------


def test_platform_helpers_mutually_exclusive():
    """Exactly one of is_macos / is_linux should be True on supported platforms."""
    system = platform.system()
    if system in ("Darwin", "Linux"):
        assert is_macos() != is_linux()


# ---------------------------------------------------------------------------
# launchd plist generation
# ---------------------------------------------------------------------------


def test_generate_launchd_plist_contains_label(fake_config: Path):
    plist = generate_launchd_plist(fake_config, label="com.test.marrow")
    assert "<string>com.test.marrow</string>" in plist


def test_generate_launchd_plist_contains_config_path(fake_config: Path):
    plist = generate_launchd_plist(fake_config)
    assert str(fake_config.resolve()) in plist


def test_generate_launchd_plist_run_command(fake_config: Path):
    plist = generate_launchd_plist(fake_config)
    assert "<string>run</string>" in plist


def test_generate_launchd_plist_keep_alive(fake_config: Path):
    plist = generate_launchd_plist(fake_config)
    assert "<key>KeepAlive</key>" in plist
    assert "<true/>" in plist


def test_generate_launchd_plist_log_paths(fake_config: Path):
    plist = generate_launchd_plist(fake_config)
    assert "marrow.log" in plist
    assert "marrow.err" in plist


# ---------------------------------------------------------------------------
# systemd unit generation
# ---------------------------------------------------------------------------


def test_generate_systemd_unit_contains_config_path(fake_config: Path):
    unit = generate_systemd_unit(fake_config)
    assert str(fake_config.resolve()) in unit


def test_generate_systemd_unit_run_command(fake_config: Path):
    unit = generate_systemd_unit(fake_config)
    assert "run" in unit


def test_generate_systemd_unit_restart_policy(fake_config: Path):
    unit = generate_systemd_unit(fake_config)
    assert "Restart=on-failure" in unit


def test_generate_systemd_unit_install_section(fake_config: Path):
    unit = generate_systemd_unit(fake_config)
    assert "[Install]" in unit
    assert "WantedBy=default.target" in unit


def test_generate_systemd_unit_service_name(fake_config: Path):
    unit = generate_systemd_unit(fake_config, service="mymarrow")
    # The unit file content doesn't embed the service name itself;
    # the filename would be mymarrow.service — just check it's valid TOML-like sections.
    assert "[Service]" in unit
    assert "[Unit]" in unit
