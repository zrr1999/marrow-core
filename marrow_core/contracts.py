"""Canonical architecture contract for marrow-core.

This module centralizes role inventory and workspace topology so runtime code
and contract tests can share one source of truth.
"""

from __future__ import annotations

ROLE_DIR = "roles"
WORKSPACE_AGENT_DIR = ".opencode/agents"

TOP_LEVEL_AGENTS = ("orchestrator",)
DIRECTORS = (
    "craft",
    "forge",
    "mind",
    "sentinel",
)
LEADERS = (
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
SPECIALISTS = (
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
SYNCED_ROLE_FILES = TOP_LEVEL_AGENTS + DIRECTORS + LEADERS + SPECIALISTS

ROLE_MODEL_TIERS = {
    "orchestrator": "high",
    **dict.fromkeys(DIRECTORS + LEADERS, "medium"),
    **dict.fromkeys(SPECIALISTS, "low"),
}

ROLE_PATHS = {
    "orchestrator": "roles/orchestrator.md",
    "craft": "roles/directors/craft.md",
    "forge": "roles/directors/forge.md",
    "mind": "roles/directors/mind.md",
    "sentinel": "roles/directors/sentinel.md",
    "builder": "roles/leaders/builder.md",
    "shaper": "roles/leaders/shaper.md",
    "verifier": "roles/leaders/verifier.md",
    "courier": "roles/leaders/courier.md",
    "herald": "roles/leaders/herald.md",
    "archivist": "roles/leaders/archivist.md",
    "scout": "roles/leaders/scout.md",
    "evolver": "roles/leaders/evolver.md",
    "reviewer": "roles/leaders/reviewer.md",
    "analyst": "roles/specialists/analyst.md",
    "researcher": "roles/specialists/researcher.md",
    "coder": "roles/specialists/coder.md",
    "tester": "roles/specialists/tester.md",
    "writer": "roles/specialists/writer.md",
    "git-ops": "roles/specialists/git-ops.md",
    "filer": "roles/specialists/filer.md",
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
