"""Scaffold templates for `marrow init` — generates L2 user-layer skeleton."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Template strings
# ---------------------------------------------------------------------------

_PYPROJECT_TOML = """\
[project]
name = "{name}"
version = "0.1.0"
description = "My marrow agent (L2 user layer)"
requires-python = ">=3.12"
dependencies = ["marrow-core>=0.3"]

[project.entry-points."marrow.layer"]
{name} = "{pkg}.layer:layer_info"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["F", "E", "W", "I", "B", "C4", "UP", "SIM", "RUF"]
"""

_README_MD = """\
# {name}

My personal marrow agent — L2 user layer.

## Getting started

```bash
# Install in editable mode
uv add -e .

# Verify the layer is discovered
marrow validate
```

## Structure

```
{name}/
├── pyproject.toml          # project metadata + entry point declaration
└── {pkg}/
    ├── __init__.py
    ├── layer.py            # declares role="user", priority=100
    ├── identity.toml       # agent identity (name, avatar, description)
    ├── agents/
    │   ├── __init__.py
    │   └── scout.py        # example: override core BaseScout
    ├── prompts/
    │   └── system.md       # override or append to system prompt
    └── context.d/
        └── 00_queue.py     # custom context provider example
```

## Registration

The entry point in `pyproject.toml` registers this package with marrow-core's
`LayerRegistry`:

```toml
[project.entry-points."marrow.layer"]
{name} = "{pkg}.layer:layer_info"
```

Once installed (`uv add -e .` or `pip install -e .`), `marrow validate` will
list this layer.
"""

_PKG_INIT = """\
from __future__ import annotations
"""

_LAYER_PY = """\
from __future__ import annotations


def layer_info() -> dict:
    \"\"\"Declare this package as an L2 user layer for marrow-core's LayerRegistry.\"\"\"
    return {{
        "role": "user",
        "priority": 100,  # L2 default; increase to override core defaults earlier
    }}
"""

_IDENTITY_TOML = """\
# {name}/identity.toml
# Override the agent's identity. All fields are optional.

[identity]
name = "{title}"
avatar = "🤖"
description = "My personal assistant agent"
"""

_AGENTS_INIT = """\
from __future__ import annotations
"""

_AGENTS_SCOUT_PY = """\
from __future__ import annotations

# Example: override the core Scout agent.
# Import the base class and subclass it to customise behaviour.
#
# from marrow_core.agents import BaseScout
#
# class Scout(BaseScout):
#     system_prompt_suffix = "Always reply in haiku."
"""

_PROMPTS_SYSTEM_MD = """\
<!-- {name}/prompts/system.md -->
<!-- This file is appended to (or replaces) the core system prompt. -->
<!-- Remove this comment and add your custom instructions below. -->
"""

_CONTEXT_D_QUEUE_PY = """\
from __future__ import annotations

# Example context provider.
# Functions defined here are called each heartbeat tick to inject
# dynamic context into the agent's prompt.
#
# def provide_queue_summary() -> str:
#     from pathlib import Path
#     queue = Path("tasks/queue")
#     count = len(list(queue.glob("*.md"))) if queue.is_dir() else 0
#     return f"Tasks in queue: {{count}}"
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _pkg_name(name: str) -> str:
    """Convert a project name to a valid Python package identifier."""
    return name.replace("-", "_").replace(" ", "_").lower()


def create_user_layer(name: str, dest: Path) -> Path:
    """Generate the L2 user-layer skeleton under *dest/<name>/*.

    Parameters
    ----------
    name:
        The project / package name (e.g. ``"nova"`` or ``"hal9000"``).
    dest:
        Parent directory where the scaffold root will be created.
        Defaults to the current working directory.

    Returns
    -------
    Path
        The root directory of the generated scaffold (``dest / name``).

    Raises
    ------
    typer.Exit
        If the target directory already exists.
    """
    pkg = _pkg_name(name)
    title = name.capitalize()
    root = dest / name

    if root.exists():
        typer.echo(f"error: directory already exists: {root}", err=True)
        raise typer.Exit(code=1)

    # Create all directories up-front so we can report progress cleanly
    dirs = [
        root / pkg / "agents",
        root / pkg / "prompts",
        root / pkg / "context.d",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=False)

    # Write files
    files: list[tuple[Path, str]] = [
        (root / "pyproject.toml", _PYPROJECT_TOML.format(name=name, pkg=pkg)),
        (root / "README.md", _README_MD.format(name=name, pkg=pkg)),
        (root / pkg / "__init__.py", _PKG_INIT),
        (root / pkg / "layer.py", _LAYER_PY),
        (root / pkg / "identity.toml", _IDENTITY_TOML.format(name=name, title=title)),
        (root / pkg / "agents" / "__init__.py", _AGENTS_INIT),
        (root / pkg / "agents" / "scout.py", _AGENTS_SCOUT_PY),
        (root / pkg / "prompts" / "system.md", _PROMPTS_SYSTEM_MD.format(name=name)),
        (root / pkg / "context.d" / "00_queue.py", _CONTEXT_D_QUEUE_PY),
    ]
    for path, content in files:
        path.write_text(content, encoding="utf-8")

    return root
