"""Background daemon management — generate and install launchd / systemd service files.

Platform detection:
  - macOS  → launchd plist under ~/Library/LaunchAgents/
  - Linux  → systemd user unit under ~/.config/systemd/user/

Usage (via CLI):
  marrow daemon install   — generate and install the service, then start it
  marrow daemon uninstall — stop and remove the service
  marrow daemon status    — show whether the service is loaded/running
"""

from __future__ import annotations

import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def _marrow_bin() -> str:
    """Return the path to the marrow executable."""
    exe = shutil.which("marrow")
    if exe:
        return exe
    # Fallback: use the same Python interpreter with -m
    return f"{sys.executable} -m marrow_core"


# ---------------------------------------------------------------------------
# macOS launchd
# ---------------------------------------------------------------------------

_PLIST_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        {args}
    </array>
    <key>WorkingDirectory</key>
    <string>{workdir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_out}</string>
    <key>StandardErrorPath</key>
    <string>{log_err}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>{home}</string>
        <key>PATH</key>
        <string>{path}</string>
    </dict>
</dict>
</plist>
"""


def _plist_path(label: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def generate_launchd_plist(config: Path, label: str = "com.marrow.heartbeat") -> str:
    """Return the content of a launchd plist for `marrow run --config <config>`."""
    marrow = _marrow_bin()
    cmd_parts = [*shlex.split(marrow), "run", "--config", str(config.resolve())]
    args_xml = "\n        ".join(f"<string>{p}</string>" for p in cmd_parts)
    log_dir = Path.home() / "Library" / "Logs" / "marrow"
    log_dir.mkdir(parents=True, exist_ok=True)
    import os

    return _PLIST_TEMPLATE.format(
        label=label,
        args=args_xml,
        workdir=str(config.parent.resolve()),
        log_out=str(log_dir / "marrow.log"),
        log_err=str(log_dir / "marrow.err"),
        home=str(Path.home()),
        path=os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    )


def install_launchd(config: Path, label: str = "com.marrow.heartbeat") -> Path:
    """Write plist and load via launchctl.  Returns plist path."""
    plist_content = generate_launchd_plist(config, label)
    dest = _plist_path(label)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(plist_content)
    # Unload first (ignore errors — it may not be loaded yet)
    subprocess.run(["launchctl", "unload", str(dest)], capture_output=True)
    subprocess.run(["launchctl", "load", "-w", str(dest)], check=True)
    return dest


def uninstall_launchd(label: str = "com.marrow.heartbeat") -> None:
    """Unload and remove the plist."""
    dest = _plist_path(label)
    if dest.exists():
        subprocess.run(["launchctl", "unload", str(dest)], capture_output=True)
        dest.unlink()


def status_launchd(label: str = "com.marrow.heartbeat") -> str:
    """Return a human-readable status string."""
    result = subprocess.run(["launchctl", "list", label], capture_output=True, text=True)
    if result.returncode != 0:
        return f"not loaded (plist: {_plist_path(label)})"
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Linux systemd
# ---------------------------------------------------------------------------

_UNIT_TEMPLATE = """\
[Unit]
Description=marrow-core heartbeat scheduler
After=network.target

[Service]
Type=simple
ExecStart={exec_start}
WorkingDirectory={workdir}
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment="HOME={home}"
Environment="PATH={path}"

[Install]
WantedBy=default.target
"""


def _unit_path(service: str = "marrow") -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{service}.service"


def generate_systemd_unit(config: Path, service: str = "marrow") -> str:
    """Return the content of a systemd user unit for `marrow run --config <config>`."""
    marrow = _marrow_bin()
    cmd = shlex.join([*shlex.split(marrow), "run", "--config", str(config.resolve())])
    import os

    return _UNIT_TEMPLATE.format(
        exec_start=cmd,
        workdir=str(config.parent.resolve()),
        home=str(Path.home()),
        path=os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    )


def install_systemd(config: Path, service: str = "marrow") -> Path:
    """Write unit file and enable/start via systemctl.  Returns unit path."""
    unit_content = generate_systemd_unit(config, service)
    dest = _unit_path(service)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(unit_content)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", service], check=True)
    return dest


def uninstall_systemd(service: str = "marrow") -> None:
    """Disable, stop, and remove the unit file."""
    subprocess.run(["systemctl", "--user", "disable", "--now", service], capture_output=True)
    dest = _unit_path(service)
    if dest.exists():
        dest.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)


def status_systemd(service: str = "marrow") -> str:
    """Return a human-readable status string."""
    result = subprocess.run(
        ["systemctl", "--user", "status", service], capture_output=True, text=True
    )
    return result.stdout.strip() or result.stderr.strip()


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------


def is_macos() -> bool:
    return platform.system() == "Darwin"


def is_linux() -> bool:
    return platform.system() == "Linux"


def install_daemon(config: Path) -> Path:
    """Install the background service for the current platform."""
    if is_macos():
        return install_launchd(config)
    elif is_linux():
        return install_systemd(config)
    else:
        raise NotImplementedError(f"daemon install not supported on {platform.system()}")


def uninstall_daemon() -> None:
    """Remove the background service for the current platform."""
    if is_macos():
        uninstall_launchd()
    elif is_linux():
        uninstall_systemd()
    else:
        raise NotImplementedError(f"daemon uninstall not supported on {platform.system()}")


def daemon_status() -> str:
    """Return status string for the current platform."""
    if is_macos():
        return status_launchd()
    elif is_linux():
        return status_systemd()
    else:
        return f"daemon status not supported on {platform.system()}"
