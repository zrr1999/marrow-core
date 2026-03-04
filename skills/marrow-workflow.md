---
name: marrow-workflow
description: >-
  Core operational workflow for Marrow agents. Covers the handoff protocol,
  checkpoint discipline, task lifecycle, and filesystem conventions.
---

## Filesystem Layout

```
/Users/marrow/                    # Agent workspace (writable)
├── tasks/
│   ├── queue/                    # Pending tasks (JSON + text)
│   ├── delegated/                # Tasks handed off to artisan
│   └── done/                     # Completed tasks (move here when done)
├── runtime/
│   ├── state/                    # Persistent state (learnings.md, etc.)
│   ├── handoff/
│   │   ├── scout-to-artisan/     # Scout writes here, artisan reads
│   │   └── artisan-to-scout/     # Artisan writes here, scout reads
│   ├── checkpoints/              # Session checkpoints
│   └── logs/exec/                # Execution logs
└── workspace/                    # Working area (docs, designs, etc.)
```

## Task Lifecycle

1. Task arrives in `tasks/queue/` (JSON file, `ts` + `task_id` fields)
2. Scout reads it and either handles it immediately or creates a handoff
3. Artisan picks it up from the handoff and works it end-to-end
4. When done, **move the file** to `tasks/done/`

## Handoff Format

Scout creates a file in `runtime/handoff/scout-to-artisan/`:

```
[P0|P1|P2] 待 Artisan：<title> — <context/goal/constraints>; ETA: <time>
```

Artisan creates a file in `runtime/handoff/artisan-to-scout/` for follow-ups.

## Checkpoint Discipline

- Write to `runtime/checkpoints/` every 20–30 min
- File name: `artisan-YYYY-MM-DD-session<N>-<phase>.md`
- Include: what was tried, what worked/didn't, next steps
- **Never skip checkpoints** — they are the audit trail

## Core Boundary

- `/opt/marrow-core/` is **root-owned and immutable**
- Proposals for core changes go to `tasks/queue/core-proposal-*.md`
- The human maintainer reviews and applies proposals

## Learnings

- Distill session learnings to `runtime/state/learnings.md`
- Write concise bullet points: what you learned, not just what you did
