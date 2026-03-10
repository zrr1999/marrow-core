"""Filesystem task queue helpers."""

from __future__ import annotations

import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

TASK_METADATA_KEYS = (
    "status",
    "task_type",
    "owner",
    "assignee",
    "acceptance",
    "delegated_by",
)


def _clean_scalar(value: Any) -> str:
    return " ".join(str(value).strip().split())


def _normalize_metadata(metadata: Mapping[str, Any] | None) -> dict[str, str]:
    normalized: dict[str, str] = {}
    if not metadata:
        return normalized
    for key in TASK_METADATA_KEYS:
        value = metadata.get(key)
        if value is None:
            continue
        text = _clean_scalar(value)
        if text:
            normalized[key] = text
    return normalized


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text

    raw_frontmatter = text[4:end].splitlines()
    body = text[end + len("\n---\n") :].lstrip("\n")
    metadata: dict[str, str] = {}
    for line in raw_frontmatter:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key not in TASK_METADATA_KEYS:
            continue
        text_value = _clean_scalar(value)
        if text_value:
            metadata[key] = text_value
    return metadata, body


def _extract_title_and_body(text: str, fallback_title: str) -> tuple[str, str]:
    lines = text.splitlines()
    if not lines:
        return fallback_title, ""
    first = lines[0]
    title = first.lstrip("# ").strip() if first.startswith("#") else fallback_title
    body = "\n".join(lines[1:]).strip()
    return title, body


def read_task_file(file_path: Path) -> dict[str, Any]:
    """Read one task file and return normalized task data."""
    raw = file_path.read_text(encoding="utf-8")
    metadata, markdown = _split_frontmatter(raw)
    title, body = _extract_title_and_body(markdown, file_path.stem)
    summary = ""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            summary = stripped
            break
    task = {
        "file": file_path.name,
        "title": title,
        "created": file_path.stat().st_ctime,
        "summary": summary,
    }
    task.update(metadata)
    return task


def create_task_file(
    task_dir: Path,
    title: str,
    body: str,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> Path:
    """Write a task markdown file into the queue directory."""
    task_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_ " else "" for c in title)[:50].strip()
    safe = safe.replace(" ", "-") or "task"
    path = task_dir / f"{ts}-{safe}.md"
    task_metadata = _normalize_metadata(metadata)
    frontmatter = ""
    if task_metadata:
        lines = ["---"]
        for key in TASK_METADATA_KEYS:
            value = task_metadata.get(key)
            if value:
                lines.append(f"{key}: {value}")
        lines.append("---")
        frontmatter = "\n".join(lines) + "\n\n"
    content = frontmatter
    content += f"# {title}\n\n{body}\n" if body else f"# {title}\n"
    path.write_text(content, encoding="utf-8")
    return path


def list_tasks(
    task_dir: Path,
    *,
    assignee: str = "",
    owner: str = "",
    status: str = "",
) -> list[dict[str, Any]]:
    """List task files in queue directory."""
    if not task_dir.is_dir():
        return []
    tasks: list[dict[str, Any]] = []
    for file_path in sorted(task_dir.glob("*.md")):
        task = read_task_file(file_path)
        if assignee and task.get("assignee", "") != assignee:
            continue
        if owner and task.get("owner", "") != owner:
            continue
        if status and task.get("status", "") != status:
            continue
        tasks.append(task)
    return tasks
