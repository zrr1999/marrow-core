"""Cross-platform service file rendering and writing."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from marrow_core.runtime import DEFAULT_SERVICE_PATH, marrow_binary


@dataclass(frozen=True)
class ServiceFile:
    name: str
    content: str


def detect_service_platform(platform: str) -> str:
    if platform == "auto":
        return "darwin" if sys.platform == "darwin" else "linux"
    if platform not in {"darwin", "linux"}:
        raise ValueError(f"unsupported platform: {platform}")
    return platform


def render_service_files(
    *,
    platform: str,
    core_dir: str,
    config_path: Path,
    workspace: str,
) -> list[ServiceFile]:
    target = detect_service_platform(platform)
    if target == "darwin":
        return _render_launchd_files(
            core_dir=core_dir, config_path=config_path, workspace=workspace
        )
    return _render_systemd_files(core_dir=core_dir, config_path=config_path, workspace=workspace)


def write_service_files(files: list[ServiceFile], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for service_file in files:
        path = output_dir / service_file.name
        path.write_text(service_file.content, encoding="utf-8")
        written.append(path)
    return written


def _render_launchd_files(*, core_dir: str, config_path: Path, workspace: str) -> list[ServiceFile]:
    binary = marrow_binary(core_dir)
    config = str(config_path)
    path_env = DEFAULT_SERVICE_PATH
    return [
        ServiceFile(
            name="com.marrow.heart.plist",
            content=(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"\n'
                '  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0">\n'
                "<dict>\n"
                "  <key>Label</key>\n"
                "  <string>com.marrow.heart</string>\n\n"
                "  <key>ProgramArguments</key>\n"
                "  <array>\n"
                f"    <string>{binary}</string>\n"
                "    <string>run</string>\n"
                "    <string>--config</string>\n"
                f"    <string>{config}</string>\n"
                "    <string>--json-logs</string>\n"
                "  </array>\n\n"
                "  <key>EnvironmentVariables</key>\n"
                "  <dict>\n"
                f"    <key>PATH</key><string>{path_env}</string>\n"
                "  </dict>\n\n"
                "  <key>WorkingDirectory</key>\n"
                f"  <string>{core_dir}</string>\n\n"
                "  <key>UserName</key>\n"
                "  <string>marrow</string>\n\n"
                "  <key>KeepAlive</key>\n"
                "  <true/>\n\n"
                "  <key>StandardOutPath</key>\n"
                f"  <string>{workspace}/runtime/logs/heart.stdout.log</string>\n"
                "  <key>StandardErrorPath</key>\n"
                f"  <string>{workspace}/runtime/logs/heart.stderr.log</string>\n"
                "</dict>\n"
                "</plist>\n"
            ),
        ),
    ]


def _render_systemd_files(*, core_dir: str, config_path: Path, workspace: str) -> list[ServiceFile]:
    binary = marrow_binary(core_dir)
    config = str(config_path)
    return [
        ServiceFile(
            name="marrow-heart.service",
            content=(
                "[Unit]\n"
                "Description=Marrow heartbeat scheduler\n"
                "After=network.target\n\n"
                "[Service]\n"
                "Type=simple\n"
                "User=marrow\n"
                f"WorkingDirectory={core_dir}\n"
                f"Environment=PATH={DEFAULT_SERVICE_PATH}\n"
                f"ExecStart={binary} run --config {config} --json-logs\n"
                "Restart=always\n"
                "RestartSec=5\n"
                f"StandardOutput=append:{workspace}/runtime/logs/heart.stdout.log\n"
                f"StandardError=append:{workspace}/runtime/logs/heart.stderr.log\n\n"
                "[Install]\n"
                "WantedBy=multi-user.target\n"
            ),
        ),
    ]
