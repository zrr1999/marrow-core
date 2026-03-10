"""Tests for marrow_core.ipc."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from marrow_core.heartbeat import AgentState, HeartbeatState
from marrow_core.ipc import start_ipc_server
from marrow_core.task_queue import create_task_file, list_tasks

# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------


def test_create_task_file(tmp_path: Path):
    queue = tmp_path / "tasks" / "queue"
    fp = create_task_file(
        queue,
        "My Task",
        "Details here",
        metadata={"owner": "curator", "assignee": "conductor", "acceptance": "light"},
    )
    assert fp.exists()
    assert fp.suffix == ".md"
    content = fp.read_text()
    assert "owner: curator" in content
    assert "# My Task" in content
    assert "Details here" in content


def test_create_task_file_no_body(tmp_path: Path):
    queue = tmp_path / "tasks" / "queue"
    fp = create_task_file(queue, "Quick fix", "")
    content = fp.read_text()
    assert "# Quick fix" in content
    assert content.count("\n") == 1


def test_create_task_file_sanitizes_name(tmp_path: Path):
    queue = tmp_path / "tasks" / "queue"
    fp = create_task_file(queue, "fix: the <bug> & crash!", "")
    assert "<" not in fp.name
    assert ">" not in fp.name
    assert "&" not in fp.name


def test_list_tasks_empty(tmp_path: Path):
    assert list_tasks(tmp_path / "nonexistent") == []


def test_list_tasks(tmp_path: Path):
    queue = tmp_path / "queue"
    create_task_file(queue, "Task A", "", metadata={"assignee": "curator"})
    create_task_file(queue, "Task B", "body", metadata={"assignee": "conductor"})
    tasks = list_tasks(queue)
    assert len(tasks) == 2
    titles = {t["title"] for t in tasks}
    assert "Task A" in titles
    assert "Task B" in titles


# ---------------------------------------------------------------------------
# HeartbeatState tests
# ---------------------------------------------------------------------------


def test_heartbeat_state_to_dict():
    state = HeartbeatState()
    state.agents["curator"] = AgentState(name="curator", interval=300, tick_count=5)
    d = state.to_dict()
    assert "uptime" in d
    assert "agents" in d
    assert d["agents"]["curator"]["tick_count"] == 5


# ---------------------------------------------------------------------------
# Integration tests over Unix socket
# ---------------------------------------------------------------------------


@pytest.fixture
async def ipc_server():
    """Start the IPC server on a temp socket and yield (socket_path, task_dir, state).

    Uses tempfile.mkdtemp() in /tmp to guarantee a short path — macOS enforces
    a 104-byte limit on AF_UNIX socket paths, which pytest's tmp_path can exceed
    in deep CI runner environments.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="mw_"))
    try:
        sock = str(tmpdir / "t.sock")
        task_dir = tmpdir / "tasks" / "queue"
        state = HeartbeatState()
        state.agents["curator"] = AgentState(name="curator", interval=300, tick_count=3)
        wake_events = {"curator": asyncio.Event()}
        server = await start_ipc_server(sock, str(task_dir), state, wake_events)
        yield sock, task_dir, state, wake_events
        server.close()
        await server.wait_closed()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


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
    sock, _, _, _ = ipc_server
    data = await _ipc_request(sock, "GET", "/health")
    assert data["status"] == "ok"


async def test_status(ipc_server):
    sock, _, _, _ = ipc_server
    data = await _ipc_request(sock, "GET", "/status")
    assert "uptime" in data
    assert "agents" in data
    assert data["agents"]["curator"]["tick_count"] == 3


async def test_post_task(ipc_server):
    sock, task_dir, _, _ = ipc_server
    payload = json.dumps(
        {
            "title": "test task",
            "body": "some details",
            "owner": "curator",
            "assignee": "conductor",
        }
    )
    data = await _ipc_request(sock, "POST", "/tasks", payload)
    assert data["ok"] is True
    assert "file" in data
    assert data["owner"] == "curator"
    assert data["assignee"] == "conductor"
    # Verify file was created
    files = list(task_dir.glob("*.md"))
    assert len(files) == 1
    assert "# test task" in files[0].read_text()


async def test_post_task_no_title(ipc_server):
    sock, _, _, _ = ipc_server
    payload = json.dumps({"title": "", "body": "text"})
    data = await _ipc_request(sock, "POST", "/tasks", payload)
    assert "error" in data
    assert "title" in data["error"]


async def test_post_task_bad_json(ipc_server):
    sock, _, _, _ = ipc_server
    data = await _ipc_request(sock, "POST", "/tasks", "not json")
    assert "error" in data


async def test_list_tasks_via_ipc_empty(ipc_server):
    sock, _, _, _ = ipc_server
    data = await _ipc_request(sock, "GET", "/tasks")
    assert data["tasks"] == []


async def test_list_tasks_after_add(ipc_server):
    sock, _, _, _ = ipc_server
    payload = json.dumps({"title": "alpha", "owner": "curator", "assignee": "conductor"})
    await _ipc_request(sock, "POST", "/tasks", payload)
    data = await _ipc_request(sock, "GET", "/tasks")
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["title"] == "alpha"
    assert data["tasks"][0]["assignee"] == "conductor"


async def test_list_tasks_can_filter_by_assignee(ipc_server):
    sock, _, _, _ = ipc_server
    await _ipc_request(
        sock,
        "POST",
        "/tasks",
        json.dumps({"title": "alpha", "owner": "curator", "assignee": "conductor"}),
    )
    await _ipc_request(
        sock,
        "POST",
        "/tasks",
        json.dumps({"title": "beta", "owner": "curator", "assignee": "repo-steward"}),
    )
    data = await _ipc_request(sock, "GET", "/tasks?assignee=conductor")
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["title"] == "alpha"


async def test_post_task_rejects_invalid_delegation(ipc_server):
    sock, _, _, _ = ipc_server
    payload = json.dumps({"title": "bad", "owner": "curator", "assignee": "coder"})
    data = await _ipc_request(sock, "POST", "/tasks", payload)
    assert "error" in data
    assert "invalid delegation" in data["error"]


async def test_not_found(ipc_server):
    sock, _, _, _ = ipc_server
    data = await _ipc_request(sock, "GET", "/nope")
    assert "error" in data


async def test_wake_sets_agent_event(ipc_server):
    sock, _, _, wake_events = ipc_server
    payload = json.dumps({"agent": "curator", "reason": "test"})
    data = await _ipc_request(sock, "POST", "/wake", payload)
    assert data == {"ok": True, "agent": "curator"}
    assert wake_events["curator"].is_set()
