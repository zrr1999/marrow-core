# marrow-core Architecture

## Overview

marrow-core is a minimal scheduler for a hierarchy-aware autonomous agent system.
The human-maintained core stays immutable under `/opt/marrow-core/`; the running
agent works inside `/Users/marrow/`.

## Prompt layers

Keep these concepts separate:

- `prompts/rules.md` -> stable global policy
- `roles/` -> role identity and delegation boundaries
- `context.d/` -> dynamic facts only
- skills -> reusable procedures outside the repo prompt-layer contract

Repo-root `agents/` has been retired from the active prompt model.

## Canonical model

The canonical source of truth is:

- `roles/` for role definitions
- `roles.toml` for model-tier and hierarchy metadata
- `marrow_core/contracts.py` for runtime-enforced topology and delegation rules
- `agent-caster` for casting canonical `roles/` into runtime tool configs

## Hierarchy

Levels are expressed by directory layout and architecture policy, not by encoding `l1-`, `l2-`, or `l3-` into runtime-facing role names.

### `L1` scheduled mains — `roles/l1/`

| Role | Purpose | Can delegate to |
|------|---------|-----------------|
| `scout` | routine monitoring, scans, alerts, passive handoffs | none |
| `conductor` | operational planning, bounded delegation, integration | `L2`, `L3` |
| `refit` | strategic review, redesign, weekly closure | `L2`, `L3` |

### `L2` expert leads — `roles/l2/`

| Role | Domain | Can delegate to |
|------|--------|-----------------|
| `refactor-lead` | refactors, migrations, architecture change | selected `L3` |
| `prototype-lead` | PoCs, experiments, exploratory builds | selected `L3` |
| `review-lead` | PR/CI/review synthesis | selected `L3` |
| `ops-lead` | CI, deployment, service, environment orchestration | selected `L3` |

### `L3` leaf workers — `roles/l3/`

`analyst`, `researcher`, `coder`, `tester`, `writer`, `git-ops`, `filer`

Leaf workers never delegate further.

## Delegation policy

- `L1 -> L2/L3` allowed
- declared `L2 -> L3` allowed
- `L3 -> *` forbidden
- upward calls forbidden
- one accountable owner per workstream
- delegation depth capped at 2 hops

## Runtime boundaries

- `marrow_core/contracts.py` — hierarchy, delegation, workspace topology
- `marrow_core/prompting.py` — context execution and prompt assembly
- `marrow_core/runtime.py` — socket, queue, binary path resolution
- `marrow_core/task_queue.py` — filesystem queue read/write helpers
- `marrow_core/services.py` — launchd/systemd rendering
- `marrow_core/scaffold.py` — workspace scaffold and starter config generation
- `marrow_core/heartbeat.py` — scheduled orchestration per configured `L1` main
- `marrow_core/ipc.py` — local control plane over Unix socket
- `marrow_core/cli.py` — user-facing command surface

## Filesystem layout

```text
/opt/marrow-core/
├── marrow_core/
├── roles/
│   ├── l1/
│   ├── l2/
│   └── l3/
├── prompts/
├── context.d/
├── roles.toml
├── marrow.toml
├── lib.sh
├── setup.sh
└── sync.sh

/Users/marrow/
├── .opencode/agents/       # cast runtime role files + custom-*.md
├── context.d/
├── tasks/
├── runtime/
│   ├── state/
│   ├── handoff/
│   │   ├── scout-to-conductor/
│   │   ├── conductor-to-scout/
│   │   └── scout-to-human/
│   ├── checkpoints/
│   └── logs/
└── docs/
```

## CLI surface

| Command | Purpose |
|---------|---------|
| `run` | persistent heartbeat loop |
| `run-once` | one tick per configured `L1` main |
| `dry-run` | prompt assembly without execution |
| `setup` | workspace init and role sync |
| `scaffold` | create workspace skeleton and starter config |
| `validate` | config summary and schema validation |
| `doctor` | workspace/context/command availability checks |
| `status` | heartbeat state via IPC |
| `install-service` | render launchd/systemd service files |
| `task add` | submit a queued task over IPC |
| `task list` | inspect queued tasks over IPC |

## Service model

- macOS: `com.marrow.heart.plist`, `com.marrow.heart.sync.plist`
- Linux: `marrow-heart.service`, `marrow-heart-sync.service`, `marrow-heart-sync.timer`
- all rendered from the same runtime model so PATH, config path, and log destinations stay aligned
