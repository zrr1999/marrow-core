# marrow-core Architecture

## Overview

marrow-core is a minimal self-evolving agent scheduler with hard
core/evolution isolation. The agent (user `marrow`) can evolve its own
behavior within its workspace, but can never modify the core.

## Design Principles

1. **Hard isolation** — Core is root-owned at `/opt/marrow-core/`. Agent
   workspace is at `/Users/marrow/`. Filesystem permissions enforce the boundary.
2. **Simplicity** — ~550 lines of core Python. No JSON plugin protocol,
   no Pydantic extra magic. Context scripts output plain text to stdout.
3. **Filesystem-as-API** — Tasks, handoffs, state, checkpoints are all
   just files. No database, no queue service.
4. **Symlink-based immutability** — Base agent definitions are symlinked
   from core into the agent's `.opencode/agents/`. The agent can see
   them but cannot modify the symlink targets (root-owned).

## Six-Agent Model

```
                      ┌──────────────────┐
                      │   marrow-core    │
                      │   (heartbeat)    │
                      └─┬──┬──┬──┬──┬──┬┘
                        │  │  │  │  │  │
           every 2m ────┘  │  │  │  │  └──── every 6h (+ on-demand)
                           │  │  │  │
           every 5m ───────┘  │  │  └──────── every 15m
                              │  │
                         every 4h └────────── weekly (+ on-demand)
                              │
       ┌──────────┐    ┌──────▼────┐    ┌───────────┐
       │ watchdog │    │  artisan  │    │ reviewer  │
       │  (infra) │    │  (deep)   │    │  (github) │
       └──────────┘    └──────┬────┘    └───────────┘
                              │ spawns (on-demand)
       ┌──────────┐    ┌──────┴────┐    ┌───────────┐
       │  scout   │◄───┤  handoff  ├───►│  analyst  │
       │  (fast)  │    │  files    │    │ (research)│
       └──────────┘    └───────────┘    └───────────┘
                             ▲
                      ┌──────┴────┐
                      │   refit   │
                      │ (meta-AI) │
                      └───────────┘
```

### Agent Roles

| Agent | Interval | Model | Purpose |
|-------|----------|-------|---------|
| **watchdog** | 2 min | gpt-5-mini | Infrastructure health; restart crashed services; alert humans |
| **scout** | 5 min | gpt-5-mini | Fast dispatcher; scan queue; do trivial tasks; delegate complex |
| **reviewer** | 15 min | gpt-5-mini | GitHub triage; read PR diffs; write review comments; reply to issues |
| **artisan** | 4 h | claude-sonnet-4.6 | Deep worker; end-to-end task completion with checkpoints; spawns subagents |
| **analyst** | 6 h (+ on-demand) | claude-sonnet-4.6 | Research; paper digests; repo exploration; structured summaries |
| **refit** | weekly (+ on-demand) | claude-opus-4.6 | Meta-learning; review performance; propose prompt/workflow improvements |

### Interaction Patterns

- **scout** delegates complex work → `runtime/handoff/scout-to-artisan/`
- **artisan** offloads quick checks → `runtime/handoff/artisan-to-scout/`
- **artisan** spawns **analyst** on-demand for focused research subtasks
- **reviewer** queues implementation tasks → `tasks/queue/` for artisan
- **analyst** queues follow-up actions → `tasks/queue/` for artisan/scout
- **watchdog** alerts humans → `runtime/handoff/scout-to-human/`
- **refit** analyzes all agent outputs and writes proposals → `tasks/queue/core-proposal-*.md`
- All agents read `tasks/queue/` for new work
- Human responds → `tasks/queue/` (new task) or `runtime/handoff/human-to-scout/`

### On-demand Sub-agent Pattern

Artisan can spawn Analyst as a focused subagent for parallel research work:

1. Artisan writes a self-contained task spec (≤200 words) to `tasks/parallel/<id>/task.md`
2. Analyst picks it up, works in isolation (fresh context), writes result to
   `tasks/parallel/<id>/result.json`
3. Artisan polls for completion and merges the result

This enables parallel decomposition: Artisan implements while Analyst researches,
reducing total session time for complex multi-faceted tasks.

### Persistent TODO Queue

Artisan maintains a persistent TODO queue at `runtime/state/artisan-todo.json`.
Items survive session boundaries — incomplete tasks are resumed in the next session.
This enables reliable multi-session execution of large tasks.

