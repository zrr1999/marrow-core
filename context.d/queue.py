#!/usr/bin/env python3
"""Queue context provider — reads task files and outputs them as prompt text.

This is a context.d script. It simply prints text to stdout.
marrow-core will inject the output into the agent's prompt.
"""

from __future__ import annotations

import os
from pathlib import Path

WORKSPACE = os.environ.get("HOME", "/Users/marrow")
QUEUE_DIR = Path(WORKSPACE) / "tasks" / "queue"
HANDOFF_DIR = Path(WORKSPACE) / "runtime" / "handoff"
MAX_TOTAL = 20_000
PER_FILE = 4_000


def main() -> None:
    if not QUEUE_DIR.is_dir():
        return

    files = sorted(p for p in QUEUE_DIR.iterdir() if p.is_file())
    if not files:
        return

    parts: list[str] = []
    total = 0
    for f in files:
        if total >= MAX_TOTAL:
            break
        try:
            body = f.read_bytes()[:PER_FILE].decode("utf-8", errors="replace").strip()
        except Exception:
            continue
        chunk = f"## {f.name}\n{body}\n"
        parts.append(chunk)
        total += len(chunk)

    if parts:
        print("Process the following task queue:\n")
        print("\n".join(parts))

    # Show delegation status
    s2a = HANDOFF_DIR / "scout-to-artisan"
    if s2a.is_dir():
        pending = sorted(s2a.iterdir())
        if pending:
            print(
                f"\nDelegated to artisan (pending): {', '.join(p.name for p in pending)}"
            )

    a2s = HANDOFF_DIR / "artisan-to-scout"
    if a2s.is_dir():
        msgs = sorted(a2s.iterdir())
        if msgs:
            print(f"\nMessages from artisan: {', '.join(p.name for p in msgs)}")


if __name__ == "__main__":
    main()
