"""Tests for repository-level role layout files."""

from __future__ import annotations

import tomllib
from pathlib import Path

from marrow_core.config import load_config
from marrow_core.contracts import (
    AUTONOMOUS_AGENTS,
    EXPERTS,
    LEADERS,
    ROLE_MODEL_TIERS,
    ROLE_PATHS,
    STEWARDS,
    SYNCED_ROLE_FILES,
    WORKSPACE_DIRS,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _role_file(name: str) -> Path:
    return REPO_ROOT / ROLE_PATHS[name]


def test_scheduled_mains_in_config():
    root = load_config(REPO_ROOT / "marrow.toml")
    assert [agent.name for agent in root.agents] == list(AUTONOMOUS_AGENTS)


def test_roles_toml_model_map():
    with (REPO_ROOT / "roles.toml").open("rb") as fh:
        config = tomllib.load(fh)

    assert config["project"]["roles_dir"] == "roles"
    assert config["targets"]["opencode"]["output_layout"] == "preserve"
    assert config["targets"]["opencode"]["model_map"] == {
        "high": "github-copilot/claude-opus-4.6",
        "medium": "github-copilot/gpt-5.4",
        "low": "github-copilot/gpt-5-mini",
    }


def test_role_inventory_matches_contract():
    actual = sorted(
        str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        for path in (REPO_ROOT / "roles").rglob("*.md")
    )
    assert actual == sorted(ROLE_PATHS.values())
    role_dirs = sorted(path.name for path in (REPO_ROOT / "roles").iterdir() if path.is_dir())
    assert role_dirs == ["experts", "leaders", "stewards"]


def test_role_model_tiers_match_expected_inventory():
    assert ROLE_MODEL_TIERS["curator"] == "high"
    assert ROLE_MODEL_TIERS["conductor"] == "medium"
    assert ROLE_MODEL_TIERS["repo-steward"] == "medium"
    assert ROLE_MODEL_TIERS["coder"] == "low"


def test_role_inventory_groups_are_stable():
    assert tuple(AUTONOMOUS_AGENTS) == ("curator",)
    assert tuple(STEWARDS) == (
        "conductor",
        "repo-steward",
        "innovation-steward",
    )
    assert tuple(LEADERS) == (
        "refactor-lead",
        "prototype-lead",
        "review-lead",
        "ops-lead",
    )
    assert tuple(EXPERTS) == (
        "analyst",
        "researcher",
        "coder",
        "tester",
        "writer",
        "git-ops",
        "filer",
    )


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


def test_docs_use_semantic_role_directories_and_avoid_numbered_layers():
    docs = [
        (REPO_ROOT / "README.md").read_text(encoding="utf-8"),
        (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8"),
        (REPO_ROOT / "prompts" / "rules.md").read_text(encoding="utf-8"),
    ]
    merged = "\n".join(docs)

    for token in ("roles/experts/", "roles/leaders/", "roles/stewards/", "`curator`"):
        assert token in merged


def test_readme_documents_commands_and_self_check():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "marrow scaffold" in text
    assert "marrow install-service" in text
    assert "marrow wake" in text
    assert "[self_check]" in text
    assert "doctor-style validation" in text


def test_service_files_exist_for_both_platforms():
    assert (REPO_ROOT / "com.marrow.heart.plist").exists()
    assert (REPO_ROOT / "marrow-heart.service").exists()


def test_docs_describe_unified_sync_model() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    agents_doc = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "marrow sync-once" in readme
    assert "CLI-managed periodic sync" in readme
    assert "one long-running service" in readme
    assert "sync-once" in agents_doc
    assert "self-check can wake `curator` early" in agents_doc
    assert "com.marrow.heart.sync.plist" not in agents_doc
    assert "marrow-heart-sync.timer" not in agents_doc


def test_role_files_use_agent_caster_friendly_frontmatter_only():
    allowed_fields = {
        "name",
        "description",
        "role",
        "model",
        "skills",
        "capabilities",
        "prompt_file",
    }
    for role in SYNCED_ROLE_FILES:
        text = _role_file(role).read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1].strip().splitlines()
        keys = {
            line.split(":", 1)[0].strip()
            for line in frontmatter
            if ":" in line and not line.startswith("  ")
        }
        assert keys <= allowed_fields
