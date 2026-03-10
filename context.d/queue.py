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
AGENT_NAME = os.environ.get("MARROW_AGENT_NAME", "").strip()
ROLE_LAYER = os.environ.get("MARROW_ROLE_LAYER", "").strip()


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    metadata: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = " ".join(value.strip().split())
    body = text[end + len("\n---\n") :].lstrip("\n")
    return metadata, body


def _read_task(path: Path) -> dict[str, str]:
    raw = path.read_text(encoding="utf-8")
    metadata, markdown = _split_frontmatter(raw)
    lines = markdown.splitlines()
    title = path.stem
    if lines and lines[0].startswith("#"):
        title = lines[0].lstrip("# ").strip()
        body_lines = lines[1:]
    else:
        body_lines = lines
    summary = ""
    for line in body_lines:
        stripped = line.strip()
        if stripped:
            summary = stripped
            break
    return {
        "file": path.name,
        "title": title,
        "summary": summary,
        "owner": metadata.get("owner", ""),
        "assignee": metadata.get("assignee", ""),
        "acceptance": metadata.get("acceptance", ""),
        "status": metadata.get("status", ""),
        "task_type": metadata.get("task_type", ""),
    }


def _print_section(title: str, tasks: list[dict[str, str]]) -> None:
    if not tasks:
        return
    print(f"{title}:")
    for task in tasks:
        line = (
            f"- {task['file']} [{task.get('status') or '?'} / {task.get('task_type') or '?'}] "
            f"{task['title']} | owner={task.get('owner') or '?'} "
            f"| assignee={task.get('assignee') or '?'} | acceptance={task.get('acceptance') or '?'}"
        )
        print(line)
        if task.get("summary"):
            print(f"  summary: {task['summary']}")
    print()


def main() -> None:
    if not QUEUE_DIR.is_dir():
        return

    tasks = [_read_task(path) for path in sorted(QUEUE_DIR.iterdir()) if path.is_file()]
    if not tasks:
        return

    print(f"Task queue summary: {len(tasks)} open task(s) in {QUEUE_DIR}.")
    if AGENT_NAME:
        print(f"Focus view for {AGENT_NAME} ({ROLE_LAYER or 'unknown'} layer).")
    print()

    assigned = [task for task in tasks if AGENT_NAME and task.get("assignee") == AGENT_NAME]
    owned = [
        task
        for task in tasks
        if AGENT_NAME and task.get("owner") == AGENT_NAME and task.get("assignee") != AGENT_NAME
    ]

    if ROLE_LAYER == "top-level":
        curator_assigned = assigned or [
            task for task in tasks if task.get("assignee") == "curator"
        ]
        steward_backlog = [
            task
            for task in tasks
            if task.get("assignee") in {"conductor", "repo-steward", "innovation-steward"}
        ]
        _print_section("Assigned to you", curator_assigned)
        _print_section("Steward backlog", steward_backlog)
    elif ROLE_LAYER in {"steward", "leader"}:
        _print_section("Assigned to you", assigned)
        _print_section("Child work you still own", owned)
    elif ROLE_LAYER == "expert":
        _print_section("Assigned to you", assigned)
    else:
        _print_section("Visible tasks", tasks)

    lane_counts: dict[str, int] = {}
    for task in tasks:
        assignee = task.get("assignee") or "(unassigned)"
        lane_counts[assignee] = lane_counts.get(assignee, 0) + 1

    print("Lane counts:")
    for assignee in sorted(lane_counts):
        print(f"- {assignee}: {lane_counts[assignee]}")


if __name__ == "__main__":
    main()
