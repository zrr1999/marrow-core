"""Tests for marrow_core.service — launchd / systemd file generation."""

from __future__ import annotations

from pathlib import Path

from marrow_core.service import (
    default_service_path,
    detect_platform,
    generate_launchd_plist,
    generate_systemd_unit,
    install_instructions,
)

# ---------------------------------------------------------------------------
# generate_launchd_plist
# ---------------------------------------------------------------------------


def test_launchd_contains_label():
    plist = generate_launchd_plist(
        label="com.test.marrow",
        core_dir="/opt/mc",
        config_path="/opt/mc/marrow.toml",
        log_dir="/tmp/logs",
        user="testuser",
    )
    assert "<string>com.test.marrow</string>" in plist


def test_launchd_contains_binary_path():
    plist = generate_launchd_plist(
        core_dir="/opt/mc",
        config_path="/opt/mc/marrow.toml",
        log_dir="/tmp/logs",
        user="testuser",
    )
    # The binary should be somewhere inside core_dir/.venv or the system path
    assert "marrow" in plist
    assert "/opt/mc" in plist


def test_launchd_contains_user():
    plist = generate_launchd_plist(
        core_dir="/opt/mc",
        config_path="/opt/mc/marrow.toml",
        log_dir="/tmp/logs",
        user="alice",
    )
    assert "<string>alice</string>" in plist


def test_launchd_contains_log_paths():
    plist = generate_launchd_plist(
        core_dir="/opt/mc",
        config_path="/opt/mc/marrow.toml",
        log_dir="/var/log/marrow",
        user="testuser",
    )
    assert "/var/log/marrow/heart.stdout.log" in plist
    assert "/var/log/marrow/heart.stderr.log" in plist


def test_launchd_keep_alive():
    plist = generate_launchd_plist(
        core_dir="/opt/mc",
        config_path="/opt/mc/marrow.toml",
        log_dir="/tmp/logs",
        user="u",
    )
    assert "<true/>" in plist


def test_launchd_config_path_in_args():
    plist = generate_launchd_plist(
        core_dir="/opt/mc",
        config_path="/custom/path/marrow.toml",
        log_dir="/tmp/logs",
        user="u",
    )
    assert "/custom/path/marrow.toml" in plist


def test_launchd_is_valid_xml():
    """Minimal XML structure check — starts with the XML declaration."""
    plist = generate_launchd_plist(
        core_dir="/opt/mc",
        config_path="/opt/mc/marrow.toml",
        log_dir="/tmp/logs",
        user="u",
    )
    assert plist.startswith('<?xml version="1.0"')
    assert "</plist>" in plist


# ---------------------------------------------------------------------------
# generate_systemd_unit
# ---------------------------------------------------------------------------


def test_systemd_contains_exec_start():
    unit = generate_systemd_unit(
        core_dir="/opt/mc",
        config_path="/opt/mc/marrow.toml",
        user="alice",
    )
    assert "ExecStart=" in unit
    assert "marrow" in unit
    assert "/opt/mc/marrow.toml" in unit


def test_systemd_contains_user():
    unit = generate_systemd_unit(
        core_dir="/opt/mc",
        config_path="/opt/mc/marrow.toml",
        user="bob",
    )
    assert "User=bob" in unit


def test_systemd_restart_always():
    unit = generate_systemd_unit(
        core_dir="/opt/mc",
        config_path="/opt/mc/marrow.toml",
        user="u",
    )
    assert "Restart=always" in unit


def test_systemd_no_log_redirect_by_default():
    unit = generate_systemd_unit(
        core_dir="/opt/mc",
        config_path="/opt/mc/marrow.toml",
        user="u",
    )
    assert "StandardOutput=" not in unit
    assert "StandardError=" not in unit


def test_systemd_log_redirect_when_log_dir():
    unit = generate_systemd_unit(
        core_dir="/opt/mc",
        config_path="/opt/mc/marrow.toml",
        user="u",
        log_dir="/var/log/marrow",
    )
    assert "StandardOutput=append:/var/log/marrow/heart.stdout.log" in unit
    assert "StandardError=append:/var/log/marrow/heart.stderr.log" in unit


def test_systemd_install_section():
    unit = generate_systemd_unit(
        core_dir="/opt/mc",
        config_path="/opt/mc/marrow.toml",
        user="u",
    )
    assert "[Install]" in unit
    assert "WantedBy=multi-user.target" in unit


def test_systemd_after_network():
    unit = generate_systemd_unit(
        core_dir="/opt/mc",
        config_path="/opt/mc/marrow.toml",
        user="u",
    )
    assert "After=network.target" in unit


# ---------------------------------------------------------------------------
# default_service_path
# ---------------------------------------------------------------------------


def test_default_service_path_macos():
    p = default_service_path("macos")
    assert str(p).endswith(".plist")
    assert "LaunchAgents" in str(p)


def test_default_service_path_linux():
    p = default_service_path("linux")
    assert str(p).endswith(".service")
    assert "systemd" in str(p)


# ---------------------------------------------------------------------------
# detect_platform
# ---------------------------------------------------------------------------


def test_detect_platform_returns_string():
    result = detect_platform()
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# install_instructions
# ---------------------------------------------------------------------------


def test_install_instructions_macos():
    p = Path("/some/path/com.test.plist")
    instructions = install_instructions("macos", p)
    assert "launchctl" in instructions
    assert str(p) in instructions


def test_install_instructions_linux():
    p = Path("/home/user/.config/systemd/user/marrow-heart.service")
    instructions = install_instructions("linux", p)
    assert "systemctl" in instructions
    assert "daemon-reload" in instructions
