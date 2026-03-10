"""Tests for marrow_core.config."""

from __future__ import annotations

import textwrap
import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError

from marrow_core.config import AgentConfig, RootConfig, ServiceConfig, load_config


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


def test_service_mode_rejects_unknown() -> None:
    with pytest.raises(ValueError, match=r"service\.mode"):
        ServiceConfig(mode="other")


def test_supervisor_mode_requires_run_identity() -> None:
    with pytest.raises(ValidationError, match="run_as_user"):
        RootConfig.model_validate(
            {
                "service": {"mode": "supervisor"},
                "agents": [
                    {
                        "name": "curator",
                        "agent_command": "cmd",
                        "workspace": "/Users/marrow",
                        "home": "/Users/marrow",
                    }
                ],
            }
        )


def test_supervisor_mode_requires_home() -> None:
    with pytest.raises(ValidationError, match="home"):
        RootConfig.model_validate(
            {
                "service": {"mode": "supervisor"},
                "agents": [
                    {
                        "name": "curator",
                        "agent_command": "cmd",
                        "workspace": "/Users/marrow",
                        "run_as_user": "marrow",
                    }
                ],
            }
        )


def test_load_config(tmp_path: Path):
    toml = tmp_path / "marrow.toml"
    toml.write_text(
        textwrap.dedent("""\
        core_dir = "/opt/marrow-core"

        [service]
        mode = "supervisor"
        runtime_root = "/var/lib/marrow"

        [[agents]]
        name = "curator"
        agent_command = "opencode run --agent curator"
        workspace = "/Users/marrow"
        run_as_user = "marrow"
        home = "/Users/marrow"
        context_dirs = ["/Users/marrow/context.d"]
    """)
    )
    root = load_config(toml)
    assert len(root.agents) == 1
    assert root.agents[0].name == "curator"
    assert root.service.mode == "supervisor"
    assert root.core_dir == "/opt/marrow-core"
    assert root.ipc.enabled is True
    assert root.self_check.enabled is True


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
