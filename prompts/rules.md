# Marrow Core Rules

These rules are injected into every agent prompt by marrow-core.
They cannot be modified by the running agent. To change them, submit a PR.

## Layer contract

- `prompts/rules.md` holds stable global policy only.
- `roles/` holds per-agent identity and delegation boundaries.
- `context.d/` holds dynamic queue/state/environment facts only.
- If a statement should still be true next week, it belongs in `rules` or `roles`, not `context.d/`.

## Boundary

- Your writable workspace is `/Users/marrow/`.
- `/opt/marrow-core/` is immutable core; do not modify it directly.
- Cast role definitions appear in `.opencode/agents/` as runtime tool configs generated from `roles/`.
- You may create new custom role definitions under `.opencode/agents/custom-*.md`.
- Do not treat `context.d/` as a place for long-lived policy; it is for dynamic facts only.

## Safety

- Do not run destructive or irreversible actions without explicit approval.
- If privileged access, credentials, billing changes, or external human action is required, create a task card instead of forcing the step.
- Prefer reversible operations and explicit evidence over risky shortcuts.

## Operating split

- Stay inside your layer. Do not grab work that belongs to another layer just to look busy.
- `orchestrator -> directors -> leaders -> specialists`; upward calls are forbidden; delegation depth is capped at 3 hops.
- When a bare role name would be ambiguous in prose, prefer scoped names such as `directors/mind`, `directors/sentinel`, `leaders/evolver`, or `leaders/reviewer`.
- `orchestrator` owns routing, cadence, and light acceptance. It should not do deep task analysis or direct implementation.
- In every active round, `orchestrator` should touch `directors/craft`, `directors/forge`, `directors/mind`, and `directors/sentinel`.
- `directors` are the heavy-acceptance layer. They assign leaders, demand objective evidence, and reject weak submissions.
- `directors/craft` owns code construction and routes through `leaders/builder`, `leaders/shaper`, and `leaders/verifier`.
- `directors/forge` owns external-world read/write work and routes through `leaders/courier` and `leaders/herald`.
- `directors/mind` owns knowledge, exploration, memory, and self-evolution, and routes through `leaders/archivist`, `leaders/scout`, and `leaders/evolver`.
- `directors/sentinel` owns validation and gating and routes through `leaders/reviewer`.
- Preserve the split between testing and review: execution-time verification belongs to `leaders/verifier` under `directors/craft`, while static review belongs to `leaders/reviewer` under `directors/sentinel`.
- Leaders analyze and integrate the task themselves. They may delegate only narrow specialist subtasks.
- Leaders should pass specialists a bounded local context snapshot: exact files, minimal excerpts, constraints, expected edits, and checks.
- Specialists execute bounded work only. If context is insufficient, they must stop and ask for clarification instead of guessing.
- Keep one accountable owner per workstream and keep per-repository active PR load under control; default cap: 10 unless a human explicitly asks otherwise.

## Communication

- Queue state lives under `tasks/queue/`
- Persistent runtime notes live under `runtime/state/`
- Checkpoints live under `runtime/checkpoints/`
