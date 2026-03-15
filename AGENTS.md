# marrow-core Architecture

## Overview

marrow-core is a minimal runtime package for autonomous agent scheduling. It does not ship a default profile, role tree, or casting workflow.

## Prompt layers

Keep these concepts separate:

- external profile `rules` -> stable global policy
- external profile `roles/` -> canonical role identity and delegation boundaries
- external profile `context.d/` -> dynamic facts only
- skills -> reusable procedures outside the repo prompt-layer contract

Repo-root `agents/` has been retired from the active prompt model.

## Canonical model

The canonical source of truth is:

- external profile `roles/` for role definitions
- external profile `roles.toml` for model-tier metadata
- `marrow_core/contracts.py` for runtime inventory and workspace topology rules

## Profile ownership

Delegation trees, role definitions, and casting policy live in external profile repos such as `marrow-bot`.

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
site-packages/marrow_core/ or uvx runtime
├── marrow_core/
├── examples/
└── docs/

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
| `setup` | workspace init |
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
