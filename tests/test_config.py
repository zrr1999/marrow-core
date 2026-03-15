"""Tests for marrow_core.config."""

from __future__ import annotations

import textwrap
import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError

from marrow_core.config import AgentConfig, PluginConfig, ServiceConfig, load_config


def test_empty_name_raises():
    with pytest.raises(ValueError, match="empty"):
        AgentConfig(name="", agent_command="cmd", workspace="/tmp")


def test_relative_workspace_raises():
    with pytest.raises(ValueError, match="absolute"):
        AgentConfig(name="x", agent_command="cmd", workspace="relative/path")


def test_interval_clamping():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cfg = AgentConfig(
            name="x",
            agent_command="cmd",
            workspace="/tmp",
            heartbeat_interval=10,
        )
        assert cfg.heartbeat_interval == 60
        assert len(w) == 1


def test_interval_allows_multi_day_schedule():
    cfg = AgentConfig(
        name="x",
        agent_command="cmd",
        workspace="/tmp",
        heartbeat_interval=302400,
    )
    assert cfg.heartbeat_interval == 302400


def test_context_dirs_relative_raises():
    with pytest.raises(ValueError, match="absolute"):
        AgentConfig(
            name="x",
            agent_command="cmd",
            workspace="/tmp",
            context_dirs=["relative/dir"],
        )


def test_service_mode_rejects_unknown() -> None:
    with pytest.raises(ValueError, match=r"service\.mode"):
        ServiceConfig(mode="other")


def test_plugin_requires_absolute_paths() -> None:
    with pytest.raises(ValueError, match="absolute"):
        PluginConfig(name="dashboard", kind="dashboard", command="python", cwd="relative/path")


def test_load_config(tmp_path: Path):
    toml = tmp_path / "marrow.toml"
    toml.write_text(
        textwrap.dedent("""\
        [service]
        mode = "supervisor"
        runtime_root = "/var/lib/marrow"

        [[agents]]
        user = "marrow"
        name = "orchestrator"
        agent_command = "opencode run --agent orchestrator"
        workspace = "/Users/marrow"
        context_dirs = ["/Users/marrow/context.d"]

        [[plugins]]
        name = "dashboard"
        kind = "dashboard"
        command = "python"
        args = ["-m", "marrow_dashboard", "serve"]
        workspace = "/Users/marrow"
    """)
    )
    root = load_config(toml)
    assert len(root.agents) == 1
    assert root.agents[0].name == "orchestrator"
    assert root.agents[0].user == "marrow"
    assert root.agents[0].home == "/Users/marrow"
    assert root.service.mode == "supervisor"
    assert root.core_dir == ""
    assert root.ipc.enabled is True
    assert root.self_check.enabled is True
    assert len(root.plugins) == 1
    assert root.plugins[0].name == "dashboard"


def test_load_config_defaults_workspace_and_context_from_user(tmp_path: Path) -> None:
    toml = tmp_path / "marrow.toml"
    toml.write_text(
        textwrap.dedent("""\
        [profile]
        root_dir = "/opt/marrow-bot"

        [service]
        mode = "single_user"
        config_path = "/opt/marrow-bot/marrow.toml"

        [[agents]]
        user = "marrow"
        name = "orchestrator"
        agent_command = "opencode run --agent orchestrator"
    """)
    )

    root = load_config(toml)

    assert root.profile.root_dir == "/opt/marrow-bot"
    assert root.profile.source_context_dir == "/opt/marrow-bot/context.d"
    assert root.service.config_path == "/opt/marrow-bot/marrow.toml"
    assert root.agents[0].workspace.endswith("/marrow")
    assert root.agents[0].agent_command == "opencode run --agent orchestrator"
    assert root.agents[0].context_dirs == ["/Users/marrow/context.d"]


def test_extra_forbid(tmp_path: Path):
    toml = tmp_path / "marrow.toml"
    toml.write_text(
        textwrap.dedent("""\
        unknown_key = true
        [[agents]]
        name = "x"
        agent_command = "cmd"
        workspace = "/tmp"
    """)
    )
    with pytest.raises(ValidationError):
        load_config(toml)
