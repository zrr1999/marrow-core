"""Layer discovery via Python entry points.

Implements the three-layer architecture from Issue #17:
  L1 (priority 0)   — core (marrow-core itself, immutable)
  L2 (priority 100) — user / site extensions (e.g. marrow-bot, agent-caster roles)
  L3 (priority 200+) — per-agent overrides (loaded from agent workspace at runtime)

Any Python package that wants to register a layer adds to its pyproject.toml:

    [project.entry-points."marrow.layer"]
    my-layer = "my_package.layer:layer_info"

where ``layer_info`` is a zero-argument callable that returns a dict with keys:

    name     (str)  — human-readable layer name (falls back to entry-point name)
    priority (int)  — sort order; lower = applied first (default: 100)
    path     (str)  — optional absolute path to the layer root
    description (str) — optional one-line description

Usage::

    from marrow_core.layers import discover

    for layer in discover():
        print(layer["name"], layer["priority"])
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any

# Built-in L1 sentinel — always present, always first.
_CORE_LAYER: dict[str, Any] = {
    "name": "core",
    "priority": 0,
    "description": "marrow-core built-in layer (immutable, root-owned)",
    "source": "builtin",
}


def discover(*, include_core: bool = True) -> list[dict[str, Any]]:
    """Return all registered layers sorted by priority (ascending).

    Parameters
    ----------
    include_core:
        When *True* (default), the built-in L1 core layer is prepended
        at priority 0 even if no package registers it via entry points.

    Returns
    -------
    list[dict]
        Each dict has at minimum ``name`` (str) and ``priority`` (int).
        Additional keys (``path``, ``description``, ``source``) may be present
        depending on what each layer's ``layer_info()`` callable returns.
    """
    eps = entry_points(group="marrow.layer")
    layers: list[dict[str, Any]] = []

    for ep in eps:
        try:
            info: dict[str, Any] = ep.load()()
        except Exception as exc:
            # A broken layer registration must never crash the scheduler.
            info = {
                "name": ep.name,
                "priority": 100,
                "description": f"[load error: {exc}]",
                "source": ep.value,
            }
        if not isinstance(info, dict):
            info = {"name": ep.name, "priority": 100, "source": ep.value}
        info.setdefault("name", ep.name)
        info.setdefault("priority", 100)
        info.setdefault("source", ep.value)
        layers.append(info)

    layers.sort(key=lambda x: (x["priority"], x["name"]))

    if include_core and not any(lay.get("priority", 100) == 0 for lay in layers):
        layers.insert(0, dict(_CORE_LAYER))

    return layers
