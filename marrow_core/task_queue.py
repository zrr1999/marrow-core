"""Filesystem task queue helpers."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any


def create_task_file(task_dir: Path, title: str, body: str) -> Path:
    """Write a task markdown file into the queue directory."""
    task_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_ " else "" for c in title)[:50].strip()
    safe = safe.replace(" ", "-") or "task"
    path = task_dir / f"{ts}-{safe}.md"
    content = f"# {title}\n\n{body}\n" if body else f"# {title}\n"
    path.write_text(content, encoding="utf-8")
    return path


def list_tasks(task_dir: Path) -> list[dict[str, Any]]:
    """List task files in queue directory."""
    if not task_dir.is_dir():
        return []
    tasks: list[dict[str, Any]] = []
    for file_path in sorted(task_dir.glob("*.md")):
        first_line = file_path.read_text(encoding="utf-8").split("\n", 1)[0]
        title = first_line.lstrip("# ").strip() if first_line.startswith("#") else file_path.stem
        tasks.append(
            {
                "file": file_path.name,
                "title": title,
                "created": file_path.stat().st_ctime,
            }
        )
    return tasks
