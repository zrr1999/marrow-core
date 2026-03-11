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
| `curator` | human communication, routing, output pacing, light acceptance | `stewards` |

### stewards — `roles/stewards/`

| Role | Domain | Can delegate to |
|------|--------|-----------------|
| `delivery-steward` | deterministic delivery intake, decomposition, heavy acceptance, queue drain | `leaders` |
| `portfolio-steward` | repository portfolio scanning, CI/review watchlists, PR/issue movement, opportunity intake, showcase surfaces | `leaders` |
| `research-steward` | frontier learning, experiments, research intake, internal materials | `leaders` |
| `acceptance-steward` | strict steward audits, quality gates, improvement guidance, workload audits | `leaders` |

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

Operating contract:

- `curator` should not do deep task analysis or direct implementation; it routes, lightly accepts, and communicates upward.
- `curator` should touch every steward lane in each active round, start with a round scorecard, set explicit output floors, re-check `tasks/queue/` after every steward cycle, and refuse to end the round while queue files remain.
- every active round must show quantifiable value in three tracks: self-improvement across accessible repo buckets, outward-facing showcase progress, and durable internal materials.
- self-improvement coverage should include `marrow-core`, other org repos, agent-owned repos or surfaces, and user repos when they are accessible; if one bucket is unavailable, the round should record the evidence and substitute another accessible improvement.
- outward-facing showcase progress should include at least 1 accepted advancement to a homepage, demo path, README, case study, example, changelog, or another public-facing surface.
- durable internal materials should include at least 3 named artifacts such as experiment briefs, research reports, comparison notes, or decision memos.
- first-cycle steward workloads should stay in the same order of magnitude; unjustified workload skew above roughly 2:1 should be corrected or explicitly explained.
- stewards are the heavy-acceptance layer and own lane-specific decomposition.
- `delivery-steward` drains `tasks/queue/`, moves completed work to `tasks/done/`, and reports the final zero-queue check.
- `portfolio-steward` must keep scanning until it has at least 10 concrete repo, PR, issue, update, or refactor tasks worth routing and at least 1 outward-facing showcase advancement.
- `research-steward` must produce at least 5 concrete frontier findings, experiment briefs, comparisons, or follow-up tasks per active round, including at least 3 durable internal materials.
- `acceptance-steward` must audit other stewards strictly, fail weak output, check round scorecard coverage plus workload balance, and give concrete improvement advice; curator may dispatch multiple acceptance passes on the same work.
- leaders analyze and integrate the task themselves, using experts only for narrow subtasks.
- experts execute bounded tasks only and never redefine scope.
- default concurrency guardrail: no more than 10 active PRs per repository unless a human explicitly asks otherwise.

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
