# marrow-core

Minimal self-evolving agent scheduler with hard isolation between the **core** (human-maintained) and **agent evolution** (agent-maintained).

## Design

```
/opt/marrow-core/      # root-owned — immutable to the agent
/Users/marrow/         # agent-owned — the agent evolves here freely
```

The agent cannot modify core. If it wants a core change it writes a proposal to `tasks/queue/core-proposal-*.md` and a human reviews it.

## Two-tier agent model

| Agent | Interval | Purpose |
|-------|----------|---------|
| **scout** | 5 min | Fast dispatcher — scan queue, do trivial work, delegate complex tasks |
| **artisan** | ~2.4 h | Deep worker — pick highest-value task, complete end-to-end with checkpoints |

## CLI

```
marrow run          # persistent heartbeat loop
marrow run-once     # one tick per agent then exit
marrow dry-run      # print assembled prompts, don't run agents
marrow setup        # init workspace dirs and sync agent symlinks
marrow validate     # check config and show summary
```

Options available on `run`, `run-once`, and `dry-run`:

```
--config / -c   PATH   Path to marrow.toml  [default: marrow.toml]
--verbose / -v         Enable debug logging
--json-logs            Emit newline-delimited JSON log records
--ipc / --no-ipc       Override IPC server flag from config
```

## Background daemon

Run marrow as a persistent background service that survives reboots:

```bash
# Install and start (macOS: launchd, Linux: systemd)
marrow daemon install --config /path/to/marrow.toml

# Check status
marrow daemon status

# Stop and remove
marrow daemon uninstall
```

**macOS** — writes `~/Library/LaunchAgents/com.marrow.heartbeat.plist` and loads it via
`launchctl`. Logs go to `~/Library/Logs/marrow/`.

**Linux** — writes `~/.config/systemd/user/marrow.service` and enables it via
`systemctl --user`. Logs are available via `journalctl --user -u marrow`.

## IPC server

Enable the IPC server to submit and list tasks without editing files directly:

```toml
# marrow.toml
[ipc]
enabled = true
# socket_path = "/Users/marrow/runtime/marrow.sock"  # optional override
# task_dir    = "/Users/marrow/tasks/queue"           # optional override
```

Once the server is running:

```bash
# Submit a new task
marrow task add "Fix the login bug" --body "Users can't log in on mobile"

# List queued tasks
marrow task list

# Query heartbeat status
marrow status
```

You can also use curl directly (no marrow CLI needed):

```bash
sock="/Users/marrow/runtime/marrow.sock"

# Health check
curl --unix-socket "$sock" http://localhost/health

# Submit task
curl --unix-socket "$sock" -X POST http://localhost/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title": "Investigate memory leak", "body": "OOM in prod since v1.3"}'

# List tasks
curl --unix-socket "$sock" http://localhost/tasks
```

## Installation

```bash
uv tool install marrow-core
# or inside a project:
uv add marrow-core
```

## Configuration

```toml
# marrow.toml
core_dir = "/opt/marrow-core"

[[agents]]
name              = "scout"
heartbeat_interval = 300       # seconds
heartbeat_timeout  = 300
agent_command      = "opencode run --agent scout"
workspace          = "/Users/marrow"
context_dirs       = ["/Users/marrow/context.d"]

[[agents]]
name              = "artisan"
heartbeat_interval = 8640      # ~2.4 hours
heartbeat_timeout  = 8000
agent_command      = "opencode run --agent artisan"
workspace          = "/Users/marrow"
context_dirs       = ["/Users/marrow/context.d"]

# Optional: Unix domain socket IPC server
[ipc]
enabled     = true
socket_path = "/Users/marrow/runtime/marrow.sock"
task_dir    = "/Users/marrow/tasks/queue"
```

## Context providers

Any executable script inside a `context_dirs` directory is run each tick. Its stdout is appended verbatim to the agent prompt. No JSON protocol — plain text.

```
/Users/marrow/context.d/
├── 00_queue.py     # reads tasks/queue/ and prints a summary
└── 10_explore.py   # fallback when no tasks are queued
```

The agent is free to add, edit, or remove scripts under its own `context.d/`.

## Architecture

See [AGENTS.md](AGENTS.md) for a full breakdown.

## License

MIT