## Heartbeat Cycle

1. **Gather context** — Run executable scripts in `context_dirs`.
   Each script outputs plain text to stdout. No JSON protocol needed.
2. **Build prompt** — Stack: core rules + base prompt + context blocks.
3. **Run agent** — Execute `agent_command` with the assembled prompt.
4. **Sleep** — Wait for `heartbeat_interval`, repeat.

## Filesystem Layout

```
/opt/marrow-core/           # ROOT-OWNED (immutable to agent)
├── marrow_core/            # Python package
│   ├── config.py           # TOML config + Pydantic validation
│   ├── heartbeat.py        # Core scheduler loop
│   ├── runner.py           # Agent subprocess execution
│   ├── sandbox.py          # Permission enforcement + symlinks
│   ├── log.py              # Structured logging
│   └── cli.py              # CLI: run, run-once, dry-run, setup, validate
├── agents/                 # Base agent definitions (symlinked to workspace)
│   ├── scout.md
│   └── artisan.md
├── prompts/
│   └── rules.md            # Immutable rules injected into every prompt
├── context.d/              # Default context providers (copied to workspace)
├── marrow.toml             # Agent configuration
├── lib.sh                  # Shared shell functions
└── setup.sh / sync.sh      # Deployment scripts

/Users/marrow/              # AGENT-OWNED (agent can modify freely)
├── .opencode/agents/       # scout.md, artisan.md (symlinks) + custom-*.md
├── context.d/              # Agent-owned context scripts
├── tasks/                  # queue/ -> delegated/ -> done/
├── runtime/                # state/, handoff/, checkpoints/, logs/
└── workspace/              # Agent's working area
```

## Evolution Protocol

The agent is encouraged to evolve within its boundary:

| What | Where | How |
|------|-------|-----|
| New agents | `.opencode/agents/custom-*.md` | Create new files |
| Context scripts | `context.d/` | Create/modify scripts |
| Skills | Anywhere in workspace | Standard opencode skills |
| Core changes | `tasks/queue/core-proposal-*.md` | Write proposal, human reviews |

## CLI Commands

| Command    | Description |
|-----------|-------------|
| `run`      | Persistent heartbeat loop |
| `run-once` | One tick per agent, then exit |
| `dry-run`  | Build prompts without running agents |
| `setup`    | Initialize workspace and sync symlinks |
| `validate` | Check config and show summary |

## Configuration

See `marrow.toml`. Key fields per agent:

- `name` — Unique identifier (scout, artisan)
- `heartbeat_interval` — Seconds between ticks
- `heartbeat_timeout` — Max seconds per agent execution
- `workspace` — Agent's writable workspace root
- `agent_command` — Command to invoke the agent
- `context_dirs` — Directories to scan for context scripts

## Commit & PR Conventions

This project uses **gitmoji** for commit messages and PR titles.

### Commit message format

```
<gitmoji> <type>: <description>
```

| Gitmoji | Type | When to use |
|---------|------|-------------|
| 🎉 | `init` | Initial commit / project scaffolding |
| ✨ | `feat` | New feature or capability |
| 🐛 | `fix` | Bug fix |
| 📝 | `docs` | Documentation only |
| ♻️ | `refactor` | Code refactoring (no behavior change) |
| 🔧 | `chore` | Config, tooling, or maintenance |
| ✅ | `test` | Add or update tests |
| 🔥 | `remove` | Remove code or files |
| 🎨 | `style` | Code style / formatting |
| 🚀 | `deploy` | Deployment related changes |

**Examples:**

```
✨ feat: add checkpoint auto-pruning for artisan
🐛 fix: use loguru {} format instead of stdlib % format
📝 docs: update AGENTS.md with commit conventions
```

### PR title format

PR titles follow the same gitmoji format:

```
✨ feat: add checkpoint auto-pruning for artisan
```

## Comparison with marrow-core

| Aspect | marrow-core | marrow-core |
|--------|-------------|-------------|
| Plugin protocol | JSON stdin/stdout | Plain text stdout |
| Agent definitions | Inside core repo | Symlinked from core |
| Permission boundary | Convention only | Filesystem enforced |
| Core lines | ~800 | ~550 |
| Config keys per agent | 9 | 6 |
| Evolution | Unrestricted | Bounded by workspace |
