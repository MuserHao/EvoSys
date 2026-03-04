"""Smoke tests for the CLI."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
        result = runner.invoke(
            app,
            ["extract", "https://example.com", "-s", "@nonexistent.json"],
        )
        assert result.exit_code == 1
        assert "not found" in result.output


class TestReflect:
    def test_empty_db_shows_no_patterns(self):
        result = runner.invoke(
            app,
            ["reflect", "--db", "sqlite+aiosqlite:///:memory:"],
        )
        assert result.exit_code == 0
        assert "No patterns found" in result.output


class TestEvolve:
    def test_empty_db_shows_no_patterns(self):
        result = runner.invoke(
            app,
            ["evolve", "--db", "sqlite+aiosqlite:///:memory:"],
        )
        assert result.exit_code == 0
        assert "Patterns found" in result.output
        assert "0" in result.output


class TestRun:
    def test_run_pretty_output(self):
        """CLI `run` command returns the agent answer in pretty format.
        The agent and all LLM calls are mocked so no network is needed."""
        from evosys.agents.agent import AgentResult

        fake_result = AgentResult(
            answer="42",
            total_tokens=5,
            total_latency_ms=10.0,
            session_id="cli-test-session",
            iterations=1,
        )

        with patch("evosys.cli._run_agent", new=AsyncMock(return_value=fake_result)):
            result = runner.invoke(
                app,
                ["run", "What is 6 * 7?", "--db", "sqlite+aiosqlite:///:memory:"],
            )

        assert result.exit_code == 0
        assert "42" in result.output

    def test_run_json_output(self):
        """CLI `run --format json` returns machine-readable output."""
        import json as json_mod

        from evosys.agents.agent import AgentResult

        fake_result = AgentResult(
            answer="Paris",
            total_tokens=8,
            total_latency_ms=20.0,
            session_id="json-session",
            iterations=2,
        )

        with patch("evosys.cli._run_agent", new=AsyncMock(return_value=fake_result)):
            result = runner.invoke(
                app,
                ["run", "Capital of France?", "--format", "json",
                 "--db", "sqlite+aiosqlite:///:memory:"],
            )

        assert result.exit_code == 0
        data = json_mod.loads(result.output)
        assert data["answer"] == "Paris"
        assert data["iterations"] == 2
        assert "session_id" in data

