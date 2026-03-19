# marrow-core Refactor Blueprint

## Direction

`marrow-core` becomes the stable service/runtime kernel.

It owns:
- service lifecycle
- scheduling
- sync and self-check
- IPC status/control
- immediate trigger with optional one-shot prompt
- service installation/rendering

It does not own:
- task queueing
- work-item contracts
- human workflow state machines
- external workflow orchestration policy

Those move to external repos.

## New Product Shape

One public CLI sits on top of the runtime core.

- root commands are the normal user-facing interface
- `service` remains only as an internal/logical grouping for runtime mechanics
- no separate `agent` command surface

Current command shape:

- `marrow run`
- `marrow run-once`
- `marrow dry-run`
- `marrow sync-once`
- `marrow setup`
- `marrow validate`
- `marrow doctor`
- `marrow scaffold`
- `marrow install-service`
- `marrow status`
- `marrow wake --reason ... --prompt ...`

## Runtime Boundary

Keep these modules as the active core boundary:

- `marrow_core/config.py`
- `marrow_core/runtime.py`
- `marrow_core/heartbeat.py`
- `marrow_core/ipc.py`
- `marrow_core/worker.py`
- `marrow_core/services.py`
- `marrow_core/health.py`
- `marrow_core/sync.py`
- `marrow_core/triggers.py`

Keep CLI assembly under:

- `marrow_core/cli/service.py`
- `marrow_core/cli/ops.py`
- `marrow_core/cli/__main__.py`

## Trigger Model

Replace task submission with trigger-only control.

Trigger payload:

```json
{"agent":"orchestrator","reason":"manual wake","prompt":"Focus on startup recovery."}
```

Semantics:

- wake the selected agent immediately
- attach prompt only to the next run
- do not persist into `context.d`
- consume after one run

This is represented in-memory for single-user mode and via worker request files in supervisor mode.

## CLI Contract

### Public root commands

- `run`
- `run-once`
- `dry-run`
- `sync-once`
- `setup`
- `validate`
- `doctor`
- `scaffold`
- `install-service`
- `status`
- `wake --reason ... --prompt ...`

Rules:

- one normal command surface
- human-readable by default
- stable enough for scripts, but no separate machine persona

### Internal service commands

Still exist for implementation structure:

- `service worker-run`
- `service workspace-sync`

These are not the main public interface.

## Config Evolution

Current config still uses `[[agents]]` as the scheduling inventory. That is acceptable for the transition.

Next cleanup step:

- rename agent runtime fields to service-oriented names
- reduce config to service-owned concerns only
- keep external workflow/task repos responsible for their own state and schemas

Potential future shape:

```toml
[service]
mode = "supervisor"
runtime_root = "/var/lib/marrow"

[control]
socket_path = "/var/lib/marrow/state/marrow.sock"

[[service.agents]]
name = "orchestrator"
command = "opencode run --agent orchestrator"
workspace = "/Users/marrow"
interval_seconds = 10800
timeout_seconds = 7200
```

## Migration Rules

### Removed from active core

- filesystem task queue
- IPC `/tasks`
- `marrow task add`
- `marrow task list`
- active `work_items` model in `marrow_core/`
- separate `agent` CLI surface

### Backed up only

- `legacy/task_queue.py`
- `legacy/work_items.py`

Nothing in active runtime code should import from `legacy/`.

## Suggested Next Refactor Passes

### Pass 1: stabilize the unified CLI

- finish test updates for the unified root command tree
- update README/examples/docs to remove task ownership and `agent` wording
- keep only hidden internal runtime commands where needed

### Pass 2: simplify service core

- move more runtime orchestration out of CLI modules into pure service modules
- make CLI wrappers thinner
- reduce overlap between `service.py` and `ops.py`

### Pass 3: harden control plane

- define explicit JSON schema for `/status` and `/wake`
- add structured trigger request persistence rules for supervisor mode
- decide whether filtered `status` views are needed

### Pass 4: shrink internal command leakage

- keep `worker-run` and `workspace-sync` internal-only
- keep service manager output and docs aligned with public root commands

## Design Principles

- service core stays small and boring
- one public CLI is easier to remember and maintain
- tasks belong outside the runtime kernel
- one-shot prompts are triggers, not queue items
