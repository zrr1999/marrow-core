"""Tests for marrow_core.config."""

from __future__ import annotations

import textwrap
import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError

from marrow_core.config import AgentConfig, load_config


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
    cfg = AgentConfig(name="  scout  ", agent_command="cmd", workspace="/tmp")
    assert cfg.name == "scout"


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
        name = "scout"
        agent_command = "opencode run --agent scout"
        workspace = "/Users/marrow"
        context_dirs = ["/Users/marrow/context.d"]
    """)
    )
    root = load_config(toml)
    assert len(root.agents) == 1
    assert root.agents[0].name == "scout"
    assert root.core_dir == "/opt/marrow-core"


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




