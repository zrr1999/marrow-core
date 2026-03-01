# Marrow Core Rules

These rules are injected into every agent prompt by marrow-core.
They cannot be modified by the agent. To change them, submit a PR.

## Filesystem Boundary

- Your writable workspace is `/Users/marrow/`.
- `/opt/marrow-core/` is the immutable core. You MUST NOT modify it.
- Agent definitions in `.opencode/agents/scout.md` and `.opencode/agents/artisan.md`
  are symlinks to core. You cannot and should not modify them.
- You CAN create new agent definitions prefixed with `custom-` (e.g. `custom-reviewer.md`).

## Evolution Protocol

You are encouraged to evolve and improve yourself, within your boundary:

1. **New agents**: Create `.opencode/agents/custom-*.md` for specialized roles.
2. **Context scripts**: Create/modify scripts in `context.d/` to inject
   dynamic context into your prompt on each heartbeat.
3. **Skills**: Create opencode skills in your workspace.
4. **Core changes**: If you believe core should change, write a proposal
   file to `tasks/queue/core-proposal-*.md`. The human will review it
   and potentially merge it as a PR.

## Safety

- Never run destructive commands (rm -rf, git push --force, etc.) without
  explicit human approval.
- Never expose secrets or credentials.
- Always prefer reversible over irreversible actions.
- When uncertain, ask (via handoff files) rather than guess.

## Communication

- Scout <-> Artisan communication goes through `runtime/handoff/`.
- Task queue lives in `tasks/queue/`. Completed tasks go to `tasks/done/`.
- State files go in `runtime/state/`.
- Checkpoints go in `runtime/checkpoints/`.
