"""Logging setup — loguru with JSON or compact human output."""

from __future__ import annotations

import sys

from loguru import logger


def setup_logging(*, verbose: bool = False, json_logs: bool = False) -> None:
    """Configure loguru for the marrow scheduler.

    - json_logs: emit newline-delimited JSON records (for daemons / log aggregators)
    - verbose: set level to DEBUG, otherwise INFO
    """
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    if json_logs:
        logger.add(
            sys.stderr,
            level=level,
            serialize=True,  # built-in JSON serialisation
        )
    else:
        logger.add(
            sys.stderr,
            level=level,
            format="[{time:HH:mm:ss}] {name}: {message}",
            colorize=True,
        )


__all__ = ["logger", "setup_logging"]
