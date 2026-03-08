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


def test_queue_reports_conductor_handoffs(tmp_path: Path) -> None:
    queue_dir = tmp_path / "tasks" / "queue"
    queue_dir.mkdir(parents=True)
    (queue_dir / "task.md").write_text("queued")

    scout_to_conductor = tmp_path / "runtime" / "handoff" / "scout-to-conductor"
    scout_to_conductor.mkdir(parents=True)
    (scout_to_conductor / "handoff-1.md").write_text("pending")

    conductor_to_scout = tmp_path / "runtime" / "handoff" / "conductor-to-scout"
    conductor_to_scout.mkdir(parents=True)
    (conductor_to_scout / "followup-1.md").write_text("message")

    output = run_queue_script(tmp_path)

    assert "Delegated to conductor (pending): handoff-1.md" in output
    assert "Messages from conductor: followup-1.md" in output
    assert "artisan" not in output
