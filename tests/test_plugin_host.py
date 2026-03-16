"""Tests for hosted plugin helpers."""

from __future__ import annotations

from pathlib import Path

from marrow_core.config import PluginConfig
from marrow_core.plugin_host import (
    build_hosted_plugins,
    ensure_plugin_host_dirs,
    render_plugin_manifest,
    render_plugin_service_files,
    write_plugin_manifest,
)


def test_plugin_host_creates_runtime_dirs_and_manifest(tmp_path: Path) -> None:
    ensure_plugin_host_dirs(tmp_path)
    plugins = [
        PluginConfig(
            name="dashboard",
            kind="dashboard",
            command="python",
            args=["-m", "marrow_dashboard", "serve"],
            workspace=str(tmp_path),
            capabilities=["read_work_items"],
        )
    ]

    hosted = build_hosted_plugins(plugins, workspace=tmp_path)
    manifest = render_plugin_manifest(plugins, workspace=tmp_path)

    assert len(hosted) == 1
    assert hosted[0].argv == ("python", "-m", "marrow_dashboard", "serve")
    assert (tmp_path / "runtime" / "plugins" / "dashboard").is_dir()
    assert '"name": "dashboard"' in manifest
    assert '"read_work_items"' in manifest


def test_plugin_host_renders_background_service_unit(tmp_path: Path) -> None:
    plugins = [
        PluginConfig(
            name="gateway",
            kind="background_service",
            command="python",
            args=["-m", "marrow_gateway", "serve"],
            cwd=str(tmp_path / "gateway"),
            workspace=str(tmp_path),
            auto_start=True,
            env={"MARROW_ENV": "dev"},
        )
    ]

    files = render_plugin_service_files(platform="linux", plugins=plugins, workspace=tmp_path)

    assert [file.name for file in files] == ["marrow-plugin-gateway.service"]
    assert "ExecStart=python -m marrow_gateway serve" in files[0].content
    assert "Environment=MARROW_ENV=dev" in files[0].content


def test_plugin_host_writes_manifest_file(tmp_path: Path) -> None:
    plugins = [
        PluginConfig(
            name="dashboard",
            kind="dashboard",
            command="python",
            args=["-m", "marrow_dashboard", "serve"],
            workspace=str(tmp_path),
        )
    ]

    path = write_plugin_manifest(
        plugins,
        workspace=tmp_path,
        destination=tmp_path / "runtime" / "plugins" / "manifest.json",
    )

    assert path.exists()
    assert '"name": "dashboard"' in path.read_text(encoding="utf-8")
