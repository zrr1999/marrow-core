"""Structured logging — JSON for daemons, compact for humans."""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            entry["exc"] = str(record.exc_info[1])
        return json.dumps(entry, ensure_ascii=True)


class CompactFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        msg = record.getMessage()
        if record.exc_info and record.exc_info[1]:
            msg += f" ({record.exc_info[1]})"
        return f"[{ts}] {record.name}: {msg}"


def setup_logging(*, verbose: bool = False, json_logs: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JSONFormatter() if json_logs else CompactFormatter())
    root = logging.getLogger("marrow")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
