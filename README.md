# marrow-core

Minimal self-evolving agent scheduler with hard isolation between the immutable core and the writable agent workspace.

## Prompt model

Use one mental model everywhere:

- `rules` -> stable global policy in `prompts/rules.md`
- `roles` -> canonical role identity and delegation boundaries in `roles/`
- `context.d` -> dynamic queue, state, and environment facts only
- `skills` -> reusable procedures outside repo prompt assembly

Repo-root `agents/` is retired. Do not add prompt material there.

## Role layout

The canonical role tree is:

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

Delegation policy:

- `orchestrator -> directors`
- `directors -> leaders`
- `leaders -> specialists`
- `specialists -> none`
- no upward calls
- one accountable owner per workstream
- max delegation depth: 3 hops

Role intent:

- `orchestrator` is the only scheduled top-level agent by default.
- `directors/craft` owns code construction.
- `directors/forge` owns external-world reads and writes.
- `directors/mind` owns knowledge, exploration, memory, and self-evolution.
- `directors/sentinel` owns validation and gates.
- `leaders/verifier` executes tests and runtime checks under craft.
- `leaders/reviewer` handles static review under sentinel.

## Canonical model

The canonical source of truth is:

- `roles/` for role prompts and layout
- `roles.toml` for model-tier casting
- `marrow_core/contracts.py` for runtime inventory and workspace topology
- `.opencode/agents/` as the generated runtime surface

## CLI

```text
marrow run              # root supervisor or single-user heartbeat loop
marrow run-once         # one tick per scheduled agent, then exit
marrow dry-run          # assemble prompts without running agents
marrow sync-once        # one bounded sync attempt with structured result codes
marrow setup            # init root runtime or single-user workspace
marrow scaffold         # create a new writable workspace skeleton and starter config
marrow validate         # check config and show summary
marrow doctor           # verify workspace, context dirs, and agent command availability
marrow status           # query live heartbeat state over IPC
marrow wake             # wake one configured agent immediately via IPC
marrow install-service  # render launchd or systemd service files
marrow task add         # submit a task into tasks/queue via IPC
marrow task list        # inspect queued tasks via IPC
```

## Configuration

```toml
core_dir = "/opt/marrow-core"

[service]
mode = "supervisor"
runtime_root = "/var/lib/marrow"

[ipc]
enabled = true

[self_check]
enabled = true
interval_seconds = 900
wake_agent = "orchestrator"

[sync]
enabled = true
interval_seconds = 3600
failure_backoff_seconds = 300

[[agents]]
user = "marrow"
name = "orchestrator"
heartbeat_interval = 10800
heartbeat_timeout = 7200
workspace = "/Users/marrow"
agent_command = "/Users/marrow/.opencode/bin/opencode run --agent orchestrator"
context_dirs = ["/Users/marrow/context.d"]
```

## Runtime contract

`marrow-core` uses `role-forge` as the casting runtime. Canonical role files in `roles/` are cast into `.opencode/agents/`, then execution is handed off to the external `opencode` CLI configured by each agent's `agent_command`.

The effective execution path is:

1. edit canonical role definitions in `roles/`
2. cast them into `.opencode/agents/` via `role-forge`
3. launch `opencode run --agent <name>`

## Runtime boundaries

- `marrow_core/contracts.py` - canonical role inventory and workspace topology
- `marrow_core/prompting.py` - context execution and prompt assembly
- `marrow_core/runtime.py` - socket, queue, service-runtime, and binary path resolution
- `marrow_core/task_queue.py` - filesystem queue helpers
- `marrow_core/health.py` - reusable doctor and self-check health checks
- `marrow_core/services.py` - launchd/systemd rendering
- `marrow_core/scaffold.py` - workspace scaffold and starter config generation
- `marrow_core/heartbeat.py`, `marrow_core/cli.py`, `marrow_core/ipc.py` - orchestration layers

## Workspace layout

```text
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

## Testing guidance

- prefer one high-signal behavior test over multiple helper tests for the same failure mode
- keep supervisor boundary coverage concentrated in `tests/test_supervisor.py`
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
