# marrow-core Architecture

## Overview

marrow-core is a minimal scheduler for an autonomous agent system with one scheduled top-level orchestrator by default and layered delegated execution beneath it. The human-maintained core stays immutable under `/opt/marrow-core/`; the running agent works inside `/Users/marrow/`.

## Prompt layers

Keep these concepts separate:

- `prompts/rules.md` -> stable global policy
- `roles/` -> canonical role identity and delegation boundaries
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

```text
roles/
├── orchestrator.md
├── directors/
│   ├── craft.md
│   ├── forge.md
│   ├── mind.md
│   └── sentinel.md
├── leaders/
│   ├── builder.md
│   ├── shaper.md
│   ├── verifier.md
│   ├── courier.md
│   ├── herald.md
│   ├── archivist.md
│   ├── scout.md
│   ├── evolver.md
│   └── reviewer.md
└── specialists/
    ├── coder.md
    ├── tester.md
    ├── analyst.md
    ├── researcher.md
    ├── writer.md
    ├── filer.md
    └── git-ops.md
```

### top-level orchestrator

| Role | Purpose | Can delegate to |
|------|---------|-----------------|
| `orchestrator` | human communication, routing, output pacing, light acceptance | `directors` |

### directors

| Role | Domain | Can delegate to |
|------|--------|-----------------|
| `craft` | code construction and execution | `leaders` |
| `forge` | external-world read/write and outward delivery | `leaders` |
| `mind` | knowledge, exploration, memory, self-evolution | `leaders` |
| `sentinel` | validation, review coordination, gating | `leaders` |

### leaders

| Role | Domain | Can delegate to |
|------|--------|-----------------|
| `builder` | concrete implementation and integration | `specialists` |
| `shaper` | refactors, migrations, structural change | `specialists` |
| `verifier` | test execution, repro, runtime validation | `specialists` |
| `courier` | repository follow-through and external coordination | `specialists` |
| `herald` | outward broadcast and public updates | `specialists` |
| `archivist` | durable memory and internal artifacts | `specialists` |
| `scout` | exploration and reconnaissance | `specialists` |
| `evolver` | prompt, role, and workflow self-improvement | `specialists` |
| `reviewer` | static review and quality gates | `specialists` |

### specialists

`analyst`, `researcher`, `coder`, `tester`, `writer`, `filer`, `git-ops`

Specialists never delegate further.

## Delegation policy

- `orchestrator -> directors`
- `directors -> leaders`
- `leaders -> specialists`
- `specialists -> *` forbidden
- upward calls forbidden
- one accountable owner per workstream
- delegation depth capped at 3 hops

Operating contract:

- when a bare role name would be ambiguous in prose, prefer scoped references such as `directors/mind`, `directors/sentinel`, `leaders/evolver`, or `leaders/reviewer`
- `orchestrator` should not do deep task analysis or direct implementation; it routes, lightly accepts, and communicates upward
- `orchestrator` should touch every director lane in each active round and set explicit output floors
- `craft` owns construction and runtime verification via `builder`, `shaper`, and `verifier`
- `forge` owns external-world reads and writes via `courier` and `herald`
- `mind` owns knowledge and self-evolution via `archivist`, `scout`, and `evolver`
- `sentinel` owns validation and gates via `reviewer`
- review and testing stay split: static review belongs to `sentinel/reviewer`, while execution-time verification belongs to `craft/verifier`
- leaders analyze and integrate the task themselves, using specialists only for narrow subtasks
- specialists execute bounded tasks only and never redefine scope

## Runtime boundaries

- `marrow_core/contracts.py` - role inventory and workspace topology
- `marrow_core/prompting.py` - context execution and prompt assembly
- `marrow_core/runtime.py` - socket, queue, binary path resolution
- `marrow_core/task_queue.py` - filesystem queue read/write helpers
- `marrow_core/health.py` - doctor and self-check health checks
- `marrow_core/services.py` - launchd/systemd rendering
- `marrow_core/scaffold.py` - workspace scaffold and starter config generation
- `marrow_core/heartbeat.py` - scheduled orchestration per configured top-level agent
- `marrow_core/ipc.py` - local control plane over Unix socket
- `marrow_core/cli.py` - user-facing command surface

## Filesystem layout

```text
/opt/marrow-core/
├── marrow_core/
├── roles/
├── prompts/
├── context.d/
├── roles.toml
├── marrow.toml
├── lib.sh
└── setup.sh

/Users/marrow/
├── .opencode/agents/
├── context.d/
├── tasks/
│   ├── queue/
│   ├── delegated/
│   └── done/
├── runtime/
│   ├── state/
│   ├── checkpoints/
│   └── logs/exec/
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

## Testing guidance

- prefer one high-signal behavior test over multiple helper tests for the same failure mode
- keep supervisor boundary coverage concentrated in `tests/test_supervisor.py`
- keep single-user compatibility coverage in the narrower module test files
- add lower-level tests only when a helper has meaningful branching not already covered by a higher-level test
