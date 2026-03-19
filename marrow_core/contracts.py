"""Stable runtime contracts for marrow-core.

This module intentionally describes only core-owned workspace and service layout.
Concrete role inventories live in external profiles such as marrow-bot.
"""

from __future__ import annotations

WORKSPACE_AGENT_DIR = ".opencode/agents"

DEFAULT_TOP_LEVEL_AGENT = "orchestrator"
AUTONOMOUS_AGENTS = (DEFAULT_TOP_LEVEL_AGENT,)

RUNTIME_DIRS = (
    "runtime/state",
    "runtime/checkpoints",
    "runtime/logs/exec",
    "runtime/control",
)

PLUGIN_DIRS = (
    "plugins",
    "runtime/plugins",
    "runtime/logs/plugins",
)

WORKSPACE_DIRS = (
    *RUNTIME_DIRS,
    *PLUGIN_DIRS,
    "context.d",
    WORKSPACE_AGENT_DIR,
)
