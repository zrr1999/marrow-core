"""Canonical architecture contract for marrow-core.

This module centralizes role inventory and workspace topology so runtime code
and contract tests can share one source of truth.
"""

from __future__ import annotations

ROLE_DIR = "roles"
WORKSPACE_AGENT_DIR = ".opencode/agents"

ROOT_AGENTS = ("refit",)
STEWARDS = (
    "conductor",
    "repo-steward",
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
AUTONOMOUS_AGENTS = ROOT_AGENTS
SYNCED_ROLE_FILES = ROOT_AGENTS + STEWARDS + LEADERS + EXPERTS

ROLE_MODEL_TIERS = {
    "refit": "high",
    **dict.fromkeys(STEWARDS + LEADERS, "medium"),
    **dict.fromkeys(EXPERTS, "low"),
}

ROLE_PATHS = {
    "refit": "roles/refit.md",
    "conductor": "roles/l3/conductor.md",
    "repo-steward": "roles/l3/repo-steward.md",
    "refactor-lead": "roles/l2/refactor-lead.md",
    "prototype-lead": "roles/l2/prototype-lead.md",
    "review-lead": "roles/l2/review-lead.md",
    "ops-lead": "roles/l2/ops-lead.md",
    "analyst": "roles/l1/analyst.md",
    "researcher": "roles/l1/researcher.md",
    "coder": "roles/l1/coder.md",
    "tester": "roles/l1/tester.md",
    "writer": "roles/l1/writer.md",
    "git-ops": "roles/l1/git-ops.md",
    "filer": "roles/l1/filer.md",
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
