"""Tests for CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ez_agent.cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestCLIVersion:
    """Test version command."""

    def test_version_flag(self, runner: CliRunner):
        """Test --version flag."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "EZ-Agent version" in result.stdout


class TestValidateCommand:
    """Test validate command."""

    def test_validate_valid_config(self, runner: CliRunner, config_file_path: Path):
        """Test validating a valid config."""
        result = runner.invoke(app, ["validate", "-c", str(config_file_path)])

        assert result.exit_code == 0
        assert "valid" in result.stdout.lower()

    def test_validate_invalid_config(self, runner: CliRunner, tmp_path: Path):
        """Test validating an invalid config."""
        invalid_config = tmp_path / "invalid.yaml"
        invalid_config.write_text("name: 123\n")

        result = runner.invoke(app, ["validate", "-c", str(invalid_config)])

        # Invalid config should cause non-zero exit
        assert result.exit_code == 1

    def test_validate_nonexistent_file(self, runner: CliRunner, tmp_path: Path):
        """Test validating nonexistent file."""
        result = runner.invoke(app, ["validate", "-c", str(tmp_path / "nope.yaml")])

        # Typer exits with code 2 for missing files
        assert result.exit_code != 0


class TestInitCommand:
    """Test init command."""

    def test_init_with_name(self, runner: CliRunner, tmp_path: Path):
        """Test init with provided name."""
        result = runner.invoke(
            app,
            ["init", "-o", str(tmp_path), "-n", "TestAgent"],
            input="\n\n\n1\n\ny\ny\ny\n\n",  # Accept defaults
        )

        # Check config file was created
        config_files = list(tmp_path.glob("*.yaml"))
        assert len(config_files) == 1
        assert "testagent" in config_files[0].name.lower()
