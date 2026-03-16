"""Minimal plugin/background-service host helpers."""

from __future__ import annotations

import json
import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from marrow_core.config import PluginConfig
from marrow_core.services import ServiceFile, detect_service_platform


@dataclass(frozen=True)
class HostedPlugin:
    """Resolved plugin process metadata for host-side rendering."""

    name: str
    kind: str
    argv: tuple[str, ...]
    cwd: str
    workspace: str
    config_path: str
    env: dict[str, str]
    capabilities: tuple[str, ...]
    runtime_dir: Path
    log_dir: Path
    auto_start: bool


def ensure_plugin_host_dirs(workspace: str | Path) -> list[Path]:
    """Create runtime directories needed by hosted plugins."""
    base = Path(workspace)
    paths = [
        base / "plugins",
        base / "runtime" / "plugins",
        base / "runtime" / "logs" / "plugins",
    ]
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
    return paths


def build_hosted_plugins(
    plugins: Sequence[PluginConfig], *, workspace: str | Path
) -> list[HostedPlugin]:
    """Resolve runtime defaults for enabled plugins."""
    workspace_path = Path(workspace)
    ensure_plugin_host_dirs(workspace_path)
    hosted: list[HostedPlugin] = []
    for plugin in plugins:
        if not plugin.enabled:
            continue
        runtime_dir = workspace_path / "runtime" / "plugins" / plugin.name
        log_dir = workspace_path / "runtime" / "logs" / "plugins" / plugin.name
        runtime_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)
        argv = (plugin.command, *plugin.args)
        hosted.append(
            HostedPlugin(
                name=plugin.name,
                kind=plugin.kind,
                argv=argv,
                cwd=plugin.cwd or plugin.workspace or str(workspace_path),
                workspace=plugin.workspace or str(workspace_path),
                config_path=plugin.config_path,
                env=dict(plugin.env),
                capabilities=tuple(plugin.capabilities),
                runtime_dir=runtime_dir,
                log_dir=log_dir,
                auto_start=plugin.auto_start,
            )
        )
    return hosted


def render_plugin_manifest(plugins: Sequence[PluginConfig], *, workspace: str | Path) -> str:
    """Render a portable JSON manifest describing hosted plugins."""
    manifest = {
        "plugins": [
            {
                "name": plugin.name,
                "kind": plugin.kind,
                "argv": list(plugin.argv),
                "cwd": plugin.cwd,
                "workspace": plugin.workspace,
                "config_path": plugin.config_path,
                "env": plugin.env,
                "capabilities": list(plugin.capabilities),
                "runtime_dir": str(plugin.runtime_dir),
                "log_dir": str(plugin.log_dir),
                "auto_start": plugin.auto_start,
            }
            for plugin in build_hosted_plugins(plugins, workspace=workspace)
        ]
    }
    return json.dumps(manifest, indent=2, ensure_ascii=False)


def write_plugin_manifest(
    plugins: Sequence[PluginConfig], *, workspace: str | Path, destination: Path
) -> Path:
    """Write the hosted-plugin manifest to disk."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        render_plugin_manifest(plugins, workspace=workspace),
        encoding="utf-8",
    )
    return destination


def render_plugin_service_files(
    *, platform: str, plugins: Sequence[PluginConfig], workspace: str | Path
) -> list[ServiceFile]:
    """Render autostart background-service units for hosted plugins."""
    target = detect_service_platform(platform)
    service_files: list[ServiceFile] = []
    for plugin in build_hosted_plugins(plugins, workspace=workspace):
        if plugin.kind != "background_service" or not plugin.auto_start:
            continue
        if target == "darwin":
            service_files.append(_render_launchd_plugin(plugin))
        else:
            service_files.append(_render_systemd_plugin(plugin))
    return service_files


def _render_launchd_plugin(plugin: HostedPlugin) -> ServiceFile:
    env_block = ""
    if plugin.env:
        entries = "\n".join(
            f"    <key>{key}</key><string>{value}</string>"
            for key, value in sorted(plugin.env.items())
        )
        env_block = f"  <key>EnvironmentVariables</key>\n  <dict>\n{entries}\n  </dict>\n\n"
    argv_block = "\n".join(f"    <string>{arg}</string>" for arg in plugin.argv)
    return ServiceFile(
        name=f"com.marrow.plugin.{plugin.name}.plist",
        content=(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"\n'
            '  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n'
            "<dict>\n"
            "  <key>Label</key>\n"
            f"  <string>com.marrow.plugin.{plugin.name}</string>\n\n"
            "  <key>ProgramArguments</key>\n"
            "  <array>\n"
            f"{argv_block}\n"
            "  </array>\n\n"
            "  <key>WorkingDirectory</key>\n"
            f"  <string>{plugin.cwd}</string>\n\n"
            f"{env_block}"
            "  <key>KeepAlive</key>\n"
            "  <true/>\n\n"
            "  <key>StandardOutPath</key>\n"
            f"  <string>{plugin.log_dir}/stdout.log</string>\n"
            "  <key>StandardErrorPath</key>\n"
            f"  <string>{plugin.log_dir}/stderr.log</string>\n"
            "</dict>\n"
            "</plist>\n"
        ),
    )


def _render_systemd_plugin(plugin: HostedPlugin) -> ServiceFile:
    env_lines = "".join(
        f"Environment={key}={shlex.quote(value)}\n" for key, value in sorted(plugin.env.items())
    )
    exec_start = " ".join(shlex.quote(arg) for arg in plugin.argv)
    return ServiceFile(
        name=f"marrow-plugin-{plugin.name}.service",
        content=(
            "[Unit]\n"
            f"Description=Marrow plugin {plugin.name}\n"
            "After=network.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"WorkingDirectory={plugin.cwd}\n"
            f"{env_lines}"
            f"ExecStart={exec_start}\n"
            "Restart=always\n"
            "RestartSec=5\n"
            f"StandardOutput=append:{plugin.log_dir}/stdout.log\n"
            f"StandardError=append:{plugin.log_dir}/stderr.log\n\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
        ),
    )
