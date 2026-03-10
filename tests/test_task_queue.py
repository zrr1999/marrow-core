"""Tests for filesystem task queue helpers."""

from __future__ import annotations

from pathlib import Path

from marrow_core.task_queue import create_task_file, list_tasks


def test_create_task_file_writes_markdown(tmp_path: Path) -> None:
    path = create_task_file(tmp_path, "My Task", "Details")

    assert path.exists()
    assert path.suffix == ".md"
    assert path.read_text(encoding="utf-8") == "# My Task\n\nDetails\n"


def test_create_task_file_writes_frontmatter_when_metadata_present(tmp_path: Path) -> None:
    path = create_task_file(
        tmp_path,
        "My Task",
        "Details",
        metadata={"owner": "curator", "assignee": "conductor", "acceptance": "light"},
    )

    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "owner: curator" in text
    assert "assignee: conductor" in text
    assert "# My Task" in text


def test_list_tasks_reads_titles(tmp_path: Path) -> None:
    create_task_file(tmp_path, "Alpha", "")
    create_task_file(
        tmp_path,
        "Beta",
        "body",
        metadata={"owner": "curator", "assignee": "conductor", "status": "queued"},
    )

    tasks = list_tasks(tmp_path)

    assert len(tasks) == 2
    assert {task["title"] for task in tasks} == {"Alpha", "Beta"}
    beta = next(task for task in tasks if task["title"] == "Beta")
    assert beta["owner"] == "curator"
    assert beta["assignee"] == "conductor"
    assert beta["status"] == "queued"


def test_list_tasks_can_filter_by_assignee(tmp_path: Path) -> None:
    create_task_file(tmp_path, "Alpha", "", metadata={"assignee": "curator"})
    create_task_file(tmp_path, "Beta", "body", metadata={"assignee": "conductor"})

    tasks = list_tasks(tmp_path, assignee="conductor")

    assert len(tasks) == 1
    assert tasks[0]["title"] == "Beta"
