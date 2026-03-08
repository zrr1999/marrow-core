"""Heartbeat loop — the core scheduler.

Each tick: gather context -> build prompt -> run agent.
Simplified from marrow-core: no JSON plugin protocol, just executable
scripts that output plain text to stdout.
"""

from __future__ import annotations

import asyncio
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from marrow_core.config import AgentConfig
from marrow_core.log_pruner import prune_exec_logs
from marrow_core.prompting import build_prompt, gather_context
from marrow_core.runner import run_agent
from marrow_core.workspace import load_rules

BASE_PROMPT = (
    "You are a relentless autonomous agent. Execute one round of high-value work now. "
    "If tasks are queued, attack the highest-priority one immediately. "
    "If the queue is empty, improve yourself: refine scripts, learn from past runs, "
    "explore your environment, or create tasks for future value. "
    "Never idle. Never ask questions. Produce tangible output every tick."
)

# Number of consecutive failed ticks before the circuit opens for one cycle.
_MAX_CONSECUTIVE_FAILURES = 3


class _CircuitBreaker:
    """Track consecutive failures; open (skip) one cycle when threshold is reached."""

    def __init__(self, max_failures: int, name: str) -> None:
        self._max = max_failures
        self._name = name
        self._count = 0

    def record(self, ok: bool) -> None:
        self._count = 0 if ok else self._count + 1

    @property
    def is_open(self) -> bool:
        if self._count >= self._max:
            logger.warning(
                "[{}] circuit open — {} consecutive failures, skipping one cycle",
                self._name,
                self._count,
            )
            self._count = 0
            return True
        return False


@dataclass
class AgentState:
    """Runtime state for a single agent — updated by the heartbeat loop."""

    name: str
    interval: int
    last_tick_at: float = 0.0
    last_tick_duration: float = 0.0
    next_tick_at: float = 0.0
    tick_count: int = 0
    running: bool = False
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "interval": self.interval,
            "last_tick_at": self.last_tick_at,
            "last_tick_duration": self.last_tick_duration,
            "next_tick_at": self.next_tick_at,
            "tick_count": self.tick_count,
            "running": self.running,
            "last_error": self.last_error,
        }


@dataclass
class HeartbeatState:
    """Shared state across all agents — read by the IPC server."""

    started_at: float = field(default_factory=time.time)
    agents: dict[str, AgentState] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "uptime": round(time.time() - self.started_at, 1),
            "agents": {n: a.to_dict() for n, a in self.agents.items()},
        }


def _session_id(agent_name: str) -> str:
    t = time.time()
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime(t))
    ms = int((t - int(t)) * 1000)
    safe = "".join(ch for ch in agent_name if ch.isalnum() or ch in "-_") or "agent"
    return f"{safe}-{ts}-{ms:03d}"


async def heartbeat(
    cfg: AgentConfig,
    core_dir: str,
    *,
    once: bool = False,
    dry_run: bool = False,
    state: HeartbeatState | None = None,
) -> None:
    """Run the heartbeat loop for a single agent."""
    rules = load_rules(core_dir)
    name = cfg.name
    interval = cfg.heartbeat_interval
    timeout = cfg.heartbeat_timeout
    circuit = _CircuitBreaker(_MAX_CONSECUTIVE_FAILURES, name)

    # Register agent state
    agent_state: AgentState | None = None
    if state is not None:
        agent_state = AgentState(name=name, interval=interval)
        state.agents[name] = agent_state

    logger.info("[{}] started (interval={}s, timeout={}s)", name, interval, timeout)

    while True:
        if circuit.is_open:
            pass  # circuit open — skip this cycle, circuit.is_open already logged
        else:
            if agent_state is not None:
                agent_state.running = True
                agent_state.last_tick_at = time.time()
            try:
                ok = await _tick(cfg, core_dir, rules, dry_run=dry_run)
                circuit.record(ok)
                if agent_state is not None:
                    agent_state.last_error = "" if ok else "tick returned failure"
            except Exception:
                logger.exception("[{}] tick failed", name)
                circuit.record(False)
                if agent_state is not None:
                    agent_state.last_error = "tick raised exception"
            finally:
                if agent_state is not None:
                    agent_state.running = False
                    agent_state.tick_count += 1
                    agent_state.last_tick_duration = round(
                        time.time() - agent_state.last_tick_at, 3
                    )
                    agent_state.next_tick_at = time.time() + interval

        if once:
            return
        await asyncio.sleep(interval)


async def _tick(
    cfg: AgentConfig,
    core_dir: str,
    rules: str,
    *,
    dry_run: bool = False,
) -> bool:
    name = cfg.name
    sid = _session_id(name)
    workspace = Path(cfg.workspace)
    log_dir = workspace / "runtime" / "logs" / "exec"

    # Gather context from all configured context dirs
    context_blocks = await gather_context(cfg.context_dirs)

    prompt = build_prompt(BASE_PROMPT, rules, context_blocks)

    if dry_run:
        print(f"--- DRY RUN [{name}] session={sid} ---")
        print(prompt)
        print("--- END ---")
        return True

    argv = shlex.split(cfg.agent_command)
    result = await run_agent(
        argv,
        message=prompt,
        timeout=cfg.heartbeat_timeout,
        cwd=cfg.workspace,
        log_dir=log_dir,
        session_id=sid,
    )

    if result.timed_out:
        logger.warning("[{}] timed out after {}s", name, cfg.heartbeat_timeout)
    if result.returncode is not None and result.returncode != 0:
        logger.warning("[{}] exited with code {}", name, result.returncode)

    logger.debug("[{}] tick done (session={}, duration={})", name, sid, result.duration)

    # Prune stale exec logs after every tick.
    if cfg.log_retention_days > 0 or cfg.log_max_count > 0:
        prune_exec_logs(
            log_dir,
            max_age_days=cfg.log_retention_days,
            max_count=cfg.log_max_count,
        )

    return result.ok
