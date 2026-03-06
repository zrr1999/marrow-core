"""Tests for marrow_core.scaffold — marrow init user scaffold generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from marrow_core.scaffold import _pkg_name, create_user_layer

# ---------------------------------------------------------------------------
# _pkg_name helper
# ---------------------------------------------------------------------------


class TestPkgName:
    def test_simple(self) -> None:
        assert _pkg_name("nova") == "nova"

    def test_hyphen_to_underscore(self) -> None:
        assert _pkg_name("my-agent") == "my_agent"

    def test_space_to_underscore(self) -> None:
        assert _pkg_name("my agent") == "my_agent"

    def test_uppercase_lowered(self) -> None:
        assert _pkg_name("Nova") == "nova"

    def test_mixed(self) -> None:
        assert _pkg_name("My-Cool Agent") == "my_cool_agent"


# ---------------------------------------------------------------------------
# create_user_layer
# ---------------------------------------------------------------------------


class TestCreateUserLayer:
    def test_creates_root_directory(self, tmp_path: Path) -> None:
        root = create_user_layer("nova", tmp_path)
        assert root.is_dir()
        assert root.name == "nova"

    def test_creates_package_subdirectory(self, tmp_path: Path) -> None:
        root = create_user_layer("nova", tmp_path)
        assert (root / "nova").is_dir()

    def test_creates_required_files(self, tmp_path: Path) -> None:
        root = create_user_layer("nova", tmp_path)
        expected_files = [
            "pyproject.toml",
            "README.md",
            "nova/__init__.py",
            "nova/layer.py",
            "nova/identity.toml",
            "nova/agents/__init__.py",
            "nova/agents/scout.py",
            "nova/prompts/system.md",
            "nova/context.d/00_queue.py",
        ]
        for rel in expected_files:
            assert (root / rel).is_file(), f"Missing: {rel}"

    def test_hyphenated_name_pkg(self, tmp_path: Path) -> None:
        """Project name with hyphens should use underscore-based package dir."""
        root = create_user_layer("hal-9000", tmp_path)
        assert (root / "hal_9000" / "layer.py").is_file()

    def test_pyproject_contains_name(self, tmp_path: Path) -> None:
        root = create_user_layer("nova", tmp_path)
        content = (root / "pyproject.toml").read_text()
        assert 'name = "nova"' in content

    def test_pyproject_entry_point(self, tmp_path: Path) -> None:
        root = create_user_layer("nova", tmp_path)
        content = (root / "pyproject.toml").read_text()
        assert '[project.entry-points."marrow.layer"]' in content
        assert "nova.layer:layer_info" in content

    def test_layer_py_returns_user_role(self, tmp_path: Path) -> None:
        root = create_user_layer("nova", tmp_path)
        content = (root / "nova" / "layer.py").read_text()
        assert '"role": "user"' in content
        assert '"priority": 100' in content

    def test_identity_toml_contains_name(self, tmp_path: Path) -> None:
        root = create_user_layer("nova", tmp_path)
        content = (root / "nova" / "identity.toml").read_text()
        assert "Nova" in content  # capitalised title

    def test_readme_contains_name(self, tmp_path: Path) -> None:
        root = create_user_layer("nova", tmp_path)
        content = (root / "README.md").read_text()
        assert "nova" in content

    def test_readme_contains_next_steps(self, tmp_path: Path) -> None:
        root = create_user_layer("nova", tmp_path)
        content = (root / "README.md").read_text()
        assert "marrow validate" in content

    def test_raises_if_dir_exists(self, tmp_path: Path) -> None:
        """Re-running should refuse to overwrite."""
        import typer

        create_user_layer("nova", tmp_path)
        with pytest.raises(typer.Exit):
            create_user_layer("nova", tmp_path)

    def test_returns_path_to_root(self, tmp_path: Path) -> None:
        root = create_user_layer("nova", tmp_path)
        assert root == tmp_path / "nova"

    def test_files_are_utf8(self, tmp_path: Path) -> None:
        root = create_user_layer("nova", tmp_path)
        for path in root.rglob("*"):
            if path.is_file():
                path.read_text(encoding="utf-8")  # should not raise

    def test_layer_py_valid_python(self, tmp_path: Path) -> None:
        import ast

        root = create_user_layer("nova", tmp_path)
        src = (root / "nova" / "layer.py").read_text()
        ast.parse(src)  # should not raise

    def test_pyproject_valid_toml(self, tmp_path: Path) -> None:
        import tomllib

        root = create_user_layer("nova", tmp_path)
        content = (root / "pyproject.toml").read_bytes()
        tomllib.loads(content.decode())  # should not raise

    def test_hyphenated_project_entry_point(self, tmp_path: Path) -> None:
        """Entry point should use underscore package name."""
        root = create_user_layer("my-agent", tmp_path)
        content = (root / "pyproject.toml").read_text()
        assert "my_agent.layer:layer_info" in content

    def test_multiple_scaffolds_in_same_dest(self, tmp_path: Path) -> None:
        """Creating two different packages in the same dest should succeed."""
        root_a = create_user_layer("alpha", tmp_path)
        root_b = create_user_layer("beta", tmp_path)
        assert root_a.is_dir()
        assert root_b.is_dir()


# ---------------------------------------------------------------------------
# CLI integration — test init user command via typer CliRunner
# ---------------------------------------------------------------------------


class TestInitUserCLI:
    def test_cli_creates_scaffold(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from marrow_core.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["init", "user", "--name", "nova", "--dest", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "nova" / "pyproject.toml").is_file()

    def test_cli_prints_next_steps(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from marrow_core.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["init", "user", "--name", "nova", "--dest", str(tmp_path)])
        assert "marrow validate" in result.output

    def test_cli_fails_if_dir_exists(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from marrow_core.cli import app

        runner = CliRunner()
        runner.invoke(app, ["init", "user", "--name", "nova", "--dest", str(tmp_path)])
        result = runner.invoke(app, ["init", "user", "--name", "nova", "--dest", str(tmp_path)])
        assert result.exit_code != 0

    def test_cli_requires_name(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from marrow_core.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["init", "user", "--dest", str(tmp_path)])
        assert result.exit_code != 0
