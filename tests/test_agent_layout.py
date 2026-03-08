"""Tests for repository-level agent layout files."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from marrow_core.config import load_config

REPO_ROOT = Path(__file__).resolve().parents[1]


def _agent_file(name: str) -> Path:
    return REPO_ROOT / "agents" / f"{name}.md"


def _frontmatter_value(name: str, field: str) -> str:
    text = _agent_file(name).read_text(encoding="utf-8")
    match = re.search(rf"(?m)^{field}: (.+)$", text)
    assert match, f"{field} missing in {name}.md"
    return match.group(1).strip()


def test_autonomous_agents_in_config():
    root = load_config(REPO_ROOT / "marrow.toml")
    assert [agent.name for agent in root.agents] == ["scout", "conductor", "refit"]


def test_roles_toml_model_map():
    with (REPO_ROOT / "roles.toml").open("rb") as fh:
        config = tomllib.load(fh)

    assert config == {
        "targets": {
            "opencode": {
                "model_map": {
                    "strategic": "github-copilot/claude-opus-4.6",
                    "operational": "github-copilot/gpt-5.4",
                    "specialist": "github-copilot/gpt-5.4",
                    "routine": "github-copilot/gpt-5-mini",
                }
            }
        }
    }


def test_agent_modes_and_models_match_role_plan():
    assert _frontmatter_value("conductor", "mode") == "primary"
    assert _frontmatter_value("conductor", "model") == "github-copilot/gpt-5.4"
    assert _frontmatter_value("scout", "mode") == "all"
    assert _frontmatter_value("scout", "model") == "github-copilot/gpt-5-mini"
    assert _frontmatter_value("reviewer", "mode") == "subagent"
    assert _frontmatter_value("reviewer", "model") == "github-copilot/gpt-5.4"


def test_watchdog_agent_removed():
    assert not (REPO_ROOT / "agents" / "watchdog.md").exists()
