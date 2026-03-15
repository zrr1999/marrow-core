# Work items and hosted plugins

## Why this exists

This document defines the smallest shared contract needed to decouple:

- intake gateways,
- bot/worker logic,
- dashboards,
- and the core runtime host.

The goal is not a finished product surface. The goal is a stable seam.

## Work-item contract

`marrow_core.work_items` provides:

- `WorkItemSource`: origin metadata such as `channel`, `system`, `event_type`, `external_id`
- `WorkItemPayload`: portable payload with `title`, `body`, `kind`, `attributes`
- `WorkItem`: stable envelope with `item_id`, `kind`, `status`, timestamps, tags, source, payload
- `FileSystemWorkItemStore`: one JSON file per work item under `work-items/`

### Minimal lifecycle

- `received`
- `ready`
- `in_progress`
- `blocked`
- `completed`
- `failed`

### Intended ownership

- **gateway** writes newly received work items
- **bot/profile repos** consume and mutate status
- **dashboard** reads and visualizes the same contract
- **core** owns only the contract and basic persistence helper

## Hosted plugin contract

`RootConfig.plugins` defines the smallest host-managed plugin entry:

```toml
[[plugins]]
name = "dashboard"
kind = "dashboard" # or "background_service"
command = "python"
args = ["-m", "marrow_dashboard", "serve", "--config", "/etc/marrow/dashboard.toml"]
cwd = "/opt/marrow-dashboard"
workspace = "/Users/marrow"
config_path = "/etc/marrow/dashboard.toml"
auto_start = false
capabilities = ["read_work_items"]

[plugins.env]
MARROW_WORKSPACE = "/Users/marrow"
```

`marrow_core.plugin_host` provides:

- runtime-dir creation under `runtime/plugins/` and `runtime/logs/plugins/`
- resolved hosted-plugin metadata
- JSON manifest rendering for host/plugin handoff
- launchd/systemd unit rendering for `background_service` plugins with `auto_start = true`

### Plugin fields

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| `name` | yes | - | non-empty identifier used in manifest and unit names |
| `kind` | no | `background_service` | allowed values: `dashboard`, `background_service` |
| `command` | yes | - | first argv element for the hosted process |
| `args` | no | `[]` | additional argv items |
| `enabled` | no | `true` | disabled plugins are skipped from manifest and unit rendering |
| `auto_start` | no | `false` | only affects `background_service` plugins |
| `cwd` | no | empty | must be an absolute path if set |
| `workspace` | no | empty | must be an absolute path if set |
| `config_path` | no | empty | must be an absolute path if set |
| `capabilities` | no | `[]` | descriptive capability tags only |
| `env` | no | `{}` | string-to-string table exported into manifest / service env |

### Resolution rules

- `cwd`, `workspace`, and `config_path` must be absolute when provided.
- If `cwd` is empty, the host uses `plugin.workspace` and then the primary workspace passed to the host.
- If `workspace` is empty, the host uses the primary workspace passed to the host.
- `args` and `capabilities` accept either TOML arrays or a single string; empty values are dropped.
- `env` must be a TOML table/object.
- Only `enabled = true` plugins appear in the manifest or service output.

### Host behavior matrix

| Kind | Manifest entry | Service unit | `auto_start` meaning |
| --- | --- | --- | --- |
| `dashboard` | yes | no | ignored; dashboards are described but not auto-started by core |
| `background_service` | yes | yes, when `auto_start = true` | render a launchd/systemd unit alongside the main heart service |

### Operator flow

1. Define one or more `[[plugins]]` entries in the runtime config.
2. Run `uvx marrow-core validate --config /path/to/runtime-config.toml` to check the config surface.
3. Run `uvx marrow-core install-service --config /path/to/runtime-config.toml --output-dir ./service-out`.
4. Inspect:
   - `./service-out/` for the main heart unit plus any auto-start background-service units
   - `<primary-workspace>/runtime/plugins/manifest.json` for the hosted-plugin manifest

### Failure and ignore rules

- relative `cwd`, `workspace`, or `config_path` values fail config validation
- `env` values that are not a TOML table/object fail config validation
- `enabled = false` skips the plugin entirely
- `dashboard` plugins are written to the manifest even if `auto_start = true`, but no auto-start service unit is rendered
- plugin manifest rendering requires a primary workspace, which today comes from the first configured agent workspace

## Boundary rules

### core

- owns contracts, storage helpers, and generic hosting mechanics
- does **not** own Feishu semantics, bot workflows, or dashboard UI policy

### gateway

- translates external events into work items
- does **not** embed bot role logic

### bot/profile repo

- interprets work items and performs task execution
- does **not** own external intake transport details

### dashboard

- reads shared work-item data and presents operational views
- does **not** mutate gateway-specific adapters

## Current limitations

- no database-backed store yet
- no in-process plugin lifecycle supervisor beyond manifest generation and optional service-manager units
- no access-control layer around work-item mutation yet

Those are intentional follow-up slices.
