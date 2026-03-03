#!/usr/bin/env python3
"""Explore context provider — proactive self-improvement when no tasks are queued.

Only outputs if the queue is empty, so it doesn't conflict with queue.py.
Provides ambitious, concrete directives to keep the agent productive.
"""

from __future__ import annotations

import os
from pathlib import Path

WORKSPACE = Path(os.environ.get("MARROW_WORKSPACE") or os.environ.get("HOME") or "/Users/marrow")
QUEUE_DIR = WORKSPACE / "tasks" / "queue"


def main() -> None:
    # Only activate when queue is empty
    if QUEUE_DIR.is_dir():
        files = [p for p in QUEUE_DIR.iterdir() if p.is_file()]
        if files:
            return  # queue.py handles this

    print("No tasks queued. You are a relentless worker — find high-value work now:")
    print()
    print("Improve yourself:")
    print("- Review runtime/state/learnings.md and identify patterns or gaps")
    print("- Audit context.d/ scripts — can they provide richer, more useful context?")
    print("- Create or refine custom agents in .opencode/agents/custom-*.md")
    print()
    print("Improve your environment:")
    print("- Scan runtime/logs/exec/ for errors or anomalies worth investigating")
    print("- Check runtime/checkpoints/ for incomplete or stalled work to resume")
    print("- Review tasks/done/ for follow-up opportunities or quality improvements")
    print()
    print("Learn and explore:")
    print("- Explore the workspace for files or patterns you haven't examined")
    print("- Research tools or techniques that could improve your workflows")
    print("- Write a task card to tasks/queue/ for any improvement idea worth pursuing")


if __name__ == "__main__":
    main()
