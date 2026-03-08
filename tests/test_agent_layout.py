"""Tests for repository-level agent layout files."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from marrow_core.config import load_config
from marrow_core.contracts import AGENT_LAYERS, AUTONOMOUS_AGENTS, BASE_AGENT_FILES, WORKSPACE_DIRS

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
    assert [agent.name for agent in root.agents] == list(AUTONOMOUS_AGENTS)


def test_base_agent_files_match_contract():
    actual = sorted(path.stem for path in (REPO_ROOT / "agents").glob("*.md"))
    assert actual == sorted(BASE_AGENT_FILES)


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


def test_agent_layers_match_role_plan():
    assert AGENT_LAYERS == {
        "scout": "routine",
        "conductor": "operational",
        "refit": "strategic",
        "reviewer": "specialist",
    }


def test_watchdog_agent_removed():
    assert not (REPO_ROOT / "agents" / "watchdog.md").exists()


def test_lib_shell_workspace_dirs_match_contract():
    text = (REPO_ROOT / "lib.sh").read_text(encoding="utf-8")
    match = re.search(r"WORKSPACE_DIRS=\((.*?)\)", text, re.S)
    assert match, "WORKSPACE_DIRS missing in lib.sh"
    actual = re.findall(r"^\s+([^\s#][^\n]*)$", match.group(1), re.M)
    assert [entry.strip() for entry in actual] == list(WORKSPACE_DIRS)


def test_rules_prompt_uses_canonical_agent_names():
    text = (REPO_ROOT / "prompts" / "rules.md").read_text(encoding="utf-8")
    assert "artisan" not in text
    assert "watchdog" not in text
    assert "conductor" in text
    assert "refit" in text


def test_agent_docs_use_canonical_dispatch_names():
    for path in (REPO_ROOT / "agents").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "Artisan" not in text
        assert "artisan" not in text
        assert "Watchdog" not in text
        assert "watchdog" not in text


def test_readme_documents_ipc_commands_and_handoffs():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "marrow status" in text
    assert "marrow task add" in text
    assert "marrow task list" in text
    assert "marrow scaffold" in text
    assert "marrow install-service" in text
    assert "runtime/handoff/scout-to-conductor/" in text
    assert "runtime/handoff/conductor-to-scout/" in text
    assert "runtime/handoff/scout-to-human/" in text


def test_service_files_exist_for_both_platforms():
    assert (REPO_ROOT / "com.marrow.heart.plist").exists()
    assert (REPO_ROOT / "com.marrow.heart.sync.plist").exists()
    assert (REPO_ROOT / "marrow-heart.service").exists()
    assert (REPO_ROOT / "marrow-heart-sync.service").exists()
    assert (REPO_ROOT / "marrow-heart-sync.timer").exists()
