from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_queue_script(workspace: Path) -> str:
    env = os.environ.copy()
    env["MARROW_WORKSPACE"] = str(workspace)
    result = subprocess.run(
        [sys.executable, str(ROOT / "context.d" / "queue.py")],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return result.stdout


def test_queue_outputs_full_paths_without_contents(tmp_path: Path) -> None:
    queue_dir = tmp_path / "tasks" / "queue"
    queue_dir.mkdir(parents=True)

    task1 = queue_dir / "task1.md"
    task2 = queue_dir / "task2.md"
    task1.write_text("first task body")
    task2.write_text("second task body")

    output = run_queue_script(tmp_path)

    # Should list full paths
    assert str(task1) in output
    assert str(task2) in output

    # Should not include file contents
    assert "first task body" not in output
    assert "second task body" not in output


def test_queue_context_stays_queue_focused(tmp_path: Path) -> None:
    queue_dir = tmp_path / "tasks" / "queue"
    queue_dir.mkdir(parents=True)
    (queue_dir / "task.md").write_text("queued")

    output = run_queue_script(tmp_path)

    assert "Task queue lives in tasks/queue/" in output
    assert "Delegated to delivery-steward" not in output
    assert "Messages from delivery-steward" not in output
