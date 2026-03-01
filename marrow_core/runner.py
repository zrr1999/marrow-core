"""Agent command execution — run opencode as a subprocess."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from loguru import logger


async def run_agent(
    argv: list[str],
    *,
    message: str | None = None,
    timeout: int = 500,
    cwd: str | None = None,
    log_dir: Path | None = None,
    session_id: str = "",
) -> dict[str, Any]:
    """Execute an agent command with optional message argument.

    Returns a dict with returncode, timing, and error info.
    """
    cmd = list(argv)
    if cwd:
        cmd += ["--dir", cwd]
    if message:
        cmd.append(message)

    started = time.time()
    timed_out = False

    stdout_f = stderr_f = None
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout_f = (log_dir / f"{session_id}.stdout.log").open("ab")
        stderr_f = (log_dir / f"{session_id}.stderr.log").open("ab")

    try:
        logger.info("exec: {}", " ".join(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=stdout_f,
            stderr=stderr_f,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            timed_out = True
            proc.kill()
            await proc.wait()
    except FileNotFoundError:
        return {
            "returncode": None,
            "timed_out": False,
            "error": f"not found: {argv[0] if argv else '(empty)'}",
            "started": started,
            "ended": time.time(),
        }
    except Exception as exc:
        return {
            "returncode": None,
            "timed_out": False,
            "error": str(exc),
            "started": started,
            "ended": time.time(),
        }
    finally:
        if stdout_f:
            stdout_f.close()
        if stderr_f:
            stderr_f.close()

    ended = time.time()
    return {
        "returncode": proc.returncode,
        "timed_out": timed_out,
        "started": started,
        "ended": ended,
        "duration": round(ended - started, 3),
    }
