"""Canonical architecture contract for marrow-core.

This module centralizes role inventory and workspace topology so runtime code
and contract tests can share one source of truth.
"""

from __future__ import annotations

ROLE_DIR = "roles"
WORKSPACE_AGENT_DIR = ".opencode/agents"

TOP_LEVEL_AGENTS = ("curator",)
STEWARDS = (
    "delivery-steward",
    "portfolio-steward",
    "research-steward",
    "acceptance-steward",
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
    "delivery-steward": "roles/stewards/delivery-steward.md",
    "portfolio-steward": "roles/stewards/portfolio-steward.md",
    "research-steward": "roles/stewards/research-steward.md",
    "acceptance-steward": "roles/stewards/acceptance-steward.md",
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
