# marrow-core

Minimal self-evolving agent scheduler with hard isolation between the immutable core and the writable agent workspace.

## Prompt model

Use one mental model everywhere:

- `rules` -> stable global policy in `prompts/rules.md`
- `roles` -> per-agent identity and delegation boundaries in `roles/`
- `context providers` -> current queue/state/environment facts from `context.d/`
- `skills` -> reusable procedures; not part of repo prompt assembly

Repo-root `agents/` is retired. Do not add new prompt material there.

## Hierarchy

marrow-core uses an explicit three-level hierarchy. Levels are expressed by folder structure and architecture docs, not encoded into runtime-facing role names.

| Level | Directory | Roles | Responsibility |
|------|-----------|-------|----------------|
| `L1` | `roles/l1/` | `scout`, `conductor`, `refit` | scheduled monitoring, operational ownership, strategic closure |
| `L2` | `roles/l2/` | `refactor-lead`, `prototype-lead`, `review-lead`, `ops-lead` | bounded domain ownership with downward delegation |
| `L3` | `roles/l3/` | `analyst`, `researcher`, `coder`, `tester`, `writer`, `git-ops`, `filer` | tightly scoped execution with no further delegation |

Delegation policy:

- `L1 -> L2/L3` allowed
- `L2 -> L3` allowed where declared
- `L3 -> *` forbidden
- no upward calls
- one accountable owner per workstream
- max delegation depth: 2 hops

## Canonical role layer

The canonical source of truth is now `roles/` plus `roles.toml`.

- `roles/` stores hierarchy-aware role definitions
- `roles.toml` stores model-tier mapping and hierarchy metadata
- `.opencode/agents/` is the synced runtime surface used by the agent runtime

## CLI

```text
marrow run              # persistent heartbeat loop
marrow run-once         # one tick per scheduled main, then exit
marrow dry-run          # assemble prompts without running agents
marrow setup            # init workspace dirs and sync role symlinks
marrow scaffold         # create a new writable workspace skeleton and starter config
marrow validate         # check config and show summary
marrow doctor           # verify workspace, context dirs, and agent command availability
marrow status           # query live heartbeat state over IPC
marrow install-service  # render launchd or systemd service files
marrow task add         # submit a task into tasks/queue via IPC
marrow task list        # inspect queued tasks via IPC
```

## Configuration

```toml
core_dir = "/opt/marrow-core"

[ipc]
enabled = true

[[agents]]
name = "scout"
heartbeat_interval = 300
heartbeat_timeout = 500
workspace = "/Users/marrow"
agent_command = "/Users/marrow/.opencode/bin/opencode run --agent scout"
context_dirs = ["/Users/marrow/context.d"]

[[agents]]
name = "conductor"
heartbeat_interval = 7200
heartbeat_timeout = 7200
workspace = "/Users/marrow"
agent_command = "/Users/marrow/.opencode/bin/opencode run --agent conductor"
context_dirs = ["/Users/marrow/context.d"]

[[agents]]
name = "refit"
heartbeat_interval = 302400
heartbeat_timeout = 28800
workspace = "/Users/marrow"
agent_command = "/Users/marrow/.opencode/bin/opencode run --agent refit"
context_dirs = ["/Users/marrow/context.d"]
```

Model tiers and hierarchy metadata live in `roles.toml`.

## Runtime boundaries

- `marrow_core/contracts.py` — canonical hierarchy, delegation, and workspace topology
- `marrow_core/prompting.py` — context execution and prompt assembly
- `marrow_core/runtime.py` — socket, queue, and binary path resolution
- `marrow_core/task_queue.py` — filesystem queue helpers
- `marrow_core/services.py` — launchd/systemd rendering
- `marrow_core/scaffold.py` — workspace scaffold and starter config generation
- `marrow_core/heartbeat.py`, `marrow_core/cli.py`, `marrow_core/ipc.py` — orchestration layers

## Filesystem handoffs

```text
runtime/handoff/scout-to-conductor/
runtime/handoff/conductor-to-scout/
runtime/handoff/scout-to-human/
```

## Service installation

```bash
marrow install-service --config marrow.toml --platform darwin --output-dir ./service-out
marrow install-service --config marrow.toml --platform linux --output-dir ./service-out
```

The repo ships both launchd plists and systemd unit templates, all rendered from the same runtime model.

## Upstream coordination

See `docs/agent-caster-priority-needs.md` for the high-priority `agent-caster` capabilities marrow-core needs next, with full issue text for:

- `agent-caster#18`
- `agent-caster#19`
- `agent-caster#20`

## Architecture

See `AGENTS.md` for the full contract and filesystem model.
