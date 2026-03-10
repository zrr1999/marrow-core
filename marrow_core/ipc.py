"""IPC server — Unix domain socket with JSON API.

Runs as a background asyncio task alongside the heartbeat loop.
Provides task submission, queue listing, and heartbeat status over
a Unix domain socket using a minimal HTTP/1.1 protocol with JSON bodies.

Usage with curl:
    curl --unix-socket /path/to/marrow.sock http://localhost/status
    curl --unix-socket /path/to/marrow.sock -X POST -d '{"title":"fix bug"}' http://localhost/tasks
    curl --unix-socket /path/to/marrow.sock -X POST -d '{"agent":"curator"}' http://localhost/wake
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

from loguru import logger

from marrow_core.contracts import ROLE_PATHS, STEWARDS, can_assign_task
from marrow_core.task_queue import create_task_file, list_tasks

if TYPE_CHECKING:
    from marrow_core.heartbeat import HeartbeatState


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

_TASK_ACCEPTANCE_LEVELS = {"light", "heavy"}
_TASK_STATUSES = {"queued", "active", "blocked", "done"}
_TASK_TYPES = {"intake", "delivery", "scan", "innovation", "repair"}


def _default_task_type(role_name: str) -> str:
    if role_name == "curator":
        return "intake"
    if role_name == "innovation-steward" or role_name == "prototype-lead":
        return "innovation"
    if role_name == "repo-steward" or role_name == "review-lead":
        return "scan"
    if role_name in STEWARDS:
        return "delivery"
    return "delivery"


def _normalize_task_request(req: dict[str, Any]) -> tuple[dict[str, str] | None, str | None]:
    title = str(req.get("title", "")).strip()
    if not title:
        return None, "title is required"

    body = str(req.get("body", "")).strip()
    owner = str(req.get("owner", "")).strip() or "curator"
    assignee = str(req.get("assignee", "")).strip() or owner
    delegated_by = str(req.get("delegated_by", "")).strip()

    for field_name, role_name in (("owner", owner), ("assignee", assignee)):
        if role_name not in ROLE_PATHS:
            return None, f"{field_name} must be a known role: {role_name}"
    if delegated_by and delegated_by not in ROLE_PATHS:
        return None, f"delegated_by must be a known role: {delegated_by}"
    if not can_assign_task(owner, assignee):
        return None, f"invalid delegation: {owner} cannot assign directly to {assignee}"

    acceptance = str(req.get("acceptance", "")).strip().lower()
    if not acceptance:
        acceptance = "light" if owner == "curator" else "heavy"
    if acceptance not in _TASK_ACCEPTANCE_LEVELS:
        return None, f"acceptance must be one of {sorted(_TASK_ACCEPTANCE_LEVELS)}"

    status = str(req.get("status", "")).strip().lower() or "queued"
    if status not in _TASK_STATUSES:
        return None, f"status must be one of {sorted(_TASK_STATUSES)}"

    task_type = str(req.get("task_type", "")).strip().lower() or _default_task_type(assignee)
    if task_type not in _TASK_TYPES:
        return None, f"task_type must be one of {sorted(_TASK_TYPES)}"

    metadata = {
        "owner": owner,
        "assignee": assignee,
        "acceptance": acceptance,
        "status": status,
        "task_type": task_type,
    }
    if delegated_by:
        metadata["delegated_by"] = delegated_by

    return {"title": title, "body": body, "metadata": metadata}, None


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
    state: HeartbeatState,
    wake_events: dict[str, asyncio.Event],
) -> None:
    """Handle one HTTP request over the Unix socket."""
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=30)
        if not request_line:
            return
        parts = request_line.decode("utf-8", errors="replace").strip().split()
        if len(parts) < 2:
            return
        method, raw_path = parts[0], parts[1]
        parsed_path = urlsplit(raw_path)
        path = parsed_path.path
        params = parse_qs(parsed_path.query)

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
            _send(
                writer,
                200,
                {
                    "tasks": list_tasks(
                        task_dir,
                        assignee=params.get("assignee", [""])[0],
                        owner=params.get("owner", [""])[0],
                        status=params.get("status", [""])[0],
                    )
                },
            )

        elif path == "/tasks" and method == "POST":
            try:
                req = json.loads(raw_body) if raw_body else {}
            except json.JSONDecodeError:
                _send(writer, 400, {"error": "invalid JSON"})
                return
            if not isinstance(req, dict):
                _send(writer, 400, {"error": "request body must be a JSON object"})
                return
            normalized, error = _normalize_task_request(req)
            if error:
                _send(writer, 400, {"error": error})
                return
            assert normalized is not None
            fp = create_task_file(
                task_dir,
                normalized["title"],
                normalized["body"],
                metadata=normalized["metadata"],
            )
            logger.info("task submitted via ipc: {}", fp.name)
            _send(writer, 200, {"ok": True, "file": fp.name, **normalized["metadata"]})

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
    state: HeartbeatState,
    wake_events: dict[str, asyncio.Event],
) -> asyncio.Server:
    """Start the IPC server on a Unix domain socket."""
    sock = Path(socket_path)
    sock.parent.mkdir(parents=True, exist_ok=True)
    # Remove stale socket file
    if sock.exists():
        sock.unlink()

    td = Path(task_dir)

    async def handler(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        await _handle(r, w, td, state, wake_events)

    server = await asyncio.start_unix_server(handler, path=str(sock))
    logger.info("ipc server listening on {}", sock)
    return server
