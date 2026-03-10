"""Canonical architecture contract for marrow-core.

This module centralizes role inventory and workspace topology so runtime code
and contract tests can share one source of truth.
"""

from __future__ import annotations

ROLE_DIR = "roles"
WORKSPACE_AGENT_DIR = ".opencode/agents"

TOP_LEVEL_AGENTS = ("curator",)
STEWARDS = (
    "conductor",
    "repo-steward",
    "innovation-steward",
)
LEADERS = (
    "refactor-lead",
    "prototype-lead",
    "review-lead",
    "ops-lead",
)
EXPERTS = (
    "analyst",
    "researcher",
    "coder",
    "tester",
    "writer",
    "git-ops",
    "filer",
)

# Scheduled agents are a runtime concern; keep them distinct from the full role inventory.
AUTONOMOUS_AGENTS = TOP_LEVEL_AGENTS
SYNCED_ROLE_FILES = TOP_LEVEL_AGENTS + STEWARDS + LEADERS + EXPERTS

ROLE_MODEL_TIERS = {
    "curator": "high",
    **dict.fromkeys(STEWARDS + LEADERS, "medium"),
    **dict.fromkeys(EXPERTS, "low"),
}

ROLE_PATHS = {
    "curator": "roles/curator.md",
    "conductor": "roles/stewards/conductor.md",
    "repo-steward": "roles/stewards/repo-steward.md",
    "innovation-steward": "roles/stewards/innovation-steward.md",
    "refactor-lead": "roles/leaders/refactor-lead.md",
    "prototype-lead": "roles/leaders/prototype-lead.md",
    "review-lead": "roles/leaders/review-lead.md",
    "ops-lead": "roles/leaders/ops-lead.md",
    "analyst": "roles/experts/analyst.md",
    "researcher": "roles/experts/researcher.md",
    "coder": "roles/experts/coder.md",
    "tester": "roles/experts/tester.md",
    "writer": "roles/experts/writer.md",
    "git-ops": "roles/experts/git-ops.md",
    "filer": "roles/experts/filer.md",
}

RUNTIME_DIRS = (
    "runtime/state",
    "runtime/checkpoints",
    "runtime/logs/exec",
)

TASK_DIRS = (
    "tasks/queue",
    "tasks/delegated",
    "tasks/done",
)

WORKSPACE_DIRS = (
    RUNTIME_DIRS[0],
    RUNTIME_DIRS[1],
    RUNTIME_DIRS[2],
    *TASK_DIRS,
    "context.d",
    WORKSPACE_AGENT_DIR,
)

ROLE_LAYERS = {
    "curator": "top-level",
    **dict.fromkeys(STEWARDS, "steward"),
    **dict.fromkeys(LEADERS, "leader"),
    **dict.fromkeys(EXPERTS, "expert"),
}

STEWARD_LEADER_ROUTES = {
    "conductor": (
        "refactor-lead",
        "ops-lead",
        "review-lead",
        "prototype-lead",
    ),
    "repo-steward": (
        "review-lead",
        "ops-lead",
        "refactor-lead",
        "prototype-lead",
    ),
    "innovation-steward": (
        "prototype-lead",
        "review-lead",
        "refactor-lead",
        "ops-lead",
    ),
}

LEADER_EXPERT_ROUTES = {
    "refactor-lead": (
        "analyst",
        "coder",
        "tester",
        "writer",
        "git-ops",
        "filer",
    ),
    "prototype-lead": (
        "researcher",
        "analyst",
        "coder",
        "tester",
        "writer",
    ),
    "review-lead": (
        "analyst",
        "researcher",
        "writer",
        "tester",
        "git-ops",
    ),
    "ops-lead": (
        "analyst",
        "coder",
        "tester",
        "git-ops",
        "filer",
        "writer",
    ),
}

DIRECT_REPORTS = {
    "curator": STEWARDS,
    **STEWARD_LEADER_ROUTES,
    **LEADER_EXPERT_ROUTES,
}


def role_layer(name: str) -> str:
    """Return the semantic layer for a known role."""
    return ROLE_LAYERS.get(name, "unknown")


def allowed_delegate_targets(name: str) -> tuple[str, ...]:
    """Return the direct children a role may assign to."""
    return DIRECT_REPORTS.get(name, ())


def can_assign_task(owner: str, assignee: str) -> bool:
    """Return True when a task owner may assign directly to the assignee."""
    if owner == assignee:
        return True
    return assignee in DIRECT_REPORTS.get(owner, ())
