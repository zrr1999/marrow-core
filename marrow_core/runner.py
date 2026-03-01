"""Agent command execution — run the configured executor as a subprocess."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger


@dataclass(frozen=True)
class RunResult:
    """Outcome of a single agent execution."""

    returncode: int | None = None
    timed_out: bool = False
    error: str = ""
    started: float = field(default_factory=time.time)
    ended: float = field(default_factory=time.time)

    @property
    def duration(self) -> float:
        return round(self.ended - self.started, 3)

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.error


async def run_agent(
    argv: list[str],
    *,
    message: str,
    timeout: int = 500,
    cwd: str,
    log_dir: Path,
    session_id: str = "",
) -> RunResult:
    """Execute an agent command with message, cwd, and log_dir required."""
    cmd = [*argv, "--dir", cwd, "--", message]
    started = time.time()

    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"{session_id}.stdout.log"
    stderr_path = log_dir / f"{session_id}.stderr.log"

    try:
        logger.info("exec: {}", " ".join(cmd))
        with stdout_path.open("ab") as stdout_f, stderr_path.open("ab") as stderr_f:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=stdout_f, stderr=stderr_f)
            timed_out = False
            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                timed_out = True
                proc.kill()
                await proc.wait()
    except FileNotFoundError:
        return RunResult(
            error=f"not found: {argv[0] if argv else '(empty)'}", started=started, ended=time.time()
        )
    except Exception as exc:
        return RunResult(error=str(exc), started=started, ended=time.time())

    return RunResult(
        returncode=proc.returncode,
        timed_out=timed_out,
        started=started,
        ended=time.time(),
    )
