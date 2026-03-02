# macOS Testing Environment

This document describes the macOS testing setup for marrow-core using GitHub Actions.

## Overview

The macOS test workflow (`macos-test.yml`) provides end-to-end integration testing of the marrow-core system on macOS. It:

1. Sets up a complete marrow-core environment
2. Configures both scout and artisan agents with free models
3. Runs a complete workflow cycle
4. Verifies execution logs and workspace state

## Key Features

### Free Model Configuration

The test uses **github-copilot/gpt-4o-mini** (OpenCode's free model) instead of paid models:

```toml
agent_command = "opencode run --agent scout --model github-copilot/gpt-4o-mini"
```

This ensures tests can run without requiring API keys or credits.

### Test Workspace Structure

```
/tmp/marrow-test-workspace/
├── runtime/
│   ├── state/              # Agent state files
│   ├── handoff/
│   │   ├── scout-to-artisan/
│   │   └── artisan-to-scout/
│   ├── checkpoints/        # Task checkpoints
│   └── logs/
│       └── exec/           # Execution logs
├── tasks/
│   ├── queue/              # Pending tasks
│   ├── delegated/          # Delegated tasks
│   └── done/               # Completed tasks
├── context.d/              # Context provider scripts
└── .opencode/
    └── agents/             # Agent definitions (symlinked)
```

## GitHub Actions Workflow

The workflow includes these stages:

1. **Setup**: Install dependencies (uv, opencode)
2. **Environment**: Create workspace structure and link files
3. **Configuration**: Generate test config with free models
4. **Validation**: Verify config with `marrow validate`
5. **Setup**: Initialize workspace with `marrow setup`
6. **Dry-run**: Test prompt generation without execution
7. **Execute**: Run agents once with `marrow run-once`
8. **Verify**: Check logs and workspace state
9. **Upload**: Archive logs as artifacts

## Local Testing

You can test the setup locally on macOS:

```bash
# Run the test setup script
./test-macos-setup.sh

# Follow the instructions to validate and run
marrow validate --config /tmp/marrow-test-auto.toml
marrow setup --config /tmp/marrow-test-auto.toml
marrow run-once --config /tmp/marrow-test-auto.toml
```

Or use the included test configuration:

```bash
# Edit marrow-test.toml to set correct paths
# Then run:
marrow validate --config marrow-test.toml
marrow run-once --config marrow-test.toml
```

## Test Task

The workflow creates a simple test task in `tasks/queue/test-task.md`:

```markdown
# Test Task: System Health Check

Please perform the following:
1. Check the current workspace directory structure
2. List files in the runtime directory
3. Create a simple status report in runtime/state/test-report.txt
```

This validates that:
- Agents can read tasks from the queue
- Context providers work correctly
- Agents can write to the workspace
- Handoff mechanism works (scout → artisan delegation)

## Verification Steps

The workflow verifies:

1. **Execution logs exist**: Checks `runtime/logs/exec/` for agent output
2. **Task processing**: Monitors queue, delegated, and done directories
3. **Handoff files**: Checks scout-to-artisan and artisan-to-scout handoffs
4. **State files**: Verifies agents create state files

## Artifacts

All test logs are uploaded as artifacts (retained for 7 days):
- Execution logs (`runtime/logs/`)
- State files (`runtime/state/`)
- Handoff files (`runtime/handoff/`)

## Configuration Notes

### Model Selection

The test uses `github-copilot/gpt-4o-mini` which is:
- Free to use with OpenCode
- Sufficient for basic task processing
- Available without API keys

For production, you can use more capable models:
- `github-copilot/gpt-5-mini` (scout default)
- `github-copilot/gpt-5.2` (artisan default)

### Timeouts

- `heartbeat_timeout`: 500s (scout), 7200s (artisan)
- Workflow timeout: 15 minutes
- Prevents hanging if agent gets stuck

### Environment Variables

- `MARROW_WORKSPACE`: Set to workspace path for context scripts
- Required by context providers to locate task queue

## Troubleshooting

### Agent Not Found

If `opencode run` fails, install opencode using npm:
```bash
npm install -g opencode-ai@latest
```

Note: opencode is a Node.js package, not a Python package. Use `npm` to install it, not `uv` or `pip`.

### Permission Denied

Ensure scripts are executable:
```bash
chmod +x context.d/*.py
```

### Model Not Available

If the free model is unavailable, check:
```bash
opencode models list
```

And update to an available free model.

## CI Integration

The workflow runs on:
- Push to `main` branch
- Pull requests
- Manual trigger (`workflow_dispatch`)

This ensures all changes are tested in a real macOS environment before merging.
