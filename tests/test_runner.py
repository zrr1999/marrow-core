"""Tests for marrow_core.runner."""

from __future__ import annotations

import sys
from pathlib import Path

from marrow_core.runner import RunResult, run_agent


def test_run_result_properties():
    r = RunResult(returncode=0, started=100.0, ended=100.5)
    assert r.duration == 0.5
    assert r.ok is True


def test_run_result_error():
    r = RunResult(error="boom")
    assert not r.ok


def test_run_result_timed_out():
    r = RunResult(returncode=0, timed_out=True)
    assert not r.ok


def test_run_result_nonzero():
    r = RunResult(returncode=1)
    assert not r.ok


async def test_run_agent_success(tmp_path: Path):
    result = await run_agent(
        [sys.executable, "-c", "print('hello')"],
        message="test",
        timeout=10,
        cwd=str(tmp_path),
        log_dir=tmp_path / "logs",
        session_id="test-001",
    )
    assert result.returncode == 0
    assert result.ok
    assert result.duration >= 0
    assert (tmp_path / "logs" / "test-001.stdout.log").exists()


async def test_run_agent_not_found(tmp_path: Path):
    result = await run_agent(
        ["/nonexistent/binary"],
        message="test",
        timeout=10,
        cwd=str(tmp_path),
        log_dir=tmp_path / "logs",
        session_id="test-002",
    )
    assert result.returncode is None
    assert "not found" in result.error
    assert not result.ok


async def test_run_agent_timeout(tmp_path: Path):
    result = await run_agent(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        message="test",
        timeout=1,
        cwd=str(tmp_path),
        log_dir=tmp_path / "logs",
        session_id="test-003",
    )
    assert result.timed_out
    assert not result.ok
