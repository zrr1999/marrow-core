"""Tests for marrow_core.runner."""

from __future__ import annotations

import sys
from pathlib import Path

from marrow_core.runner import RunResult, _read_tail, run_agent, run_agent_http


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


def test_read_tail_normal(tmp_path: Path):
    f = tmp_path / "out.log"
    f.write_text("\n".join(str(i) for i in range(50)))
    tail = _read_tail(f, lines=5)
    assert tail == "45\n46\n47\n48\n49"


def test_read_tail_missing(tmp_path: Path):
    assert _read_tail(tmp_path / "nonexistent.log") == ""


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


async def test_run_agent_nonzero_writes_stderr_log(tmp_path: Path):
    """Non-zero exit creates a stderr log that can be inspected."""
    result = await run_agent(
        [sys.executable, "-c", "import sys; print('err msg', file=sys.stderr); sys.exit(1)"],
        message="test",
        timeout=10,
        cwd=str(tmp_path),
        log_dir=tmp_path / "logs",
        session_id="test-004",
    )
    assert result.returncode == 1
    assert not result.ok
    stderr_log = tmp_path / "logs" / "test-004.stderr.log"
    assert stderr_log.exists()
    assert "err msg" in stderr_log.read_text()


async def test_run_agent_http_connection_error(tmp_path: Path):
    """HTTP runner returns error result when server is not running."""
    result = await run_agent_http(
        "http://127.0.0.1:19999",  # nothing listening here
        message="test",
        timeout=5,
        log_dir=tmp_path / "logs",
        session_id="test-http-001",
    )
    assert not result.ok
    assert result.error
