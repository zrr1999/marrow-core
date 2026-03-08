"""Exec-log pruning — keep disk usage from growing unbounded.

Two independent knobs (either or both may be set):
  - ``max_age_days``: delete any file older than N days.
  - ``max_count``:    after age-based deletion, if the remaining file count
                      still exceeds this limit, delete the oldest files first
                      until the count is within budget.

The function is designed to be called from the heartbeat loop after each
agent run.  It is synchronous and fast (only reads stat(2) per file, no
file content reads).
"""

from __future__ import annotations

import time
from pathlib import Path

from loguru import logger


def prune_exec_logs(
    log_dir: Path,
    *,
    max_age_days: int = 7,
    max_count: int = 200,
) -> int:
    """Delete stale exec-log files from *log_dir*.

    Parameters
    ----------
    log_dir:
        Directory that contains per-session ``*.stdout.log`` / ``*.stderr.log``
        files created by :func:`marrow_core.runner.run_agent`.
    max_age_days:
        Files whose mtime is older than this many days are removed.
        Set to 0 to skip age-based pruning.
    max_count:
        Maximum number of log files to keep (counted *after* age pruning).
        The oldest files are removed first.  Set to 0 to skip count-based pruning.

    Returns
    -------
    int
        Number of files deleted.
    """
    if not log_dir.is_dir():
        return 0

    deleted = 0
    now = time.time()
    cutoff = now - max_age_days * 86400 if max_age_days > 0 else None

    # Collect all log files with their mtimes, sorted oldest-first.
    files: list[tuple[float, Path]] = []
    for p in log_dir.iterdir():
        if not p.is_file():
            continue
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        files.append((mtime, p))

    files.sort()  # oldest first

    # Phase 1: age-based deletion.
    if cutoff is not None:
        survivors: list[tuple[float, Path]] = []
        for mtime, p in files:
            if mtime < cutoff:
                try:
                    p.unlink()
                    deleted += 1
                    logger.debug("pruned old log (age): {}", p.name)
                except OSError as exc:
                    logger.warning("could not delete {}: {}", p, exc)
            else:
                survivors.append((mtime, p))
        files = survivors

    # Phase 2: count-based deletion.
    if max_count > 0 and len(files) > max_count:
        excess = files[: len(files) - max_count]
        for _, p in excess:
            try:
                p.unlink()
                deleted += 1
                logger.debug("pruned old log (count): {}", p.name)
            except OSError as exc:
                logger.warning("could not delete {}: {}", p, exc)

    if deleted:
        logger.info("log pruner: deleted {} exec-log file(s) from {}", deleted, log_dir)

    return deleted
