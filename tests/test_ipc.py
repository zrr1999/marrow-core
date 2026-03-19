"""Tests for marrow_core.ipc."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path

import pytest

from marrow_core.heartbeat import AgentState, HeartbeatState
from marrow_core.ipc import start_ipc_server
from marrow_core.triggers import TriggerMailbox


def test_heartbeat_state_to_dict() -> None:
    state = HeartbeatState()
    state.agents["orchestrator"] = AgentState(name="orchestrator", interval=300, tick_count=5)
    payload = state.to_dict()
    assert payload["agents"]["orchestrator"]["tick_count"] == 5


@pytest.fixture
async def ipc_server():
    tmpdir = Path(tempfile.mkdtemp(prefix="mw_"))
    try:
        sock = str(tmpdir / "t.sock")
        state = HeartbeatState()
        state.agents["orchestrator"] = AgentState(name="orchestrator", interval=300, tick_count=3)
        trigger_mailboxes = {"orchestrator": TriggerMailbox()}
        server = await start_ipc_server(sock, state, trigger_mailboxes)
        yield sock, state, trigger_mailboxes
        server.close()
        await server.wait_closed()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


async def _ipc_request(sock: str, method: str, path: str, body: str = "") -> dict:
    reader, writer = await asyncio.open_unix_connection(sock)
    req = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\n"
    if body:
        req += f"Content-Length: {len(body)}\r\n"
    req += "\r\n"
    if body:
        req += body
    writer.write(req.encode())
    await writer.drain()
    resp = await asyncio.wait_for(reader.read(65536), timeout=5)
    writer.close()
    await writer.wait_closed()
    text = resp.decode("utf-8", errors="replace")
    idx = text.find("\r\n\r\n")
    return json.loads(text[idx + 4 :] if idx >= 0 else text)


async def test_health(ipc_server):
    sock, _, _ = ipc_server
    data = await _ipc_request(sock, "GET", "/health")
    assert data["status"] == "ok"


async def test_status(ipc_server):
    sock, _, _ = ipc_server
    data = await _ipc_request(sock, "GET", "/status")
    assert data["agents"]["orchestrator"]["tick_count"] == 3


async def test_ipc_socket_is_user_writable(ipc_server):
    sock, _, _ = ipc_server
    sock_mode = stat.S_IMODE(os.stat(sock).st_mode)
    assert sock_mode == 0o660


async def test_wake_sets_trigger_mailbox_with_prompt(ipc_server):
    sock, _, trigger_mailboxes = ipc_server
    payload = json.dumps(
        {"agent": "orchestrator", "reason": "test", "prompt": "Focus on repair mode."}
    )
    data = await _ipc_request(sock, "POST", "/wake", payload)
    trigger = trigger_mailboxes["orchestrator"].consume_pending()

    assert data == {"ok": True, "agent": "orchestrator"}
    assert trigger is not None
    assert trigger.reason == "test"
    assert trigger.prompt == "Focus on repair mode."


async def test_unknown_path_returns_error(ipc_server):
    sock, _, _ = ipc_server
    data = await _ipc_request(sock, "GET", "/nope")
    assert "error" in data
