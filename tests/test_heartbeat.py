"""Tests for marrow_core.heartbeat."""

from __future__ import annotations

import re

from marrow_core.heartbeat import _build_prompt, _session_id


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


