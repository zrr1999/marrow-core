"""Tests for marrow_core.web."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from marrow_core.web import (
    _create_task_file,
    _parse_form,
    _render,
    start_web_server,
)


def test_render_default():
    html = _render()
    assert "marrow" in html
    assert "<form" in html
    assert "{message}" not in html


def test_render_with_message():
    html = _render('<div class="msg ok">Done</div>')
    assert "Done" in html
    assert "{message}" not in html


def test_parse_form_basic():
    fields = _parse_form("title=hello+world&body=some+text")
    assert fields["title"] == "hello world"
    assert fields["body"] == "some text"


def test_parse_form_encoded():
    fields = _parse_form("title=%E4%BD%A0%E5%A5%BD")
    assert fields["title"] == "你好"


def test_parse_form_empty():
    fields = _parse_form("")
    assert fields == {}


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
    assert content.count("\n") == 1  # just title + trailing newline


def test_create_task_file_sanitizes_name(tmp_path: Path):
    queue = tmp_path / "tasks" / "queue"
    fp = _create_task_file(queue, "fix: the <bug> & crash!", "")
    assert "<" not in fp.name
    assert ">" not in fp.name
    assert "&" not in fp.name


@pytest.fixture
async def web_server(tmp_path: Path):
    """Start the web server on a random port and yield (host, port, task_dir)."""
    task_dir = tmp_path / "tasks" / "queue"
    server = await start_web_server(str(task_dir), "127.0.0.1", 0)
    addr = server.sockets[0].getsockname()
    yield addr[0], addr[1], task_dir
    server.close()
    await server.wait_closed()


async def _http_request(host: str, port: int, request: str) -> str:
    """Send raw HTTP request and return the full response."""
    reader, writer = await asyncio.open_connection(host, port)
    writer.write(request.encode())
    await writer.drain()
    response = await asyncio.wait_for(reader.read(65536), timeout=5)
    writer.close()
    await writer.wait_closed()
    return response.decode("utf-8", errors="replace")


async def test_get_index(web_server):
    host, port, _ = web_server
    resp = await _http_request(host, port, "GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
    assert "200 OK" in resp
    assert "marrow" in resp
    assert "<form" in resp


async def test_post_submit(web_server):
    host, port, task_dir = web_server
    body = "title=test+task&body=description+here"
    req = (
        f"POST /submit HTTP/1.1\r\n"
        f"Host: localhost\r\n"
        f"Content-Type: application/x-www-form-urlencoded\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"\r\n"
        f"{body}"
    )
    resp = await _http_request(host, port, req)
    assert "200 OK" in resp
    assert "Task submitted" in resp
    # Verify task file was created
    files = list(task_dir.glob("*.md"))
    assert len(files) == 1
    assert "# test task" in files[0].read_text()


async def test_post_submit_empty_title(web_server):
    host, port, _ = web_server
    body = "title=&body=some+text"
    req = (
        f"POST /submit HTTP/1.1\r\n"
        f"Host: localhost\r\n"
        f"Content-Type: application/x-www-form-urlencoded\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"\r\n"
        f"{body}"
    )
    resp = await _http_request(host, port, req)
    assert "400 Bad Request" in resp
    assert "Title is required" in resp


async def test_health_endpoint(web_server):
    host, port, _ = web_server
    resp = await _http_request(host, port, "GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
    assert "200 OK" in resp
    assert '"ok"' in resp


async def test_not_found(web_server):
    host, port, _ = web_server
    resp = await _http_request(host, port, "GET /nope HTTP/1.1\r\nHost: localhost\r\n\r\n")
    assert "404" in resp
