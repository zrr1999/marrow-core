"""Agent command execution — run opencode as a subprocess or via HTTP serve API."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
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


def _read_tail(path: Path, lines: int = 20) -> str:
    """Read the last `lines` lines of a text file, returning a single string."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        tail_lines = text.splitlines()[-lines:]
        return "\n".join(tail_lines).strip()
    except OSError:
        return ""


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
            except TimeoutError:
                timed_out = True
                proc.kill()
                await proc.wait()
    except FileNotFoundError:
        return RunResult(
            error=f"not found: {argv[0] if argv else '(empty)'}", started=started, ended=time.time()
        )
    except Exception as exc:
        return RunResult(error=str(exc), started=started, ended=time.time())

    if proc.returncode != 0 and not timed_out and stderr_path.exists():
        tail = _read_tail(stderr_path, lines=20)
        if tail:
            logger.debug("[runner] stderr tail ({}): {}", session_id, tail)

    return RunResult(
        returncode=proc.returncode,
        timed_out=timed_out,
        started=started,
        ended=time.time(),
    )


async def run_agent_http(
    opencode_url: str,
    *,
    message: str,
    timeout: int = 500,
    log_dir: Path,
    session_id: str = "",
) -> RunResult:
    """Execute an agent via the opencode serve HTTP API.

    Flow: create session -> send chat message -> wait for response.
    """
    started = time.time()
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"{session_id}.stdout.log"
    stderr_path = log_dir / f"{session_id}.stderr.log"

    base = opencode_url.rstrip("/")

    try:
        async with httpx.AsyncClient(base_url=base, timeout=timeout) as client:
            # 1. Create a new session
            logger.info("opencode serve: creating session at {}", base)
            resp = await client.post("/session")
            resp.raise_for_status()
            session_data = resp.json()
            oc_session_id = session_data.get("id", "")
            logger.debug("opencode serve: session created id={}", oc_session_id)

            # 2. Send chat message
            logger.info("opencode serve: sending chat to session {}", oc_session_id)
            chat_resp = await client.post(
                f"/session/{oc_session_id}/chat",
                json={
                    "parts": [{"type": "text", "text": message}],
                },
            )
            chat_resp.raise_for_status()
            result_data = chat_resp.json()

            # 3. Log output
            with stdout_path.open("ab") as f:
                f.write(json.dumps(result_data, indent=2, ensure_ascii=False).encode("utf-8"))
                f.write(b"\n")

            logger.debug("opencode serve: chat completed for session {}", oc_session_id)

            # 4. Clean up session
            logger.debug("opencode serve: deleting session {}", oc_session_id)
            with contextlib.suppress(Exception):
                await client.delete(f"/session/{oc_session_id}")

    except httpx.TimeoutException:
        with stderr_path.open("ab") as f:
            f.write(f"timeout after {timeout}s\n".encode())
        return RunResult(timed_out=True, started=started, ended=time.time())
    except httpx.HTTPStatusError as exc:
        err_msg = f"HTTP {exc.response.status_code}: {exc.response.text[:500]}"
        with stderr_path.open("ab") as f:
            f.write(err_msg.encode("utf-8"))
        return RunResult(error=err_msg, started=started, ended=time.time())
    except Exception as exc:
        with stderr_path.open("ab") as f:
            f.write(str(exc).encode("utf-8"))
        return RunResult(error=str(exc), started=started, ended=time.time())

    return RunResult(returncode=0, started=started, ended=time.time())
