"""Smoke tests for the CLI."""

from __future__ import annotations

from typer.testing import CliRunner

from evosys.cli import app

runner = CliRunner()


class TestInfo:
    def test_shows_version(self):
        result = runner.invoke(app, ["info"])
        assert result.exit_code == 0
        assert "EvoSys" in result.output
        assert "0.1.0" in result.output


class TestSkillsList:
    def test_lists_skills(self):
        result = runner.invoke(app, ["skills", "list"])
        assert result.exit_code == 0
        # Rich table may truncate names; check for partial match
        assert "ycombinato" in result.output
        assert "wikipedia" in result.output

    def test_active_filter(self):
        result = runner.invoke(app, ["skills", "list", "--active"])
        assert result.exit_code == 0
        assert "ycombinato" in result.output


class TestExtractValidation:
    def test_missing_schema_file(self):
        result = runner.invoke(app, ["extract", "https://example.com", "-s", "@nonexistent.json"])
        assert result.exit_code == 1
        assert "not found" in result.output
