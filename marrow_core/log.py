"""Logging setup — loguru with JSON or compact human output.

When running as a launchd / systemd daemon the *file sink* should be
preferred so that the host process's stderr redirect (e.g.
``StandardErrorPath`` in a plist) can safely point to ``/dev/null``
instead of accumulating gigabytes of unbounded JSON.

Usage::

    setup_logging(json_logs=True, log_file=Path("/Users/marrow/runtime/logs/marrow.log"))
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

# Default rotation/retention for the file sink.
_FILE_ROTATION = "50 MB"
_FILE_RETENTION = "7 days"
_FILE_COMPRESSION = "gz"


def setup_logging(
    *,
    verbose: bool = False,
    json_logs: bool = False,
    log_file: Path | None = None,
) -> None:
    """Configure loguru for the marrow scheduler.

    Parameters
    ----------
    verbose:
        Set level to DEBUG (default INFO).
    json_logs:
        Emit newline-delimited JSON records on the stderr sink.
        The file sink always uses JSON when this flag is set.
    log_file:
        Optional path for a **rotating** file sink.  When provided loguru
        writes to this file with automatic rotation at 50 MB, 7-day
        retention, and gzip compression of rotated files.  Useful when
        running as a daemon so that the host stderr redirect can be
        ``/dev/null``.
    """
    logger.remove()
    level = "DEBUG" if verbose else "INFO"

    # --- stderr sink ---
    if json_logs:
        logger.add(sys.stderr, level=level, serialize=True)
    else:
        logger.add(
            sys.stderr,
            level=level,
            format="[{time:HH:mm:ss}] {name}: {message}",
            colorize=True,
        )

    # --- optional rotating file sink ---
    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            str(log_file),
            level=level,
            serialize=json_logs,  # match the stderr format
            rotation=_FILE_ROTATION,
            retention=_FILE_RETENTION,
            compression=_FILE_COMPRESSION,
            enqueue=True,  # thread-safe async writes
        )


__all__ = ["logger", "setup_logging"]
