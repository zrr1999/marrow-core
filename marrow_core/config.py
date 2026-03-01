"""Configuration loading and validation.

Keeps it simple: one TOML file, one RootConfig, multiple AgentConfig.
All paths must be absolute. Intervals are clamped with loud warnings.
"""

from __future__ import annotations

import tomllib
import warnings
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    context_dirs: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")

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
        return _clamp(v, 60, 86400, "heartbeat_interval")

    @field_validator("heartbeat_timeout")
    @classmethod
    def _clamp_timeout(cls, v: int) -> int:
        return _clamp(v, 5, 86400, "heartbeat_timeout")

    @field_validator("workspace")
    @classmethod
    def _abs_workspace(cls, v: str) -> str:
        if not Path(v).is_absolute():
            raise ValueError(f"workspace must be absolute: {v}")
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


class RootConfig(BaseModel):
    """Top-level marrow.toml schema."""

    core_dir: str = "/opt/marrow-core"
    agents: list[AgentConfig] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


def load_config(path: Path) -> RootConfig:
    with path.open("rb") as f:
        data = tomllib.load(f)
    return RootConfig.model_validate(data)
