"""Tests for service file rendering."""

from __future__ import annotations

from pathlib import Path

import pytest

from marrow_core.services import (
    detect_service_platform,
    render_service_files,
    resolve_service_config_path,
    write_service_files,
)


def test_detect_service_platform_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        detect_service_platform("windows")


def test_render_launchd_service_files_include_path_and_logs(tmp_path: Path) -> None:
    files = render_service_files(
        platform="darwin",
        core_dir="/opt/marrow-core",
        service_config_path=resolve_service_config_path("darwin"),
        service_user="",
        log_dir="/var/lib/marrow/logs",
    )

    assert [file.name for file in files] == ["com.marrow.heart.plist"]
    assert "EnvironmentVariables" in files[0].content
    assert "/var/lib/marrow/logs/heart.stdout.log" in files[0].content
    assert "/Library/Application Support/marrow/marrow.toml" in files[0].content
    assert "UserName" not in files[0].content


def test_render_systemd_service_files_only_include_primary_unit(tmp_path: Path) -> None:
    files = render_service_files(
        platform="linux",
        core_dir="/opt/marrow-core",
        service_config_path=resolve_service_config_path("linux"),
        service_user="marrow",
        log_dir="/Users/marrow/runtime/logs",
    )

    assert [file.name for file in files] == ["marrow-heart.service"]
    assert (
        "ExecStart=/opt/marrow-core/.venv/bin/marrow run "
        "--config /etc/marrow/marrow.toml --json-logs" in files[0].content
    )
    assert "User=marrow" in files[0].content


def test_write_service_files_persists_rendered_units(tmp_path: Path) -> None:
    files = render_service_files(
        platform="linux",
        core_dir="/opt/marrow-core",
        service_config_path=resolve_service_config_path("linux"),
        service_user="",
        log_dir="/var/lib/marrow/logs",
    )

    written = write_service_files(files, tmp_path)

    assert len(written) == 1
    assert (tmp_path / "marrow-heart.service").exists()
