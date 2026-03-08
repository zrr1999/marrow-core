"""Canonical architecture contract for marrow-core.

This module centralizes role inventory and workspace topology so runtime code
and contract tests can share one source of truth.
"""

from __future__ import annotations

ROLE_DIR = "roles"
WORKSPACE_AGENT_DIR = ".opencode/agents"

SCHEDULED_MAINS = (
    "scout",
    "conductor",
    "refit",
)

EXPERT_LEADS = (
    "refactor-lead",
    "prototype-lead",
    "review-lead",
    "ops-lead",
)

LEAF_WORKERS = (
    "analyst",
    "researcher",
    "coder",
    "tester",
    "writer",
    "git-ops",
    "filer",
)

AUTONOMOUS_AGENTS = SCHEDULED_MAINS
SYNCED_ROLE_FILES = SCHEDULED_MAINS + EXPERT_LEADS + LEAF_WORKERS

ROLE_MODEL_TIERS = {
    "scout": "routine",
    "conductor": "operational",
    "refit": "strategic",
    **dict.fromkeys(EXPERT_LEADS + LEAF_WORKERS, "specialist"),
}

ROLE_PATHS = {
    "scout": "roles/l1/scout.md",
    "conductor": "roles/l1/conductor.md",
    "refit": "roles/l1/refit.md",
    "refactor-lead": "roles/l2/refactor-lead.md",
    "prototype-lead": "roles/l2/prototype-lead.md",
    "review-lead": "roles/l2/review-lead.md",
    "ops-lead": "roles/l2/ops-lead.md",
    "analyst": "roles/l3/analyst.md",
    "researcher": "roles/l3/researcher.md",
    "coder": "roles/l3/coder.md",
    "tester": "roles/l3/tester.md",
    "writer": "roles/l3/writer.md",
    "git-ops": "roles/l3/git-ops.md",
    "filer": "roles/l3/filer.md",
}

HANDOFF_ROUTES = (
    ("scout", "conductor"),
    ("conductor", "scout"),
    ("scout", "human"),
)

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
    *(f"runtime/handoff/{sender}-to-{recipient}" for sender, recipient in HANDOFF_ROUTES),
    RUNTIME_DIRS[1],
    RUNTIME_DIRS[2],
    *TASK_DIRS,
    "context.d",
    WORKSPACE_AGENT_DIR,
)


def handoff_dir(sender: str, recipient: str) -> str:
    return f"runtime/handoff/{sender}-to-{recipient}"
