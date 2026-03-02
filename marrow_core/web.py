"""Minimal web UI for task submission — zero-dependency async HTTP server.

Runs as a background asyncio task alongside the heartbeat loop.
Provides a single-page form to submit tasks into the queue directory.
"""

from __future__ import annotations

import asyncio
import contextlib
import html
import time
from pathlib import Path
from urllib.parse import unquote_plus

from loguru import logger

_HTML_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>marrow — submit task</title>
<style>
*{box-sizing:border-box}
body{font-family:system-ui,sans-serif;max-width:540px;margin:40px auto;
padding:0 20px;background:#fafafa;color:#333}
h1{font-size:1.3em}
form{background:#fff;padding:20px;border-radius:8px;
box-shadow:0 1px 3px rgba(0,0,0,.12)}
label{display:block;margin-bottom:4px;font-weight:600;font-size:.9em}
input,textarea{width:100%;padding:8px;margin-bottom:14px;
border:1px solid #ddd;border-radius:4px;font-size:.95em}
textarea{min-height:100px;resize:vertical}
button{background:#2563eb;color:#fff;border:none;padding:10px 20px;
border-radius:4px;cursor:pointer;font-size:.95em}
button:hover{background:#1d4ed8}
.msg{padding:10px;margin-bottom:14px;border-radius:4px;font-size:.9em}
.ok{background:#dcfce7;color:#166534}
.err{background:#fef2f2;color:#991b1b}
</style>
</head>
<body>
<h1>🦴 marrow — submit task</h1>
{message}
<form method="POST" action="/submit">
<label for="title">Title</label>
<input id="title" name="title" required placeholder="e.g. refactor logging module">
<label for="body">Description</label>
<textarea id="body" name="body" placeholder="Details (optional)"></textarea>
<button type="submit">Submit</button>
</form>
</body>
</html>"""


def _render(message: str = "") -> str:
    return _HTML_PAGE.replace("{message}", message)


def _parse_form(raw: str) -> dict[str, str]:
    """Parse application/x-www-form-urlencoded body."""
    fields: dict[str, str] = {}
    for pair in raw.split("&"):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        fields[unquote_plus(k)] = unquote_plus(v)
    return fields


def _create_task_file(task_dir: Path, title: str, body: str) -> Path:
    """Write a task markdown file into the queue directory."""
    task_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_ " else "" for c in title)[:50].strip()
    safe = safe.replace(" ", "-") or "task"
    path = task_dir / f"{ts}-{safe}.md"
    content = f"# {title}\n\n{body}\n" if body else f"# {title}\n"
    path.write_text(content, encoding="utf-8")
    return path


_STATUS_TEXT = {
    200: "OK",
    400: "Bad Request",
    404: "Not Found",
    500: "Internal Server Error",
}


def _send(writer: asyncio.StreamWriter, status: int, ctype: str, body: str) -> None:
    """Write a complete HTTP/1.1 response and close."""
    reason = _STATUS_TEXT.get(status, "OK")
    payload = body.encode()
    writer.write(
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {ctype}; charset=utf-8\r\n"
        f"Content-Length: {len(payload)}\r\n"
        f"Connection: close\r\n"
        f"\r\n".encode()
        + payload
    )


async def _handle(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    task_dir: Path,
) -> None:
    """Handle one HTTP request."""
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

        # Routes
        if method == "GET" and path == "/":
            _send(writer, 200, "text/html", _render())
        elif method == "POST" and path == "/submit":
            raw = ""
            if content_length > 0:
                data = await asyncio.wait_for(
                    reader.readexactly(content_length), timeout=10
                )
                raw = data.decode("utf-8", errors="replace")
            fields = _parse_form(raw)
            title = fields.get("title", "").strip()
            if not title:
                msg = '<div class="msg err">Title is required.</div>'
                _send(writer, 400, "text/html", _render(msg))
            else:
                body = fields.get("body", "").strip()
                fp = _create_task_file(task_dir, title, body)
                logger.info("task submitted via web: {}", fp.name)
                escaped = html.escape(title)
                _send(
                    writer,
                    200,
                    "text/html",
                    _render(f'<div class="msg ok">✅ Task submitted: {escaped}</div>'),
                )
        elif method == "GET" and path == "/health":
            _send(writer, 200, "application/json", '{"status":"ok"}')
        else:
            _send(writer, 404, "text/plain", "Not Found")
    except (TimeoutError, ConnectionError):
        pass  # Idle/broken connections — expected with keep-alive browsers
    except Exception as exc:
        logger.warning("web request error: {}", exc)
        with contextlib.suppress(Exception):
            _send(writer, 500, "text/plain", "Internal Server Error")
    finally:
        with contextlib.suppress(Exception):
            writer.close()
            await writer.wait_closed()


async def start_web_server(
    task_dir: str,
    host: str = "127.0.0.1",
    port: int = 8321,
) -> asyncio.Server:
    """Start the minimal web server and return the asyncio.Server handle."""
    td = Path(task_dir)

    async def handler(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        await _handle(r, w, td)

    server = await asyncio.start_server(handler, host, port)
    logger.info("web UI listening on http://{}:{}", host, port)
    return server
