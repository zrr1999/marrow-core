#!/usr/bin/env python3
"""Explore context provider — fallback when no tasks are queued.

Only outputs if the queue is empty, so it doesn't conflict with queue.py.
"""

from __future__ import annotations

import os
from pathlib import Path

WORKSPACE = os.environ.get("HOME", "/Users/marrow")
QUEUE_DIR = Path(WORKSPACE) / "tasks" / "queue"


def main() -> None:
    # Only activate when queue is empty
    if QUEUE_DIR.is_dir():
        files = [p for p in QUEUE_DIR.iterdir() if p.is_file()]
        if files:
            return  # queue.py handles this

    print("No tasks queued. You may:")
    print("- Explore the workspace and check system health")
    print("- Review and organize runtime state")
    print("- Create or improve context scripts in context.d/")
    print("- Record observations to runtime/state/")


if __name__ == "__main__":
    main()
