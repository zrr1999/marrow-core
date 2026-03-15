"""IPC server — Unix domain socket with JSON API.

Runs as a background asyncio task alongside the heartbeat loop.
Provides task submission, queue listing, and heartbeat status over
a Unix domain socket using a minimal HTTP/1.1 protocol with JSON bodies.

Usage with curl:
    curl --unix-socket /path/to/marrow.sock http://localhost/status
    curl --unix-socket /path/to/marrow.sock -X POST -d '{"title":"fix bug"}' http://localhost/tasks
    curl --unix-socket /path/to/marrow.sock -X POST -d '{"agent":"orchestrator"}' http://localhost/wake
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from loguru import logger

from marrow_core.task_queue import create_task_file, list_tasks

if TYPE_CHECKING:
    from collections.abc import Mapping


class _WakeHandle(Protocol):
    def set(self) -> None: ...


class _StateView(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Minimal HTTP helpers
# ---------------------------------------------------------------------------

_STATUS_TEXT = {
    200: "OK",
    400: "Bad Request",
    404: "Not Found",
    405: "Method Not Allowed",
    500: "Internal Server Error",
}


def _send(
    writer: asyncio.StreamWriter,
    status: int,
    body: dict[str, Any] | str,
) -> None:
    """Write an HTTP/1.1 JSON response."""
    reason = _STATUS_TEXT.get(status, "OK")
    payload = json.dumps(body).encode() if isinstance(body, dict) else body.encode()
    writer.write(
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: application/json; charset=utf-8\r\n"
        f"Content-Length: {len(payload)}\r\n"
        f"Connection: close\r\n"
        f"\r\n".encode()
        + payload
    )


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------


async def _handle(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    task_dir: Path,
    state: _StateView,
    wake_events: Mapping[str, _WakeHandle],
    *,
    task_submitter=None,
    task_lister=None,
) -> None:
    """Handle one HTTP request over the Unix socket."""
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=30)
        if not request_line:
            return
        parts = request_line.decode("utf-8", errors="replace").strip().split()
        if len(parts) < 2:
            return
        method, path = parts[0], parts[1]

        # Read headers
        content_length = 0
        while True:
            hdr = await asyncio.wait_for(reader.readline(), timeout=10)
            line = hdr.decode("utf-8", errors="replace").strip()
            if not line:
                break
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())

        # Read body if present
        raw_body = ""
        if content_length > 0:
            data = await asyncio.wait_for(reader.readexactly(content_length), timeout=10)
            raw_body = data.decode("utf-8", errors="replace")

        # Route
        if path == "/health" and method == "GET":
            _send(writer, 200, {"status": "ok"})

        elif path == "/status" and method == "GET":
            _send(writer, 200, state.to_dict())

        elif path == "/tasks" and method == "GET":
            tasks = task_lister() if task_lister is not None else list_tasks(task_dir)
            _send(writer, 200, {"tasks": tasks})

        elif path == "/tasks" and method == "POST":
            try:
                req = json.loads(raw_body) if raw_body else {}
            except json.JSONDecodeError:
                _send(writer, 400, {"error": "invalid JSON"})
                return
            title = req.get("title", "").strip() if isinstance(req, dict) else ""
            if not title:
                _send(writer, 400, {"error": "title is required"})
                return
            body_text = req.get("body", "").strip() if isinstance(req, dict) else ""
            fp = (
                task_submitter(title, body_text)
                if task_submitter is not None
                else create_task_file(task_dir, title, body_text)
            )
            logger.info("task submitted via ipc: {}", fp.name)
            _send(writer, 200, {"ok": True, "file": fp.name})

        elif path == "/wake" and method == "POST":
            try:
                req = json.loads(raw_body) if raw_body else {}
            except json.JSONDecodeError:
                _send(writer, 400, {"error": "invalid JSON"})
                return
            agent = req.get("agent", "").strip() if isinstance(req, dict) else ""
            if not agent:
                _send(writer, 400, {"error": "agent is required"})
                return
            event = wake_events.get(agent)
            if event is None:
                _send(writer, 404, {"error": f"unknown agent: {agent}"})
                return
            event.set()
            reason = req.get("reason", "").strip() if isinstance(req, dict) else ""
            if reason:
                logger.info('wake submitted via ipc for "{}": {}', agent, reason)
            else:
                logger.info('wake submitted via ipc for "{}"', agent)
            _send(writer, 200, {"ok": True, "agent": agent})

        else:
            _send(writer, 404, {"error": "not found"})

    except (TimeoutError, ConnectionError):
        pass  # Idle / broken connections
    except Exception as exc:
        logger.warning("ipc request error: {}", exc)
        with contextlib.suppress(Exception):
            _send(writer, 500, {"error": "internal server error"})
    finally:
        with contextlib.suppress(Exception):
            writer.close()
            await writer.wait_closed()


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


async def start_ipc_server(
    socket_path: str,
    task_dir: str,
    state: _StateView,
    wake_events: Mapping[str, _WakeHandle],
    *,
    task_submitter=None,
    task_lister=None,
) -> asyncio.Server:
    """Start the IPC server on a Unix domain socket."""
    sock = Path(socket_path)
    sock.parent.mkdir(parents=True, exist_ok=True)
    # Remove stale socket file
    if sock.exists():
        sock.unlink()

    td = Path(task_dir)
    td.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(PermissionError):
        os.chmod(td, 0o770)

    async def handler(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        await _handle(
            r,
            w,
            td,
            state,
            wake_events,
            task_submitter=task_submitter,
            task_lister=task_lister,
        )

    server = await asyncio.start_unix_server(handler, path=str(sock))
    with contextlib.suppress(PermissionError):
        os.chmod(sock, 0o660)
    logger.info("ipc server listening on {}", sock)
    return server
