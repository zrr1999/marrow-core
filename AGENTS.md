# marrow-core Architecture

## Overview

marrow-core is a minimal scheduler for an autonomous agent system with one scheduled top-level orchestrator by default and layered delegated execution beneath it. The human-maintained core stays immutable under `/opt/marrow-core/`; the running agent works inside `/Users/marrow/`.

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
- `roles.toml` for model-tier metadata
- `marrow_core/contracts.py` for runtime inventory and workspace topology rules
- `role-forge` for casting canonical `roles/` into runtime tool configs

## Role layout

Directory layout is an architecture aid, not runtime-enforced metadata.

### top-level scheduled orchestrators — `roles/`

| Role | Purpose | Can delegate to |
|------|---------|-----------------|
| `curator` | orchestration, repair, backlog shaping, multi-round closure | `stewards` |

### stewards — `roles/stewards/`

| Role | Domain | Can delegate to |
|------|--------|-----------------|
| `conductor` | delivery workstream ownership, integration, closure | `leaders`, exceptional direct `experts` |
| `repo-steward` | GitHub lifecycle, CI follow-through, permission-change workflow | `leaders`, `experts` |

### leaders — `roles/leaders/`

| Role | Domain | Can delegate to |
|------|--------|-----------------|
| `refactor-lead` | refactors, migrations, architecture change | `experts` |
| `prototype-lead` | PoCs, experiments, exploratory builds | `experts` |
| `review-lead` | PR/CI/review synthesis | `experts` |
| `ops-lead` | CI, deployment, service, environment orchestration | `experts` |

### experts — `roles/experts/`

`analyst`, `researcher`, `coder`, `tester`, `writer`, `git-ops`, `filer`

Experts never delegate further.

## Delegation policy

These are prompt-level operating rules, not runtime-enforced hierarchy metadata.

- `curator -> stewards`
- `stewards -> leaders`
- `leaders -> experts`
- `experts -> *` forbidden
- upward calls forbidden
- one accountable owner per workstream
- delegation depth capped at 3 hops

## Runtime boundaries

- `marrow_core/contracts.py` — role inventory and workspace topology
- `marrow_core/prompting.py` — context execution and prompt assembly
- `marrow_core/runtime.py` — socket, queue, binary path resolution
- `marrow_core/task_queue.py` — filesystem queue read/write helpers
- `marrow_core/health.py` — doctor and self-check health checks
- `marrow_core/services.py` — launchd/systemd rendering
- `marrow_core/scaffold.py` — workspace scaffold and starter config generation
- `marrow_core/heartbeat.py` — scheduled orchestration per configured top-level agent
- `marrow_core/ipc.py` — local control plane over Unix socket
- `marrow_core/cli.py` — user-facing command surface

## Filesystem layout

```text
/opt/marrow-core/
├── marrow_core/
├── roles/
│ ├── experts/
│ ├── leaders/
│ ├── stewards/
│ └── curator.md
├── prompts/
├── context.d/
├── roles.toml
├── marrow.toml
├── lib.sh
└── setup.sh

/Users/marrow/
├── .opencode/agents/       # cast runtime role files + custom-*.md
├── context.d/
├── tasks/
│ ├── queue/
│ ├── delegated/
│ └── done/
├── runtime/
│ ├── state/
│ ├── checkpoints/
│ └── logs/
└── docs/
```

## CLI surface

| Command | Purpose |
|---------|---------|
| `run` | persistent heartbeat loop |
| `run-once` | one tick per configured scheduled agent |
| `dry-run` | prompt assembly without execution |
| `sync-once` | one bounded sync attempt with structured result |
| `setup` | workspace init and role sync |
| `scaffold` | create workspace skeleton and starter config |
| `validate` | config summary and schema validation |
| `doctor` | workspace/context/command availability checks |
| `status` | heartbeat state via IPC |
| `wake` | wake a configured agent via IPC |
| `install-service` | render launchd/systemd service files |
| `task add` | submit a queued task over IPC |
| `task list` | inspect queued tasks over IPC |

## Service model

- macOS: `com.marrow.heart.plist`
- Linux: `marrow-heart.service`
- `marrow run` is either the single-user heartbeat process or the root supervisor service
- supervisor mode keeps one long-running service and spawns per-user workers directly instead of rendering extra worker units
- CLI-managed periodic sync stays inside `marrow run` by invoking `sync-once` in a subprocess
- core-owned self-check can wake `curator` early with a repair task when doctor-style checks fail
- all rendered from the same runtime model so PATH, config path, and log destinations stay aligned

## Testing guidance

- prefer one high-signal behavior test over multiple helper tests for the same failure mode
- keep supervisor boundary coverage concentrated in `tests/test_supervisor.py`
- keep single-user compatibility coverage in the narrower module test files
- add lower-level tests only when a helper has meaningful branching not already covered by a higher-level test

## Quick start

Fresh install:

```bash
git clone https://github.com/zrr1999/marrow-core.git /opt/marrow-core
cd /opt/marrow-core
sudo ./setup.sh
```

Manual update attempt:

```bash
cd /opt/marrow-core
python -m marrow_core.cli sync-once --config marrow.toml
```

Expected sync outcomes:

- `0` -> `noop`
- `10` -> `reloaded`
- `11` -> `restart_required`
- `1` -> `failed`
