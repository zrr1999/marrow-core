# marrow-core

Minimal self-evolving agent scheduler with hard isolation between the immutable core and the writable agent workspace.

> Migration note: profile-coupled assets have been removed from `marrow-core`. New setups should provide prompts, context, role definitions, and runtime config from external profile/runtime repos such as `marrow-bot`.

## Prompt model

Use one mental model everywhere:

- `rules` -> stable global policy in the external profile bundle
- `roles` -> canonical role identity and delegation boundaries in the external profile bundle
- `context.d` -> dynamic queue, state, and environment facts from the external profile bundle
- `skills` -> reusable procedures outside repo prompt assembly

Repo-root `agents/` is retired. Do not add prompt material there.

## Profile ownership

Role trees, prompt policy, and model maps are external profile concerns.

`marrow-core` no longer ships canonical `roles/` or an in-repo casting flow. Use an external profile such as `marrow-bot` and cast it with `uvx role-forge`.

## Canonical model

The canonical source of truth is:

- external profile `roles/` for role prompts and layout
- external profile `roles.toml` for model-tier casting
- `marrow_core/contracts.py` for runtime inventory and workspace topology
- `marrow_core/work_items.py` for cross-repo work-item contracts and storage
- `marrow_core/plugin_host.py` for hosted plugin/background-service rendering
- `.opencode/agents/` as the generated runtime surface

## Recommended installation path

Use `marrow-core` as runtime package only:

- install `marrow-core` via `uvx`/package tooling
- provide runtime config outside core (or from an external profile repo)
- provide prompt/context/roles from an external profile root via `[profile]`
- use `uvx marrow-core validate --config /path/to/runtime-config.toml`
- use `uvx marrow-core install-service --config /path/to/runtime-config.toml`

`marrow-core` no longer carries in-repo profile assets. New deployments should supply them externally.

## uvx-first usage

Preferred invocation is package/runtime-first rather than source-checkout-first:

```bash
uvx marrow-core validate --config /path/to/runtime-config.toml
uvx marrow-core run --config /path/to/runtime-config.toml
uvx marrow-core install-service --config /path/to/runtime-config.toml --platform auto --output-dir ./service-out
```

The core runtime prompt is now intentionally generic. Execution policy belongs in external profile repos, not in `marrow_core.heartbeat`.

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
[service]
mode = "supervisor"
runtime_root = "/var/lib/marrow"

[profile]
root_dir = "/path/to/marrow-bot"

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

`marrow-core` does not cast profiles itself.

The effective execution path is:

1. maintain role definitions in an external profile repo
2. cast them with `uvx role-forge cast --config <profile>/roles.toml`
3. run `uvx marrow-core ...` against a runtime config that points at that profile

## Runtime boundaries

- `marrow_core/contracts.py` - canonical role inventory and workspace topology
- `marrow_core/work_items.py` - contract-first work-item models and filesystem store
- `marrow_core/plugin_host.py` - plugin/background-service host manifests and units
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
├── plugins/
├── work-items/
├── tasks/
│   ├── queue/
│   ├── delegated/
│   └── done/
├── runtime/
│   ├── state/
│   ├── checkpoints/
│   ├── logs/exec/
│   ├── logs/plugins/
│   └── plugins/
└── docs/
```

## Work items and hosted plugins

`marrow-core` now carries two minimal cross-repo contracts:

- **Work items**: a stable JSON-backed model in `marrow_core.work_items` for gateways to ingest, bots to process, and dashboards to inspect.
- **Hosted plugins**: a small `[[plugins]]` config surface for dashboard/background-service processes. `marrow_core.plugin_host` resolves runtime directories, emits a manifest, and can render autostart units for background services.

Typical hosted plugin/service examples include operator-side repos such as `marrow-dashboard` and `marrow-task`.

When `marrow install-service` is run with `[[plugins]]` configured, it now:

- writes a plugin manifest to `<primary-workspace>/runtime/plugins/manifest.json`
- renders autostart service units for `background_service` plugins with `auto_start = true`

Minimal `[[plugins]]` shape:

```toml
[[plugins]]
name = "dashboard"
kind = "dashboard"
command = "python"
args = ["-m", "marrow_dashboard", "serve", "--config", "/etc/marrow/dashboard.toml"]
cwd = "/opt/marrow-dashboard"
workspace = "/Users/marrow"
config_path = "/etc/marrow/dashboard.toml"
capabilities = ["read_work_items"]

[[plugins]]
name = "gateway"
kind = "background_service"
command = "python"
args = ["-m", "marrow_gateway", "serve"]
cwd = "/opt/marrow-gateway"
workspace = "/Users/marrow"
auto_start = true

[plugins.env]
MARROW_WORKSPACE = "/Users/marrow"
```

See `examples/runtime-config.example.toml` for a copyable example and `docs/contracts/work-items-and-plugins.md` for the contract-first boundary.

## Testing guidance

- prefer one high-signal behavior test over multiple helper tests for the same failure mode
- keep supervisor boundary coverage concentrated in `tests/test_supervisor.py`
- add lower-level tests only when a helper has meaningful branching not already covered by a higher-level test

## Quick start

Fresh install:

```bash
uvx marrow-core validate --config /path/to/runtime-config.toml
```

Manual update attempt:

```bash
uvx marrow-core sync-once --config /path/to/runtime-config.toml
```

Note: `sync-once` is maintenance-only and still assumes a source checkout `core_dir`. For pure `uvx` runtime installs, prefer disabling sync or using an external repo-maintenance flow.

Expected sync outcomes:

- `0` -> `noop`
- `10` -> `reloaded`
- `11` -> `restart_required`
- `1` -> `failed`
