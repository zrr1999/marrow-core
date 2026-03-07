"""Service file generation — launchd (macOS) and systemd (Linux).

These helpers are pure functions that take explicit parameters so they
remain testable without touching the filesystem.
"""

from __future__ import annotations

import getpass
import shutil
import sys
from pathlib import Path


def detect_platform() -> str:
    """Return 'macos' or 'linux' based on the current OS."""
    s = sys.platform
    if s == "darwin":
        return "macos"
    if s.startswith("linux"):
        return "linux"
    return s  # pass-through for other / test overrides


def _find_marrow_binary(core_dir: str) -> str:
    """Best-effort path to the marrow executable."""
    venv_bin = Path(core_dir) / ".venv" / "bin" / "marrow"
    if venv_bin.exists():
        return str(venv_bin)
    system_bin = shutil.which("marrow")
    if system_bin:
        return system_bin
    return str(venv_bin)  # fall back to venv path even if not present yet


def generate_launchd_plist(
    *,
    label: str = "com.marrow.heart",
    core_dir: str = "/opt/marrow-core",
    config_path: str = "/opt/marrow-core/marrow.toml",
    log_dir: str = "/Users/marrow/runtime/logs",
    user: str | None = None,
) -> str:
    """Render a launchd property list (macOS) for the marrow heartbeat service."""
    binary = _find_marrow_binary(core_dir)
    resolved_user = user or getpass.getuser()
    stdout_log = str(Path(log_dir) / "heart.stdout.log")
    stderr_log = str(Path(log_dir) / "heart.stderr.log")

    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>

  <key>ProgramArguments</key>
  <array>
    <string>{binary}</string>
    <string>run</string>
    <string>--config</string>
    <string>{config_path}</string>
    <string>--json-logs</string>
  </array>

  <key>WorkingDirectory</key>
  <string>{core_dir}</string>

  <key>UserName</key>
  <string>{resolved_user}</string>

  <key>KeepAlive</key>
  <true/>

  <key>StandardOutPath</key>
  <string>{stdout_log}</string>
  <key>StandardErrorPath</key>
  <string>{stderr_log}</string>
</dict>
</plist>
"""


def generate_systemd_unit(
    *,
    description: str = "Marrow self-evolving agent heartbeat",
    core_dir: str = "/opt/marrow-core",
    config_path: str = "/opt/marrow-core/marrow.toml",
    log_dir: str | None = None,
    user: str | None = None,
    after: str = "network.target",
) -> str:
    """Render a systemd service unit (Linux) for the marrow heartbeat service.

    Note: systemd captures stdout/stderr via journald by default.
    If log_dir is provided, StandardOutput/StandardError are redirected to files
    (requires the log directory to exist and be writable by the service user).
    """
    binary = _find_marrow_binary(core_dir)
    resolved_user = user or getpass.getuser()

    logging_lines = ""
    if log_dir:
        stdout_log = str(Path(log_dir) / "heart.stdout.log")
        stderr_log = str(Path(log_dir) / "heart.stderr.log")
        logging_lines = f"StandardOutput=append:{stdout_log}\nStandardError=append:{stderr_log}\n"

    return f"""\
[Unit]
Description={description}
After={after}
StartLimitIntervalSec=0

[Service]
Type=simple
User={resolved_user}
WorkingDirectory={core_dir}
ExecStart={binary} run --config {config_path} --json-logs
Restart=always
RestartSec=5
{logging_lines}
[Install]
WantedBy=multi-user.target
"""


def default_service_path(target_platform: str, label: str = "com.marrow.heart") -> Path:
    """Return the conventional installation path for the service file."""
    if target_platform == "macos":
        return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    # Linux: user systemd unit (no root required)
    return Path.home() / ".config" / "systemd" / "user" / "marrow-heart.service"


def install_instructions(target_platform: str, output_path: Path) -> str:
    """Return human-readable post-install instructions."""
    if target_platform == "macos":
        return (
            f"  launchctl load -w {output_path}\n"
            "  # To stop:  launchctl unload -w {path}\n".replace("{path}", str(output_path))
        )
    # Linux systemd (user mode)
    return (
        "  systemctl --user daemon-reload\n"
        "  systemctl --user enable --now marrow-heart.service\n"
        "  # To check status: systemctl --user status marrow-heart.service\n"
        "  # To stop:         systemctl --user stop marrow-heart.service\n"
    )
