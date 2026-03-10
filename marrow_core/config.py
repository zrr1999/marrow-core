"""Configuration loading and validation."""

from __future__ import annotations

import tomllib
import warnings
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _clamp(value: int, lo: int, hi: int, name: str) -> int:
    clamped = max(lo, min(hi, int(value)))
    if clamped != int(value):
        warnings.warn(f"{name}={value} outside [{lo},{hi}], clamped to {clamped}", stacklevel=3)
    return clamped


class AgentConfig(BaseModel):
    """Single scheduled agent definition."""

    name: str
    heartbeat_interval: int = 300
    heartbeat_timeout: int = 500
    agent_command: str
    workspace: str  # Agent's writable workspace root (e.g. /Users/marrow)
    run_as_user: str = ""
    run_as_group: str = ""
    home: str = ""
    context_dirs: list[str] = Field(default_factory=list)
    log_retention_days: int = 7  # exec-log age-based pruning (0 = disabled)
    log_max_count: int = 200  # exec-log count-based pruning (0 = disabled)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v: Any) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("agent name must not be empty")
        return s

    @field_validator("heartbeat_interval")
    @classmethod
    def _clamp_interval(cls, v: int) -> int:
        return _clamp(v, 60, 604800, "heartbeat_interval")

    @field_validator("heartbeat_timeout")
    @classmethod
    def _clamp_timeout(cls, v: int) -> int:
        return _clamp(v, 5, 86400, "heartbeat_timeout")

    @field_validator("run_as_user", "run_as_group", "home", mode="before")
    @classmethod
    def _strip_optional_fields(cls, v: Any) -> str:
        return str(v).strip() if v is not None else ""

    @field_validator("workspace")
    @classmethod
    def _abs_workspace(cls, v: str) -> str:
        if not Path(v).is_absolute():
            raise ValueError(f"workspace must be absolute: {v}")
        return v

    @field_validator("home")
    @classmethod
    def _abs_home(cls, v: str) -> str:
        if v and not Path(v).is_absolute():
            raise ValueError(f"home must be absolute: {v}")
        return v

    @field_validator("context_dirs", mode="before")
    @classmethod
    def _normalize_dirs(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        return [str(x).strip() for x in v if str(x).strip()]

    @field_validator("context_dirs")
    @classmethod
    def _abs_context_dirs(cls, v: list[str]) -> list[str]:
        for p in v:
            if not Path(p).is_absolute():
                raise ValueError(f"context_dirs must be absolute: {p}")
        return v


class IpcConfig(BaseModel):
    """Optional IPC server configuration (Unix domain socket)."""

    enabled: bool = True
    socket_path: str = ""  # If empty, derived from first agent's workspace
    task_dir: str = ""  # If empty, derived from first agent's workspace

    model_config = ConfigDict(extra="forbid")


class SyncConfig(BaseModel):
    """Periodic sync supervisor configuration."""

    enabled: bool = True
    interval_seconds: int = 3600
    failure_backoff_seconds: int = 300
    state_file: str = ""
    lock_file: str = ""

    model_config = ConfigDict(extra="forbid")

    @field_validator("interval_seconds")
    @classmethod
    def _clamp_interval(cls, v: int) -> int:
        return _clamp(v, 60, 604800, "sync.interval_seconds")

    @field_validator("failure_backoff_seconds")
    @classmethod
    def _clamp_backoff(cls, v: int) -> int:
        return _clamp(v, 5, 86400, "sync.failure_backoff_seconds")

    @field_validator("state_file", "lock_file")
    @classmethod
    def _abs_optional_path(cls, v: str) -> str:
        if v and not Path(v).is_absolute():
            raise ValueError(f"sync path must be absolute: {v}")
        return v


class SelfCheckConfig(BaseModel):
    """Core-owned health checks that can wake a top-level agent early."""

    enabled: bool = True
    interval_seconds: int = 900
    wake_agent: str = "curator"
    extra_commands: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("interval_seconds")
    @classmethod
    def _clamp_interval(cls, v: int) -> int:
        return _clamp(v, 60, 604800, "self_check.interval_seconds")

    @field_validator("wake_agent", mode="before")
    @classmethod
    def _normalize_wake_agent(cls, v: Any) -> str:
        return str(v).strip()

    @field_validator("extra_commands", mode="before")
    @classmethod
    def _normalize_commands(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        return [str(x).strip() for x in v if str(x).strip()]


class ServiceConfig(BaseModel):
    """Long-running service configuration."""

    mode: str = "single_user"
    runtime_root: str = ""
    log_dir: str = ""

    model_config = ConfigDict(extra="forbid")

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, v: Any) -> str:
        mode = str(v).strip() if v is not None else "single_user"
        if mode not in {"single_user", "supervisor"}:
            raise ValueError("service.mode must be 'single_user' or 'supervisor'")
        return mode

    @field_validator("runtime_root", "log_dir", mode="before")
    @classmethod
    def _strip_optional_path(cls, v: Any) -> str:
        return str(v).strip() if v is not None else ""

    @field_validator("runtime_root", "log_dir")
    @classmethod
    def _abs_optional_path(cls, v: str) -> str:
        if v and not Path(v).is_absolute():
            raise ValueError(f"service path must be absolute: {v}")
        return v


class RootConfig(BaseModel):
    """Top-level marrow.toml schema."""

    core_dir: str = "/opt/marrow-core"
    service: ServiceConfig = Field(default_factory=ServiceConfig)
    agents: list[AgentConfig] = Field(default_factory=list)
    ipc: IpcConfig = Field(default_factory=IpcConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    self_check: SelfCheckConfig = Field(default_factory=SelfCheckConfig)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_supervisor_agents(self) -> RootConfig:
        if self.service.mode != "supervisor":
            return self
        for agent in self.agents:
            if not agent.run_as_user:
                raise ValueError(
                    f"supervisor mode requires run_as_user for agent {agent.name!r}"
                )
            if not agent.home:
                raise ValueError(f"supervisor mode requires home for agent {agent.name!r}")
        return self


def load_config(path: Path) -> RootConfig:
    with path.open("rb") as f:
        data = tomllib.load(f)
    return RootConfig.model_validate(data)
