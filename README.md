# marrow-core

Minimal self-evolving agent scheduler with hard isolation between the **core** (human-maintained) and **agent evolution** (agent-maintained).

## Design

```
/opt/marrow-core/      # root-owned — immutable to the agent
/Users/marrow/         # agent-owned — the agent evolves here freely
```

The agent cannot modify core. If it wants a core change it writes a proposal to `tasks/queue/core-proposal-*.md` and a human reviews it.

## Autonomous + specialist agent model

| Tier | Agent | Category | Purpose |
|------|-------|----------|---------|
| strategic | **refit** | Autonomous | Goal setting, system improvement, meta-learning |
| operational | **conductor** | Autonomous | Plan work, dispatch specialists, integrate results |
| specialist | **scout** | Autonomous + Subagent | Exploration, information gathering, quick reconnaissance |
| specialist | **reviewer** | Subagent | PR review, CI triage, issue/PR responses |
| routine | **watchdog** | Subagent | Monitoring, health checks, safe recovery actions |

## CLI

```
marrow run          # persistent heartbeat loop
marrow run-once     # one tick per agent then exit
marrow dry-run      # print assembled prompts, don't run agents
marrow setup        # init workspace dirs and sync agent symlinks
marrow validate     # check config and show summary
marrow doctor       # verify workspace, context dirs, and agent command availability
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
heartbeat_interval = 300
heartbeat_timeout  = 500
agent_command      = "opencode run --agent scout"
workspace          = "/Users/marrow"
context_dirs       = ["/Users/marrow/context.d"]

[[agents]]
name              = "conductor"
heartbeat_interval = 14400     # 4 hours
heartbeat_timeout  = 7200
agent_command      = "opencode run --agent conductor"
workspace          = "/Users/marrow"
context_dirs       = ["/Users/marrow/context.d"]

[[agents]]
name              = "refit"
heartbeat_interval = 302400    # 3.5 days
heartbeat_timeout  = 28800
agent_command      = "opencode run --agent refit"
workspace          = "/Users/marrow"
context_dirs       = ["/Users/marrow/context.d"]
```

Model tiers are defined in [`roles.toml`](roles.toml):

```toml
[targets.opencode.model_map]
strategic   = "github-copilot/claude-opus-4.6"
operational = "github-copilot/gpt-5.4"
specialist  = "github-copilot/gpt-5.4"
routine     = "github-copilot/gpt-5-mini"
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
