#!/usr/bin/env python3
"""Queue context provider — reads task files and outputs them as prompt text.

This is a context.d script. It simply prints text to stdout.
marrow-core will inject the output into the agent's prompt.
"""

from __future__ import annotations

import os
from pathlib import Path

WORKSPACE = Path(os.environ.get("MARROW_WORKSPACE") or os.environ.get("HOME") or "/Users/marrow")
QUEUE_DIR = WORKSPACE / "tasks" / "queue"


def main() -> None:
    if not QUEUE_DIR.is_dir():
        return

    files = sorted(p for p in QUEUE_DIR.iterdir() if p.is_file())
    if not files:
        return

    print("Task queue lives in tasks/queue/. Completed tasks go to tasks/done/.")
    print("Process the following task queue files (full paths):\n")

    for f in files:
        print(f.resolve())


if __name__ == "__main__":
    main()
