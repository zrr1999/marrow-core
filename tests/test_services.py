"""Tests for service file rendering."""

from __future__ import annotations

from pathlib import Path

import pytest

from marrow_core.services import detect_service_platform, render_service_files, write_service_files


def test_detect_service_platform_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        detect_service_platform("windows")


def test_render_launchd_service_files_include_path_and_logs(tmp_path: Path) -> None:
    files = render_service_files(
        platform="darwin",
        core_dir="/opt/marrow-core",
        config_path=Path("/opt/marrow-core/marrow.toml"),
        workspace="/Users/marrow",
    )

    assert [file.name for file in files] == [
        "com.marrow.heart.plist",
        "com.marrow.heart.sync.plist",
    ]
    assert "EnvironmentVariables" in files[0].content
    assert "/Users/marrow/runtime/logs/heart.stdout.log" in files[0].content


def test_render_systemd_service_files_include_timer(tmp_path: Path) -> None:
    files = render_service_files(
        platform="linux",
        core_dir="/opt/marrow-core",
        config_path=Path("/opt/marrow-core/marrow.toml"),
        workspace="/Users/marrow",
    )

    assert [file.name for file in files] == [
        "marrow-heart.service",
        "marrow-heart-sync.service",
        "marrow-heart-sync.timer",
    ]
    assert (
        "ExecStart=/opt/marrow-core/.venv/bin/marrow run "
        "--config /opt/marrow-core/marrow.toml --json-logs" in files[0].content
    )
    assert "OnCalendar=*-*-* 00:05:00" in files[2].content


def test_write_service_files_persists_rendered_units(tmp_path: Path) -> None:
    files = render_service_files(
        platform="linux",
        core_dir="/opt/marrow-core",
        config_path=Path("/opt/marrow-core/marrow.toml"),
        workspace="/Users/marrow",
    )

    written = write_service_files(files, tmp_path)

    assert len(written) == 3
    assert (tmp_path / "marrow-heart.service").exists()
