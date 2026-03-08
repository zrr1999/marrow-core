"""Tests for filesystem task queue helpers."""

from __future__ import annotations

from pathlib import Path

from marrow_core.task_queue import create_task_file, list_tasks


def test_create_task_file_writes_markdown(tmp_path: Path) -> None:
    path = create_task_file(tmp_path, "My Task", "Details")

    assert path.exists()
    assert path.suffix == ".md"
    assert path.read_text(encoding="utf-8") == "# My Task\n\nDetails\n"


def test_list_tasks_reads_titles(tmp_path: Path) -> None:
    create_task_file(tmp_path, "Alpha", "")
    create_task_file(tmp_path, "Beta", "body")

    tasks = list_tasks(tmp_path)

    assert len(tasks) == 2
    assert {task["title"] for task in tasks} == {"Alpha", "Beta"}
