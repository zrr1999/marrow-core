"""Tests for marrow_core.config."""

from __future__ import annotations

import textwrap
import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError

from marrow_core.config import AgentConfig, RootConfig, load_config


def test_minimal_agent_config():
    cfg = AgentConfig(
        name="test",
        agent_command="opencode run",
        workspace="/tmp/test",
    )
    assert cfg.name == "test"
    assert cfg.heartbeat_interval == 300
    assert cfg.heartbeat_timeout == 500
    assert cfg.context_dirs == []


def test_name_strip():
    cfg = AgentConfig(name="  curator  ", agent_command="cmd", workspace="/tmp")
    assert cfg.name == "curator"


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


def test_context_dirs_normalization():
    cfg = AgentConfig(
        name="x",
        agent_command="cmd",
        workspace="/tmp",
        context_dirs=["/foo/bar"],
    )
    assert cfg.context_dirs == ["/foo/bar"]


def test_context_dirs_relative_raises():
    with pytest.raises(ValueError, match="absolute"):
        AgentConfig(
            name="x",
            agent_command="cmd",
            workspace="/tmp",
            context_dirs=["relative/dir"],
        )


def test_load_config(tmp_path: Path):
    toml = tmp_path / "marrow.toml"
    toml.write_text(
        textwrap.dedent("""\
        core_dir = "/opt/marrow-core"

        [[agents]]
        name = "curator"
        agent_command = "opencode run --agent curator"
        workspace = "/Users/marrow"
        context_dirs = ["/Users/marrow/context.d"]
    """)
    )
    root = load_config(toml)
    assert len(root.agents) == 1
    assert root.agents[0].name == "curator"
    assert root.core_dir == "/opt/marrow-core"
    assert root.ipc.enabled is True
    assert root.self_check.enabled is True


def test_root_config_rejects_non_top_level_scheduled_agent() -> None:
    with pytest.raises(ValidationError, match="scheduled agent must be top-level"):
        RootConfig.model_validate(
            {
                "agents": [
                    {
                        "name": "conductor",
                        "agent_command": "cmd",
                        "workspace": "/tmp",
                    }
                ]
            }
        )


def test_root_config_rejects_non_top_level_wake_agent() -> None:
    with pytest.raises(ValidationError, match=r"self_check\.wake_agent"):
        RootConfig.model_validate(
            {
                "agents": [
                    {
                        "name": "curator",
                        "agent_command": "cmd",
                        "workspace": "/tmp",
                    }
                ],
                "self_check": {"wake_agent": "review-lead"},
            }
        )


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
