#!/bin/bash
# Test script for macOS environment setup
# This script simulates what the GitHub Actions workflow does

set -euo pipefail

WORKSPACE_DIR="/tmp/marrow-test-workspace"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Marrow Core macOS Test Setup ==="
echo "Repository: $REPO_DIR"
echo "Workspace: $WORKSPACE_DIR"
echo ""

# Clean up previous test runs
if [ -d "$WORKSPACE_DIR" ]; then
    echo "Cleaning up previous test workspace..."
    rm -rf "$WORKSPACE_DIR"
fi

# Create workspace structure
echo "Creating workspace structure..."
mkdir -p "$WORKSPACE_DIR/runtime/state"
mkdir -p "$WORKSPACE_DIR/runtime/handoff/scout-to-artisan"
mkdir -p "$WORKSPACE_DIR/runtime/handoff/artisan-to-scout"
mkdir -p "$WORKSPACE_DIR/runtime/checkpoints"
mkdir -p "$WORKSPACE_DIR/runtime/logs/exec"
mkdir -p "$WORKSPACE_DIR/tasks/queue"
mkdir -p "$WORKSPACE_DIR/tasks/delegated"
mkdir -p "$WORKSPACE_DIR/tasks/done"
mkdir -p "$WORKSPACE_DIR/context.d"
mkdir -p "$WORKSPACE_DIR/.opencode/agents"

# Copy context providers
echo "Copying context providers..."
cp "$REPO_DIR"/context.d/*.py "$WORKSPACE_DIR/context.d/"
chmod +x "$WORKSPACE_DIR"/context.d/*.py

# Link agent definitions
echo "Linking agent definitions..."
ln -sf "$REPO_DIR/agents/scout.md" "$WORKSPACE_DIR/.opencode/agents/scout.md"
ln -sf "$REPO_DIR/agents/artisan.md" "$WORKSPACE_DIR/.opencode/agents/artisan.md"

# Create test configuration
echo "Creating test configuration..."
cat > /tmp/marrow-test-auto.toml << EOF
core_dir = "$REPO_DIR"

[[agents]]
name = "scout"
heartbeat_interval = 300
heartbeat_timeout = 500
workspace = "$WORKSPACE_DIR"
agent_command = "opencode run --agent scout --model github-copilot/gpt-4o-mini"
context_dirs = [
  "$WORKSPACE_DIR/context.d",
]

[[agents]]
name = "artisan"
heartbeat_interval = 8640
heartbeat_timeout = 7200
workspace = "$WORKSPACE_DIR"
agent_command = "opencode run --agent artisan --model github-copilot/gpt-4o-mini"
context_dirs = [
  "$WORKSPACE_DIR/context.d",
]
EOF

# Create a test task
echo "Creating test task..."
cat > "$WORKSPACE_DIR/tasks/queue/test-task.md" << 'EOF'
# Test Task: System Health Check

Please perform the following:
1. Check the current workspace directory structure
2. List files in the runtime directory
3. Create a simple status report in runtime/state/test-report.txt

This is a test task to verify the marrow-core system is working correctly.
EOF

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Test workspace created at: $WORKSPACE_DIR"
echo "Test configuration at: /tmp/marrow-test-auto.toml"
echo ""
echo "Next steps:"
echo "  1. Validate config:  marrow validate --config /tmp/marrow-test-auto.toml"
echo "  2. Setup workspace:  marrow setup --config /tmp/marrow-test-auto.toml"
echo "  3. Test dry-run:     marrow dry-run --config /tmp/marrow-test-auto.toml"
echo "  4. Run once:         marrow run-once --config /tmp/marrow-test-auto.toml"
echo ""
