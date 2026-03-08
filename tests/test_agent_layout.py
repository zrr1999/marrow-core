"""Tests for repository-level role layout files."""

from __future__ import annotations

import tomllib
from pathlib import Path

from marrow_core.config import load_config
from marrow_core.contracts import (
    ALLOWED_CHILDREN,
    AUTONOMOUS_AGENTS,
    EXPERT_LEADS,
    LEAF_WORKERS,
    MAX_DELEGATION_HOPS,
    ROLE_CLASSES,
    ROLE_LEVELS,
    ROLE_MODEL_TIERS,
    ROLE_PATHS,
    SYNCED_ROLE_FILES,
    WORKSPACE_DIRS,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _role_file(name: str) -> Path:
    return REPO_ROOT / ROLE_PATHS[name]


def test_scheduled_mains_in_config():
    root = load_config(REPO_ROOT / "marrow.toml")
    assert [agent.name for agent in root.agents] == list(AUTONOMOUS_AGENTS)


def test_roles_toml_model_map_and_hierarchy():
    with (REPO_ROOT / "roles.toml").open("rb") as fh:
        config = tomllib.load(fh)

    assert config["targets"]["opencode"]["model_map"] == {
        "strategic": "github-copilot/claude-opus-4.6",
        "operational": "github-copilot/gpt-5.4",
        "specialist": "github-copilot/gpt-5.4",
        "routine": "github-copilot/gpt-5-mini",
    }
    assert config["hierarchy"]["max_delegate_depth"] == MAX_DELEGATION_HOPS
    assert tuple(config["hierarchy"]["scheduled_mains"]) == AUTONOMOUS_AGENTS
    assert tuple(config["hierarchy"]["expert_leads"]) == EXPERT_LEADS
    assert tuple(config["hierarchy"]["leaf_workers"]) == LEAF_WORKERS


def test_role_inventory_matches_contract():
    actual = sorted(
        str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        for path in (REPO_ROOT / "roles").rglob("*.md")
    )
    assert actual == sorted(ROLE_PATHS.values())


def test_role_contract_maps_match_expected_hierarchy():
    assert ROLE_LEVELS == {
        "scout": "l1",
        "conductor": "l1",
        "refit": "l1",
        "refactor-lead": "l2",
        "prototype-lead": "l2",
        "review-lead": "l2",
        "ops-lead": "l2",
        "analyst": "l3",
        "researcher": "l3",
        "coder": "l3",
        "tester": "l3",
        "writer": "l3",
        "git-ops": "l3",
        "filer": "l3",
    }
    assert ROLE_CLASSES["conductor"] == "main"
    assert ROLE_CLASSES["prototype-lead"] == "lead"
    assert ROLE_CLASSES["coder"] == "leaf"
    assert ROLE_MODEL_TIERS["scout"] == "routine"
    assert ROLE_MODEL_TIERS["conductor"] == "operational"
    assert ROLE_MODEL_TIERS["refit"] == "strategic"
    assert ROLE_MODEL_TIERS["coder"] == "specialist"


def test_l2_roles_delegate_only_to_l3():
    for role in EXPERT_LEADS:
        children = ALLOWED_CHILDREN[role]
        assert children
        assert all(child in LEAF_WORKERS for child in children)


def test_l3_roles_have_no_children():
    for role in LEAF_WORKERS:
        assert ALLOWED_CHILDREN[role] == ()


def test_lib_shell_workspace_dirs_match_contract():
    text = (REPO_ROOT / "lib.sh").read_text(encoding="utf-8")
    actual = []
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "WORKSPACE_DIRS=(":
            inside = True
            continue
        if inside and stripped == ")":
            break
        if inside and stripped:
            actual.append(stripped)
    assert actual == list(WORKSPACE_DIRS)


def test_docs_describe_rules_roles_context_layers():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    agents_doc = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    rules = (REPO_ROOT / "prompts" / "rules.md").read_text(encoding="utf-8")

    assert "`rules` -> stable global policy" in readme
    assert "`roles` -> per-agent identity" in readme
    assert "`context providers` -> current queue/state/environment facts" in readme
    assert "`prompts/rules.md` -> stable global policy" in agents_doc
    assert "`roles/` -> role identity and delegation boundaries" in agents_doc
    assert "`context.d/` -> dynamic facts only" in agents_doc
    assert "Do not treat `context.d/` as a place for long-lived policy" in rules


def test_docs_use_level_folders_not_level_encoded_names():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    agents_doc = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    rules = (REPO_ROOT / "prompts" / "rules.md").read_text(encoding="utf-8")

    for token in ("roles/l1/", "roles/l2/", "roles/l3/", "prototype-lead", "coder"):
        assert token in readme or token in agents_doc or token in rules

    for token in ("l1-", "l2-", "l3-"):
        assert token not in readme
        assert token not in rules


def test_readme_documents_new_handoffs_and_commands():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "marrow scaffold" in text
    assert "marrow install-service" in text
    assert "runtime/handoff/scout-to-conductor/" in text
    assert "runtime/handoff/conductor-to-scout/" in text
    assert "runtime/handoff/scout-to-human/" in text


def test_docs_include_agent_caster_priority_needs_note():
    text = (REPO_ROOT / "docs" / "agent-caster-priority-needs.md").read_text(encoding="utf-8")
    assert "agent-caster#18" in text
    assert "agent-caster#19" in text
    assert "agent-caster#20" in text
    assert "https://github.com/zrr1999/agent-caster/issues/18" in text
    assert "https://github.com/zrr1999/agent-caster/issues/19" in text
    assert "https://github.com/zrr1999/agent-caster/issues/20" in text


def test_service_files_exist_for_both_platforms():
    assert (REPO_ROOT / "com.marrow.heart.plist").exists()
    assert (REPO_ROOT / "com.marrow.heart.sync.plist").exists()
    assert (REPO_ROOT / "marrow-heart.service").exists()
    assert (REPO_ROOT / "marrow-heart-sync.service").exists()
    assert (REPO_ROOT / "marrow-heart-sync.timer").exists()


def test_role_files_use_agent_caster_friendly_frontmatter_only():
    allowed_fields = {"description", "mode", "model", "tools"}
    for role in SYNCED_ROLE_FILES:
        text = _role_file(role).read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1].strip().splitlines()
        keys = {
            line.split(":", 1)[0].strip()
            for line in frontmatter
            if ":" in line and not line.startswith("  ")
        }
        assert keys <= allowed_fields
