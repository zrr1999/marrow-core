"""Canonical architecture contract for marrow-core.

This module centralizes agent names, workspace topology, and handoff paths so
runtime code and contract tests can share one source of truth.
"""

from __future__ import annotations

AUTONOMOUS_AGENTS = (
    "scout",
    "conductor",
    "refit",
)

SPECIALIST_AGENTS = (
    "analyst",
    "coder",
    "filer",
    "git-ops",
    "ops",
    "researcher",
    "reviewer",
    "tester",
    "writer",
)

BASE_AGENT_FILES = AUTONOMOUS_AGENTS + SPECIALIST_AGENTS

AGENT_LAYERS = {
    "scout": "routine",
    "conductor": "operational",
    "refit": "strategic",
    "reviewer": "specialist",
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
    ".opencode/agents",
)


def handoff_dir(sender: str, recipient: str) -> str:
    return f"runtime/handoff/{sender}-to-{recipient}"
