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

## Three Autonomous Agents + Delegated Sub-agents

```
marrow-core heartbeat (scheduler)
│
├── 5 min ──► scout        monitor queue/state/services; scan notifications; create handoffs
├── 2 h ────► conductor    plan work; dispatch specialists; validate/integrate
└── 3.5 day ► refit        strategic review; meta-learning; system improvements
                           (scheduled only — not callable by other agents)

On-demand sub-agents:
  conductor/refit ──task──► scout     focused monitoring / scanning / status gathering
  conductor/refit ──task──► reviewer  GitHub triage; PR reviews; issue replies

Data flows (all via filesystem):
  scout ──handoff────► conductor     runtime/handoff/scout-to-conductor/
  conductor ──follow-up──► scout     runtime/handoff/conductor-to-scout/
  scout ──alert────► human           runtime/handoff/scout-to-human/
  refit ──coordinate──► sub-agents   task tool (parallel lower-level workers)
  refit ──propose────► human         tasks/queue/core-proposal-*.md
  human ──task──────► autonomous     tasks/queue/
```

### Agent Roles

| Tier | Agent | Category | Model | Role |
|------|-------|----------|-------|------|
| `strategic` | **refit** | Autonomous | claude-opus-4.6 | Goal setting, system improvement, meta-learning |
| `operational` | **conductor** | Autonomous | gpt-5.4 | Task decomposition, specialist dispatch, result integration |
| `routine` | **scout** | Autonomous + Subagent | gpt-5-mini | Monitoring, scanning, notifications, safe recovery actions |
| `specialist` | **reviewer** | Subagent | gpt-5.4 | GitHub triage, PR reviews, CI inspection |

### Model map (`roles.toml`)

```toml
[targets.opencode.model_map]
strategic   = "github-copilot/claude-opus-4.6"
operational = "github-copilot/gpt-5.4"
specialist  = "github-copilot/gpt-5.4"
routine     = "github-copilot/gpt-5-mini"
```

### Persistent TODO Queue

Conductor maintains a persistent TODO queue at `runtime/state/conductor-todo.json`.
Items survive session boundaries — incomplete tasks are resumed in the next session.
This enables reliable multi-session execution of large tasks.

## Heartbeat Cycle

1. **Gather context** — Run executable scripts in `context_dirs`.
   Each script outputs plain text to stdout. No JSON protocol needed.
2. **Build prompt** — Stack: core rules + base prompt + context blocks.
3. **Run agent** — Execute `agent_command` with the assembled prompt.
4. **Sleep** — Wait for `heartbeat_interval`, repeat.

## Runtime Boundaries

- `marrow_core/prompting.py` — context execution and prompt assembly
- `marrow_core/runtime.py` — canonical socket, queue, and binary path resolution
- `marrow_core/task_queue.py` — filesystem task queue read/write helpers
- `marrow_core/services.py` — launchd/systemd rendering
- `marrow_core/scaffold.py` — workspace scaffold and starter config generation
- `marrow_core/heartbeat.py` / `marrow_core/cli.py` / `marrow_core/ipc.py` — orchestration layers that compose those helpers

## Filesystem Layout

```
/opt/marrow-core/           # ROOT-OWNED (immutable to agent)
├── marrow_core/            # Python package
│   ├── config.py           # TOML config + Pydantic validation
│   ├── contracts.py        # Canonical topology and role model
│   ├── heartbeat.py        # Core scheduler loop
│   ├── prompting.py        # Context execution + prompt assembly
│   ├── runtime.py          # Canonical runtime paths
│   ├── task_queue.py       # Filesystem queue helpers
│   ├── scaffold.py         # Workspace/config scaffolding
│   ├── services.py         # launchd/systemd rendering
│   ├── runner.py           # Agent subprocess execution
│   ├── workspace.py        # Permission enforcement + symlinks
│   ├── log.py              # Structured logging
│   ├── ipc.py              # Local control plane over Unix socket
│   └── cli.py              # CLI: run, status, task, scaffold, service install
├── agents/                 # Base agent definitions (symlinked to workspace)
│   ├── scout.md
│   ├── conductor.md
│   ├── refit.md
│   ├── reviewer.md
│   └── analyst.md
├── prompts/
│   └── rules.md            # Immutable rules injected into every prompt
├── context.d/              # Default context providers (copied to workspace)
├── marrow.toml             # Agent configuration
├── lib.sh                  # Shared shell functions
└── setup.sh / sync.sh      # Deployment scripts

/Users/marrow/              # AGENT-OWNED (agent can modify freely)
├── .opencode/agents/       # scout.md, conductor.md, ... (symlinks) + custom-*.md
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
| `scaffold` | Create a workspace skeleton and starter config |
| `validate` | Check config and show summary |
| `doctor`   | Verify workspace, context dirs, and agent command availability |
| `status`   | Query live heartbeat state over IPC |
| `install-service` | Render launchd or systemd service files |
| `task add` | Submit a queued task over IPC |
| `task list`| List queued tasks over IPC |

## Configuration

See `marrow.toml`. Key fields per agent:

- `name` — Unique identifier (scout, conductor, refit)
- `heartbeat_interval` — Seconds between ticks
- `heartbeat_timeout` — Max seconds per agent execution
- `workspace` — Agent's writable workspace root
- `agent_command` — Command to invoke the agent
- `context_dirs` — Directories to scan for context scripts

## Service Model

- macOS uses `com.marrow.heart.plist` and `com.marrow.heart.sync.plist`
- Linux uses `marrow-heart.service`, `marrow-heart-sync.service`, and `marrow-heart-sync.timer`
- Both are rendered from the same CLI/runtime model so PATH, binary path, config path, and log destinations stay aligned

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
✨ feat: add checkpoint auto-pruning for conductor
🐛 fix: use loguru {} format instead of stdlib % format
📝 docs: update AGENTS.md with commit conventions
```

### PR title format

PR titles follow the same gitmoji format:

```
✨ feat: add checkpoint auto-pruning for conductor
```
