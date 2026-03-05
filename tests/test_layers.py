"""Tests for marrow_core.layers."""

from __future__ import annotations

from importlib.metadata import EntryPoint
from unittest.mock import MagicMock, patch

from marrow_core.layers import _CORE_LAYER, discover

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_ep(name: str, value: str, load_return: object) -> MagicMock:
    """Build a mock EntryPoint whose .load()() returns *load_return*."""
    ep = MagicMock(spec=EntryPoint)
    ep.name = name
    ep.value = value
    ep.load.return_value = MagicMock(return_value=load_return)
    return ep


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDiscoverNoEntryPoints:
    """When no packages register marrow.layer entry points."""

    def test_returns_core_layer_by_default(self):
        with patch("marrow_core.layers.entry_points", return_value=[]):
            result = discover()
        assert len(result) == 1
        assert result[0]["name"] == "core"
        assert result[0]["priority"] == 0

    def test_exclude_core(self):
        with patch("marrow_core.layers.entry_points", return_value=[]):
            result = discover(include_core=False)
        assert result == []


class TestDiscoverWithEntryPoints:
    """Happy-path: one or more valid entry point registrations."""

    def test_single_layer_sorted_after_core(self):
        ep = _mock_ep(
            "my-layer", "my_pkg.layer:layer_info", {"priority": 100, "description": "test"}
        )
        with patch("marrow_core.layers.entry_points", return_value=[ep]):
            result = discover()
        assert result[0]["name"] == "core"
        assert result[1]["name"] == "my-layer"
        assert result[1]["priority"] == 100

    def test_priority_ordering(self):
        eps = [
            _mock_ep("l3-agent", "a:f", {"priority": 200}),
            _mock_ep("l2-user", "b:f", {"priority": 100}),
        ]
        with patch("marrow_core.layers.entry_points", return_value=eps):
            result = discover()
        names = [r["name"] for r in result]
        assert names == ["core", "l2-user", "l3-agent"]

    def test_name_fallback_to_ep_name(self):
        ep = _mock_ep("fallback-name", "x:f", {"priority": 50})
        # layer_info returns a dict without "name" key
        with patch("marrow_core.layers.entry_points", return_value=[ep]):
            result = discover()
        # priority 50 < core (0) is not less than 0, so core still first
        user_layer = next(r for r in result if r["name"] != "core")
        assert user_layer["name"] == "fallback-name"

    def test_source_field_set(self):
        ep = _mock_ep("my-layer", "my_pkg.layer:layer_info", {"priority": 100})
        with patch("marrow_core.layers.entry_points", return_value=[ep]):
            result = discover()
        user_layer = next(r for r in result if r["name"] != "core")
        assert user_layer["source"] == "my_pkg.layer:layer_info"

    def test_core_not_duplicated_when_ep_registers_priority_0(self):
        ep = _mock_ep("custom-core", "pkg:f", {"priority": 0, "name": "custom-core"})
        with patch("marrow_core.layers.entry_points", return_value=[ep]):
            result = discover()
        # Since an ep registered priority=0, include_core sentinel is suppressed
        assert len([r for r in result if r["priority"] == 0]) == 1

    def test_alphabetical_tiebreak(self):
        eps = [
            _mock_ep("z-layer", "z:f", {"priority": 100}),
            _mock_ep("a-layer", "a:f", {"priority": 100}),
        ]
        with patch("marrow_core.layers.entry_points", return_value=eps):
            result = discover(include_core=False)
        assert result[0]["name"] == "a-layer"
        assert result[1]["name"] == "z-layer"


class TestDiscoverRobustness:
    """Broken entry points must never crash discover()."""

    def test_load_error_produces_error_description(self):
        ep = MagicMock(spec=EntryPoint)
        ep.name = "broken"
        ep.value = "broken_pkg:bad_func"
        ep.load.side_effect = ImportError("no module named broken_pkg")
        with patch("marrow_core.layers.entry_points", return_value=[ep]):
            result = discover()
        broken = next(r for r in result if r["name"] == "broken")
        assert "load error" in broken["description"]

    def test_load_callable_raises(self):
        ep = MagicMock(spec=EntryPoint)
        ep.name = "raises"
        ep.value = "pkg:raises"
        ep.load.return_value = MagicMock(side_effect=RuntimeError("boom"))
        with patch("marrow_core.layers.entry_points", return_value=[ep]):
            result = discover()
        broken = next(r for r in result if r["name"] == "raises")
        assert "load error" in broken["description"]

    def test_non_dict_return_handled(self):
        ep = _mock_ep("bad-return", "pkg:f", "not a dict")
        with patch("marrow_core.layers.entry_points", return_value=[ep]):
            result = discover()
        bad = next(r for r in result if r["name"] == "bad-return")
        assert bad["priority"] == 100


class TestCoreLayerImmutability:
    """Mutations to returned layers must not affect the _CORE_LAYER sentinel."""

    def test_returned_core_is_a_copy(self):
        with patch("marrow_core.layers.entry_points", return_value=[]):
            result = discover()
        result[0]["name"] = "MUTATED"
        assert _CORE_LAYER["name"] == "core"
