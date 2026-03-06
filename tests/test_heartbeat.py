"""Tests for marrow_core.heartbeat."""

from __future__ import annotations

import re

from marrow_core.config import AgentConfig
from marrow_core.heartbeat import _build_prompt, _hierarchy_rule, _session_id


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
    prompt = _build_prompt(
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
    prompt = _build_prompt("", "", [])
    assert prompt.strip() == ""


def test_build_prompt_rules_only():
    prompt = _build_prompt("", "Rule 1", [])
    assert "Rule 1" in prompt


def _make_agent(name: str, level: int) -> AgentConfig:
    return AgentConfig(name=name, level=level, agent_command="cmd", workspace="/tmp")


def test_hierarchy_rule_lists_higher_agents():
    agents = [
        _make_agent("watchdog", 1),
        _make_agent("scout", 2),
        _make_agent("artisan", 4),
        _make_agent("refit", 5),
    ]
    rule = _hierarchy_rule(agents[1], agents)  # scout (level 2)
    assert "artisan" in rule
    assert "refit" in rule
    assert "watchdog" not in rule
    # scout appears only as the current agent identifier, never as a forbidden target
    assert "(artisan, refit)" in rule
    # Remove the first (and only expected) occurrence of 'scout' as the current agent name,
    # then verify it's not listed as a forbidden target.
    assert "scout" not in rule.replace("scout", "", 1)
    assert "MUST NOT" in rule


def test_hierarchy_rule_highest_agent_empty():
    agents = [
        _make_agent("artisan", 4),
        _make_agent("refit", 5),
    ]
    rule = _hierarchy_rule(agents[1], agents)  # refit (level 5) — no higher agents
    assert rule == ""


def test_hierarchy_rule_level_zero_returns_empty():
    agents = [
        _make_agent("scout", 0),
        _make_agent("artisan", 0),
    ]
    rule = _hierarchy_rule(agents[0], agents)
    assert rule == ""


def test_hierarchy_rule_single_agent_returns_empty():
    agents = [_make_agent("scout", 2)]
    rule = _hierarchy_rule(agents[0], agents)
    assert rule == ""
