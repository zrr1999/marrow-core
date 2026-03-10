"""Tests for marrow_core.heartbeat."""

from __future__ import annotations

import re
import stat
import sys
from pathlib import Path

from marrow_core.config import AgentConfig
from marrow_core.heartbeat import HeartbeatState, _session_id, _tick, heartbeat
from marrow_core.prompting import build_prompt, gather_context
from marrow_core.runner import RunResult


def test_session_id_format():
    sid = _session_id(
        "scout",
    )
    assert sid.startswith("scout-")
    # Pattern: name-YYYYMMDD-HHMMSS-nnn
    assert re.match(r"^scout-\d{8}-\d{6}-\d{3}$", sid)


def test_session_id_sanitizes_name():
    sid = _session_id("my agent!")
    assert sid.startswith("myagent-")


def test_build_prompt_all_parts():
    prompt = build_prompt(
        base_prompt="Do work.",
        rules="Be safe.",
        context_blocks=["--- [queue] ---\nTask 1"],
    )
    assert "Be safe." in prompt
    assert "Do work." in prompt
    assert "Task 1" in prompt
    # Rules should come first
    assert prompt.index("Be safe.") < prompt.index("Do work.")


def test_build_prompt_empty():
    prompt = build_prompt("", "", [])
    assert prompt.strip() == ""


def test_build_prompt_rules_only():
    prompt = build_prompt("", "Rule 1", [])
    assert "Rule 1" in prompt


async def test_gather_context_runs_executable_scripts_in_order(tmp_path: Path):
    first = tmp_path / "a.py"
    first.write_text("#!/usr/bin/env python3\nprint('first')\n", encoding="utf-8")
    first.chmod(first.stat().st_mode | stat.S_IXUSR)

    second = tmp_path / "b.py"
    second.write_text("#!/usr/bin/env python3\nprint('second')\n", encoding="utf-8")
    second.chmod(second.stat().st_mode | stat.S_IXUSR)

    ignored = tmp_path / "c.txt"
    ignored.write_text("ignored", encoding="utf-8")

    blocks = await gather_context([str(tmp_path)])

    assert blocks == ["--- [a] ---\nfirst", "--- [b] ---\nsecond"]


async def test_tick_dry_run_prints_prompt(monkeypatch, tmp_path: Path, capsys) -> None:
    cfg = AgentConfig(
        name="scout",
        agent_command=sys.executable,
        workspace=str(tmp_path),
        context_dirs=[str(tmp_path / "context.d")],
    )

    async def fake_gather_context(
        context_dirs: list[str], timeout: int = 15, *, extra_env=None
    ) -> list[str]:
        assert extra_env["MARROW_AGENT_NAME"] == "scout"
        assert extra_env["MARROW_WORKSPACE"] == str(tmp_path)
        return ["--- [queue] ---\nTask 1"]

    monkeypatch.setattr("marrow_core.heartbeat.gather_context", fake_gather_context)

    ok = await _tick(cfg, str(tmp_path), "Be safe.", dry_run=True)

    captured = capsys.readouterr().out
    assert ok is True
    assert "DRY RUN [scout]" in captured
    assert "Be safe." in captured
    assert "Task 1" in captured


async def test_tick_runs_agent_and_prunes_logs(monkeypatch, tmp_path: Path) -> None:
    cfg = AgentConfig(
        name="scout",
        agent_command=f"{sys.executable} -V",
        workspace=str(tmp_path),
        context_dirs=[],
        log_retention_days=3,
        log_max_count=5,
    )
    run_agent_call: dict[str, object] = {}
    prune_call: dict[str, object] = {}

    async def fake_gather_context(
        context_dirs: list[str], timeout: int = 15, *, extra_env=None
    ) -> list[str]:
        assert extra_env["MARROW_AGENT_NAME"] == "scout"
        return []

    async def fake_run_agent(argv, *, message, timeout, cwd, log_dir, session_id):
        run_agent_call.update(
            {
                "argv": argv,
                "message": message,
                "timeout": timeout,
                "cwd": cwd,
                "log_dir": log_dir,
                "session_id": session_id,
            }
        )
        return RunResult(returncode=0, started=1.0, ended=2.0)

    def fake_prune_exec_logs(log_dir: Path, *, max_age_days: int, max_count: int) -> None:
        prune_call.update(
            {
                "log_dir": log_dir,
                "max_age_days": max_age_days,
                "max_count": max_count,
            }
        )

    monkeypatch.setattr("marrow_core.heartbeat.gather_context", fake_gather_context)
    monkeypatch.setattr("marrow_core.heartbeat.run_agent", fake_run_agent)
    monkeypatch.setattr("marrow_core.heartbeat.prune_exec_logs", fake_prune_exec_logs)

    ok = await _tick(cfg, str(tmp_path), "Rules")

    assert ok is True
    assert run_agent_call["argv"] == [sys.executable, "-V"]
    assert run_agent_call["cwd"] == str(tmp_path)
    assert run_agent_call["log_dir"] == tmp_path / "runtime" / "logs" / "exec"
    assert run_agent_call["timeout"] == cfg.heartbeat_timeout
    assert run_agent_call["session_id"]
    assert prune_call == {
        "log_dir": tmp_path / "runtime" / "logs" / "exec",
        "max_age_days": 3,
        "max_count": 5,
    }


async def test_heartbeat_once_updates_state_on_failure(monkeypatch, tmp_path: Path) -> None:
    cfg = AgentConfig(
        name="scout",
        agent_command=sys.executable,
        workspace=str(tmp_path),
        context_dirs=[],
    )
    state = HeartbeatState()

    monkeypatch.setattr("marrow_core.heartbeat.load_rules", lambda core_dir: "Rules")

    async def fake_tick(cfg, core_dir, rules, *, dry_run=False):
        return False

    monkeypatch.setattr("marrow_core.heartbeat._tick", fake_tick)

    await heartbeat(cfg, str(tmp_path), once=True, state=state)

    agent_state = state.agents["scout"]
    assert agent_state.tick_count == 1
    assert agent_state.running is False
    assert agent_state.last_error == "tick returned failure"
    assert agent_state.next_tick_at > 0


async def test_heartbeat_once_records_tick_exception(monkeypatch, tmp_path: Path) -> None:
    cfg = AgentConfig(
        name="scout",
        agent_command=sys.executable,
        workspace=str(tmp_path),
        context_dirs=[],
    )
    state = HeartbeatState()

    monkeypatch.setattr("marrow_core.heartbeat.load_rules", lambda core_dir: "Rules")

    async def fake_tick(cfg, core_dir, rules, *, dry_run=False):
        raise RuntimeError("boom")

    monkeypatch.setattr("marrow_core.heartbeat._tick", fake_tick)

    await heartbeat(cfg, str(tmp_path), once=True, state=state)

    agent_state = state.agents["scout"]
    assert agent_state.tick_count == 1
    assert agent_state.running is False
    assert agent_state.last_error == "tick raised exception"
