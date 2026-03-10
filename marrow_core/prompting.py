"""Prompt assembly and context execution helpers."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from pathlib import Path

from loguru import logger


async def gather_context(
    context_dirs: list[str],
    timeout: int = 15,
    *,
    extra_env: Mapping[str, str] | None = None,
) -> list[str]:
    """Run executable context scripts and collect their stdout blocks."""
    blocks: list[str] = []
    env = os.environ.copy()
    if extra_env:
        env.update({key: value for key, value in extra_env.items() if value})
    for raw in context_dirs:
        directory = Path(raw)
        if not directory.is_dir():
            continue
        scripts = sorted(p for p in directory.iterdir() if p.is_file() and os.access(p, os.X_OK))
        for script in scripts:
            try:
                proc = await asyncio.create_subprocess_exec(
                    str(script),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
                out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                text = (out or b"").decode("utf-8", errors="replace").strip()
                if text:
                    blocks.append(f"--- [{script.stem}] ---\n{text}")
                if proc.returncode != 0:
                    logger.warning("context script {} exited {}", script, proc.returncode)
                    if err:
                        logger.debug(
                            "context script {} stderr: {}",
                            script,
                            err.decode("utf-8", errors="replace").strip(),
                        )
            except TimeoutError:
                logger.warning("context script {} timed out after {}s", script, timeout)
            except Exception as exc:
                logger.warning("context script {} failed: {}", script, exc)
    return blocks


def build_prompt(base_prompt: str, rules: str, context_blocks: list[str]) -> str:
    """Assemble final prompt from rules, base prompt, and context blocks."""
    parts: list[str] = []
    if rules:
        parts.append(f"--- [Core Rules] ---\n{rules}")
    if base_prompt:
        parts.append(base_prompt.strip())
    parts.extend(context_blocks)
    return "\n\n".join(parts).strip() + "\n"
