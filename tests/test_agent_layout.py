"""Tests for repository-level role layout files."""

from __future__ import annotations

import tomllib
from pathlib import Path

from marrow_core.config import load_config
from marrow_core.contracts import (
    AUTONOMOUS_AGENTS,
    DIRECTORS,
    LEADERS,
    ROLE_MODEL_TIERS,
    ROLE_PATHS,
    SPECIALISTS,
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
        "high": "github-copilot/gpt-5.4",
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
    assert role_dirs == ["directors", "leaders", "specialists"]


def test_role_model_tiers_match_expected_inventory():
    assert ROLE_MODEL_TIERS["orchestrator"] == "high"
    assert ROLE_MODEL_TIERS["craft"] == "medium"
    assert ROLE_MODEL_TIERS["forge"] == "medium"
    assert ROLE_MODEL_TIERS["mind"] == "medium"
    assert ROLE_MODEL_TIERS["sentinel"] == "medium"
    assert ROLE_MODEL_TIERS["evolver"] == "medium"
    assert ROLE_MODEL_TIERS["reviewer"] == "medium"
    assert ROLE_MODEL_TIERS["coder"] == "low"


def test_role_inventory_groups_are_stable():
    assert tuple(AUTONOMOUS_AGENTS) == ("orchestrator",)
    assert tuple(DIRECTORS) == (
        "craft",
        "forge",
        "mind",
        "sentinel",
    )
    assert tuple(LEADERS) == (
        "builder",
        "shaper",
        "verifier",
        "courier",
        "herald",
        "archivist",
        "scout",
        "evolver",
        "reviewer",
    )
    assert tuple(SPECIALISTS) == (
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


def test_service_files_exist_for_both_platforms():
    assert (REPO_ROOT / "com.marrow.heart.plist").exists()
    assert (REPO_ROOT / "marrow-heart.service").exists()


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
