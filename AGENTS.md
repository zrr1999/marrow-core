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

## Two-Tier Agent Model

```
              ┌──────────────────┐
              │   marrow-core    │
              │   (heartbeat)    │
              └──┬───────────┬───┘
                 │           │
        every 5m │           │ every ~2.4h
                 ▼           ▼
          ┌──────────┐ ┌───────────┐
          │  scout   │ │  artisan  │
          │  (fast)  │ │  (deep)   │
          └──────────┘ └───────────┘
                 │           ▲
                 │  handoff  │
                 └───────────┘
```

- **scout** — Fast dispatcher (~3 min). Scans queue, does trivial work,
  delegates complex tasks to artisan.
- **artisan** — Deep worker (up to 2 hours). Picks highest-value task,
  completes it end-to-end with checkpoints.

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
