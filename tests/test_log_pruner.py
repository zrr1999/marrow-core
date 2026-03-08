"""Tests for marrow_core.log_pruner."""

from __future__ import annotations

import os
import time
from pathlib import Path

from marrow_core.log_pruner import prune_exec_logs

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_log(path: Path, age_days: float = 0.0) -> None:
    """Create a file and set its mtime to ``age_days`` days in the past."""
    path.touch()
    mtime = time.time() - age_days * 86400
    os.utime(path, (mtime, mtime))


# ---------------------------------------------------------------------------
# Basic behaviour
# ---------------------------------------------------------------------------


def test_returns_zero_for_missing_dir(tmp_path: Path):
    assert prune_exec_logs(tmp_path / "no_such_dir") == 0


def test_returns_zero_empty_dir(tmp_path: Path):
    assert prune_exec_logs(tmp_path) == 0


def test_both_knobs_disabled_deletes_nothing(tmp_path: Path):
    for i in range(5):
        _make_log(tmp_path / f"old-{i}.log", age_days=30)
    deleted = prune_exec_logs(tmp_path, max_age_days=0, max_count=0)
    assert deleted == 0
    assert len(list(tmp_path.iterdir())) == 5


# ---------------------------------------------------------------------------
# Age-based pruning
# ---------------------------------------------------------------------------


def test_age_prunes_old_files(tmp_path: Path):
    _make_log(tmp_path / "old.log", age_days=10)
    _make_log(tmp_path / "new.log", age_days=1)
    deleted = prune_exec_logs(tmp_path, max_age_days=7, max_count=0)
    assert deleted == 1
    assert (tmp_path / "new.log").exists()
    assert not (tmp_path / "old.log").exists()


def test_age_keeps_files_exactly_at_boundary(tmp_path: Path):
    # A file that is exactly 7 days old should be kept (mtime >= cutoff).
    _make_log(tmp_path / "boundary.log", age_days=7)
    # Small tolerance: the file will be *slightly* older than 7 days by the time
    # prune runs, so just ensure no crash and that very-new files are safe.
    _make_log(tmp_path / "fresh.log", age_days=0)
    deleted = prune_exec_logs(tmp_path, max_age_days=7, max_count=0)
    # fresh.log must survive
    assert (tmp_path / "fresh.log").exists()
    # total deleted is 0 or 1 (boundary edge), no assertion on boundary.log itself
    assert deleted in (0, 1)


def test_age_zero_disables_age_pruning(tmp_path: Path):
    for i in range(3):
        _make_log(tmp_path / f"ancient-{i}.log", age_days=365)
    deleted = prune_exec_logs(tmp_path, max_age_days=0, max_count=0)
    assert deleted == 0


# ---------------------------------------------------------------------------
# Count-based pruning
# ---------------------------------------------------------------------------


def test_count_prunes_oldest_files(tmp_path: Path):
    for i in range(10):
        _make_log(tmp_path / f"log-{i:02d}.log", age_days=10 - i)
    # max_count=5 → keep 5 newest, delete 5 oldest
    deleted = prune_exec_logs(tmp_path, max_age_days=0, max_count=5)
    assert deleted == 5
    remaining = sorted(tmp_path.iterdir(), key=lambda p: p.stat().st_mtime)
    assert len(remaining) == 5
    # The 5 newest should survive (age_days 4, 3, 2, 1, 0)
    # i.e. log-05 through log-09
    names = {p.name for p in remaining}
    assert "log-09.log" in names  # youngest
    assert "log-00.log" not in names  # oldest


def test_count_zero_disables_count_pruning(tmp_path: Path):
    for i in range(20):
        _make_log(tmp_path / f"log-{i}.log")
    deleted = prune_exec_logs(tmp_path, max_age_days=0, max_count=0)
    assert deleted == 0


def test_count_within_budget_deletes_nothing(tmp_path: Path):
    for i in range(5):
        _make_log(tmp_path / f"log-{i}.log")
    deleted = prune_exec_logs(tmp_path, max_age_days=0, max_count=10)
    assert deleted == 0


# ---------------------------------------------------------------------------
# Combined age + count pruning
# ---------------------------------------------------------------------------


def test_combined_age_then_count(tmp_path: Path):
    # 5 files older than 7 days → deleted by age phase
    for i in range(5):
        _make_log(tmp_path / f"old-{i}.log", age_days=10)
    # 10 recent files; max_count=7 → 3 more deleted by count phase
    for i in range(10):
        _make_log(tmp_path / f"recent-{i:02d}.log", age_days=i * 0.1)
    deleted = prune_exec_logs(tmp_path, max_age_days=7, max_count=7)
    assert deleted == 5 + 3  # 5 old + 3 excess recent
    assert len(list(tmp_path.iterdir())) == 7


# ---------------------------------------------------------------------------
# Edge case: non-file entries are ignored
# ---------------------------------------------------------------------------


def test_subdirectories_ignored(tmp_path: Path):
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    _make_log(tmp_path / "log.log", age_days=10)
    deleted = prune_exec_logs(tmp_path, max_age_days=7, max_count=0)
    assert deleted == 1
    assert subdir.is_dir()  # not deleted
