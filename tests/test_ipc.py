"""Tests for marrow_core.ipc."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from marrow_core.heartbeat import AgentState, HeartbeatState
from marrow_core.ipc import (
    _create_task_file,
    _list_tasks,
    start_ipc_server,
)

# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------


def test_create_task_file(tmp_path: Path):
    queue = tmp_path / "tasks" / "queue"
    fp = _create_task_file(queue, "My Task", "Details here")
    assert fp.exists()
    assert fp.suffix == ".md"
    content = fp.read_text()
    assert "# My Task" in content
    assert "Details here" in content


def test_create_task_file_no_body(tmp_path: Path):
    queue = tmp_path / "tasks" / "queue"
    fp = _create_task_file(queue, "Quick fix", "")
    content = fp.read_text()
    assert "# Quick fix" in content
    assert content.count("\n") == 1


def test_create_task_file_sanitizes_name(tmp_path: Path):
    queue = tmp_path / "tasks" / "queue"
    fp = _create_task_file(queue, "fix: the <bug> & crash!", "")
    assert "<" not in fp.name
    assert ">" not in fp.name
    assert "&" not in fp.name


def test_list_tasks_empty(tmp_path: Path):
    assert _list_tasks(tmp_path / "nonexistent") == []


def test_list_tasks(tmp_path: Path):
    queue = tmp_path / "queue"
    _create_task_file(queue, "Task A", "")
    _create_task_file(queue, "Task B", "body")
    tasks = _list_tasks(queue)
    assert len(tasks) == 2
    titles = {t["title"] for t in tasks}
    assert "Task A" in titles
    assert "Task B" in titles


# ---------------------------------------------------------------------------
# HeartbeatState tests
# ---------------------------------------------------------------------------


def test_heartbeat_state_to_dict():
    state = HeartbeatState()
    state.agents["scout"] = AgentState(name="scout", interval=300, tick_count=5)
    d = state.to_dict()
    assert "uptime" in d
    assert "agents" in d
    assert d["agents"]["scout"]["tick_count"] == 5


# ---------------------------------------------------------------------------
# Integration tests over Unix socket
# ---------------------------------------------------------------------------


@pytest.fixture
async def ipc_server(tmp_path: Path):
    """Start the IPC server on a temp socket and yield (socket_path, task_dir, state)."""
    sock = str(tmp_path / "test.sock")
    task_dir = tmp_path / "tasks" / "queue"
    state = HeartbeatState()
    state.agents["scout"] = AgentState(name="scout", interval=300, tick_count=3)
    server = await start_ipc_server(sock, str(task_dir), state)
    yield sock, task_dir, state
    server.close()
    await server.wait_closed()


async def _ipc_request(sock: str, method: str, path: str, body: str = "") -> dict:
    """Send a raw HTTP request over Unix socket and return parsed JSON."""
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
    json_str = text[idx + 4 :] if idx >= 0 else text
    return json.loads(json_str)


async def test_health(ipc_server):
    sock, _, _ = ipc_server
    data = await _ipc_request(sock, "GET", "/health")
    assert data["status"] == "ok"


async def test_status(ipc_server):
    sock, _, _ = ipc_server
    data = await _ipc_request(sock, "GET", "/status")
    assert "uptime" in data
    assert "agents" in data
    assert data["agents"]["scout"]["tick_count"] == 3


async def test_post_task(ipc_server):
    sock, task_dir, _ = ipc_server
    payload = json.dumps({"title": "test task", "body": "some details"})
    data = await _ipc_request(sock, "POST", "/tasks", payload)
    assert data["ok"] is True
    assert "file" in data
    # Verify file was created
    files = list(task_dir.glob("*.md"))
    assert len(files) == 1
    assert "# test task" in files[0].read_text()


async def test_post_task_no_title(ipc_server):
    sock, _, _ = ipc_server
    payload = json.dumps({"title": "", "body": "text"})
    data = await _ipc_request(sock, "POST", "/tasks", payload)
    assert "error" in data
    assert "title" in data["error"]


async def test_post_task_bad_json(ipc_server):
    sock, _, _ = ipc_server
    data = await _ipc_request(sock, "POST", "/tasks", "not json")
    assert "error" in data


async def test_list_tasks_via_ipc_empty(ipc_server):
    sock, _, _ = ipc_server
    data = await _ipc_request(sock, "GET", "/tasks")
    assert data["tasks"] == []


async def test_list_tasks_after_add(ipc_server):
    sock, _, _ = ipc_server
    payload = json.dumps({"title": "alpha"})
    await _ipc_request(sock, "POST", "/tasks", payload)
    data = await _ipc_request(sock, "GET", "/tasks")
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["title"] == "alpha"


async def test_not_found(ipc_server):
    sock, _, _ = ipc_server
    data = await _ipc_request(sock, "GET", "/nope")
    assert "error" in data
