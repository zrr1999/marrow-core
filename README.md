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

Options available on every command:

```
--config / -c   PATH   Path to marrow.toml  [default: marrow.toml]
--verbose / -v         Enable debug logging
--json-logs            Emit newline-delimited JSON log records
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
opencode_url       = "http://localhost:4096"   # opencode serve mode (preferred)
workspace          = "/Users/marrow"
context_dirs       = ["/Users/marrow/context.d"]

[[agents]]
name              = "artisan"
heartbeat_interval = 8640      # ~2.4 hours
heartbeat_timeout  = 8000
agent_command      = "opencode run --agent artisan"
opencode_url       = "http://localhost:4096"   # opencode serve mode (preferred)
workspace          = "/Users/marrow"
context_dirs       = ["/Users/marrow/context.d"]
```

### Execution modes

marrow-core supports two modes for running opencode agents:

| Mode | Config | Description |
|------|--------|-------------|
| **Serve (HTTP)** | `opencode_url = "http://localhost:4096"` | Preferred. Talks to a running `opencode serve` instance via HTTP API. |
| **Subprocess** | `agent_command = "opencode run --agent scout"` | Fallback. Spawns opencode as a subprocess each tick. |

When `opencode_url` is set, the HTTP mode is used and `agent_command` is ignored.

To start the opencode server:

```bash
opencode serve --hostname 127.0.0.1 --port 4096
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
