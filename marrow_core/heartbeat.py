"""Heartbeat loop — the core scheduler.

Each tick: gather context -> build prompt -> run agent.
Simplified from genesis-core: no JSON plugin protocol, just executable
scripts that output plain text to stdout.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import time
from pathlib import Path

from loguru import logger

from marrow_core.config import AgentConfig
from marrow_core.runner import run_agent
from marrow_core.sandbox import load_rules

BASE_PROMPT = "Run one round of work. Follow context and rules."


def _session_id(agent_name: str) -> str:
    t = time.time()
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime(t))
    ms = int((t - int(t)) * 1000)
    safe = "".join(ch for ch in agent_name if ch.isalnum() or ch in "-_") or "agent"
    return f"{safe}-{ts}-{ms:03d}"


async def _gather_context(context_dirs: list[str], timeout: int = 15) -> list[str]:
    """Run all executable scripts in context_dirs, collect stdout as text blocks.

    No JSON protocol — scripts simply print text to stdout.
    Order: alphabetical within each dir, dirs in config order.
    """
    blocks: list[str] = []
    for raw in context_dirs:
        d = Path(raw)
        if not d.is_dir():
            continue
        scripts = sorted(p for p in d.iterdir() if p.is_file() and os.access(p, os.X_OK))
        for script in scripts:
            try:
                proc = await asyncio.create_subprocess_exec(
                    str(script),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                out, _err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                text = (out or b"").decode("utf-8", errors="replace").strip()
                if text:
                    blocks.append(f"--- [{script.stem}] ---\n{text}")
                if proc.returncode != 0:
                    logger.warning("context script {} exited {}", script, proc.returncode)
            except asyncio.TimeoutError:
                logger.warning("context script {} timed out after {}s", script, timeout)
            except Exception as exc:
                logger.warning("context script {} failed: {}", script, exc)
    return blocks


def _build_prompt(
    base_prompt: str,
    rules: str,
    context_blocks: list[str],
) -> str:
    """Assemble final prompt: rules + base prompt + context blocks."""
    parts: list[str] = []
    if rules:
        parts.append(f"--- [Core Rules] ---\n{rules}")
    if base_prompt:
        parts.append(base_prompt.strip())
    parts.extend(context_blocks)
    return "\n\n".join(parts).strip() + "\n"


async def heartbeat(
    cfg: AgentConfig,
    core_dir: str,
    *,
    once: bool = False,
    dry_run: bool = False,
) -> None:
    """Run the heartbeat loop for a single agent."""
    rules = load_rules(core_dir)
    name = cfg.name
    interval = cfg.heartbeat_interval
    timeout = cfg.heartbeat_timeout

    logger.info("[{}] started (interval={}s, timeout={}s)", name, interval, timeout)

    while True:
        try:
            await _tick(cfg, core_dir, rules, dry_run=dry_run)
        except Exception:
            logger.exception("[{}] tick failed", name)

        if once:
            return
        await asyncio.sleep(interval)


async def _tick(
    cfg: AgentConfig,
    core_dir: str,
    rules: str,
    *,
    dry_run: bool = False,
) -> None:
    name = cfg.name
    sid = _session_id(name)
    workspace = Path(cfg.workspace)
    log_dir = workspace / "runtime" / "logs" / "exec"

    # Gather context from all configured context dirs
    context_blocks = await _gather_context(cfg.context_dirs)

    prompt = _build_prompt(BASE_PROMPT, rules, context_blocks)

    if dry_run:
        print(f"--- DRY RUN [{name}] session={sid} ---")
        print(prompt)
        print("--- END ---")
        return

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
