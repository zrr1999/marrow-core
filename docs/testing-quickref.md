# macOS Testing - Quick Reference

## Quick Start

```bash
# Run the automated setup script
./test-macos-setup.sh

# Then execute tests
export MARROW_WORKSPACE=/tmp/marrow-test-workspace
marrow run-once --config /tmp/marrow-test-auto.toml
```

## Common Commands

```bash
# Validate configuration
marrow validate --config /tmp/marrow-test-auto.toml

# Test prompt generation (no execution)
marrow dry-run --config /tmp/marrow-test-auto.toml

# Run one cycle of all agents
marrow run-once --config /tmp/marrow-test-auto.toml

# Check logs
ls -la /tmp/marrow-test-workspace/runtime/logs/exec/
cat /tmp/marrow-test-workspace/runtime/logs/exec/*.log

# Check task status
ls -la /tmp/marrow-test-workspace/tasks/queue/
ls -la /tmp/marrow-test-workspace/tasks/delegated/
ls -la /tmp/marrow-test-workspace/tasks/done/

# Check handoffs
ls -la /tmp/marrow-test-workspace/runtime/handoff/scout-to-artisan/
ls -la /tmp/marrow-test-workspace/runtime/handoff/artisan-to-scout/

# Check state
cat /tmp/marrow-test-workspace/runtime/state/*.json
```

## Directory Structure

```
/tmp/marrow-test-workspace/
├── .opencode/agents/          # Agent definitions (symlinked)
├── context.d/                 # Context provider scripts
├── tasks/
│   ├── queue/                 # Pending tasks
│   ├── delegated/             # Tasks delegated to artisan
│   └── done/                  # Completed tasks
└── runtime/
    ├── state/                 # Agent state (JSON files)
    ├── logs/exec/             # Execution logs
    ├── checkpoints/           # Task checkpoints
    └── handoff/
        ├── scout-to-artisan/  # Scout → Artisan delegation
        └── artisan-to-scout/  # Artisan → Scout messages
```

## Troubleshooting

### "opencode: command not found"

```bash
# Install opencode
uv tool install opencode
# or
pip install opencode

# Verify
opencode --version
```

### "marrow: command not found"

```bash
# Install marrow-core
uv sync --all-groups

# Run via uv
uv run marrow --help
```

### Context scripts fail

```bash
# Check permissions
chmod +x /tmp/marrow-test-workspace/context.d/*.py

# Test individually
/tmp/marrow-test-workspace/context.d/queue.py
/tmp/marrow-test-workspace/context.d/explore.py
```

### "Model not available" error

```bash
# List available models
opencode models list

# Use a different free model
# Edit /tmp/marrow-test-auto.toml and replace:
# agent_command = "opencode run --agent scout --model github-copilot/gpt-4o-mini"
# with another free model from the list
```

### Agents hang or timeout

```bash
# Check if agents are running
ps aux | grep opencode

# Kill hung processes
pkill -f "opencode run"

# Clean workspace and retry
rm -rf /tmp/marrow-test-workspace
./test-macos-setup.sh
```

### No logs generated

```bash
# Verify workspace structure
ls -R /tmp/marrow-test-workspace

# Check core_dir in config
grep core_dir /tmp/marrow-test-auto.toml

# Verify agent definitions exist
ls -la /tmp/marrow-test-workspace/.opencode/agents/
```

### Task not processed

```bash
# Verify task file exists
cat /tmp/marrow-test-workspace/tasks/queue/test-task.md

# Run dry-run to see if task is detected
export MARROW_WORKSPACE=/tmp/marrow-test-workspace
marrow dry-run --config /tmp/marrow-test-auto.toml | grep -A 10 "test-task"
```

## Creating Custom Test Tasks

```bash
# Create a simple task
cat > /tmp/marrow-test-workspace/tasks/queue/my-task.md << 'EOF'
# My Custom Task

Description of what you want the agent to do.
EOF

# Run agents
marrow run-once --config /tmp/marrow-test-auto.toml
```

## Cleanup

```bash
# Remove test workspace
rm -rf /tmp/marrow-test-workspace

# Remove test config
rm -f /tmp/marrow-test-auto.toml
```

## GitHub Actions Access

```bash
# View workflow runs
# Go to: https://github.com/zrr1999/marrow-core/actions

# Download artifacts
# 1. Click on a workflow run
# 2. Scroll to "Artifacts"
# 3. Download "marrow-test-logs"
```

## Verifying Success

A successful test should show:

✅ **Execution logs** in `runtime/logs/exec/`
✅ **Task moved** from queue to delegated or done
✅ **State files** created in `runtime/state/`
✅ **No errors** in log files (check `*.stderr.log`)

## Model Options

Free models you can use:

- `github-copilot/gpt-4o-mini` (default in test config)
- Check `opencode models list` for current options

Production models (require credits):

- `github-copilot/gpt-5-mini` (scout default)
- `github-copilot/gpt-5.2` (artisan default)

## Configuration Tips

### Reduce timeouts for faster testing:

```toml
[[agents]]
name = "scout"
heartbeat_timeout = 60  # Instead of 500
```

### Test with verbose logging:

```bash
marrow run-once --config /tmp/marrow-test-auto.toml --verbose
```

### Test single agent:

Edit config to include only one agent section, then run.

## CI Integration

The workflow runs automatically on:

- Push to `main`
- Pull requests
- Manual trigger (Actions tab → Run workflow)

Workflow timeout: 15 minutes per agent execution

## Support

If tests fail:

1. Check workflow logs in GitHub Actions
2. Download and review artifacts
3. Run locally to reproduce
4. Check model availability
5. Verify dependencies installed correctly

## Performance

Typical execution times:

- Setup: ~2-3 minutes
- Validation: ~5 seconds
- Dry-run: ~10 seconds
- Agent execution: ~1-5 minutes per agent
- Total workflow: ~5-10 minutes

## Documentation

- Full guide: `docs/macos-testing.md`
- Implementation: `docs/implementation-summary.md`
- Main README: `README.md`
