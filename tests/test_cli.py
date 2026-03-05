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

    def test_system_prompt_mentions_tools(self):
        """Default system prompt should tell the agent about its capabilities."""
        from evosys.config import EvoSysConfig
        prompt = EvoSysConfig().agent_system_prompt
        assert "python" in prompt.lower()
        assert "file" in prompt.lower()
        assert "shell" in prompt.lower() or "command" in prompt.lower()


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

    def test_run_passes_tools_enabled_by_default(self):
        """CLI run enables shell and python_eval by default."""
        from unittest.mock import patch

        from evosys.agents.agent import AgentResult
        from evosys.config import EvoSysConfig

        fake_result = AgentResult(
            answer="done",
            total_tokens=1,
            total_latency_ms=5.0,
            session_id="s",
            iterations=1,
        )

        captured_cfg: list[EvoSysConfig] = []

        async def fake_run_agent(cfg: EvoSysConfig, task: str):
            captured_cfg.append(cfg)
            return fake_result

        with patch("evosys.cli._run_agent", side_effect=fake_run_agent):
            result = runner.invoke(
                app,
                ["run", "do something", "--db", "sqlite+aiosqlite:///:memory:"],
            )

        assert result.exit_code == 0
        assert len(captured_cfg) == 1
        assert captured_cfg[0].enable_shell_tool is True
        assert captured_cfg[0].enable_python_eval_tool is True

    def test_run_no_shell_disables_shell(self):
        """--no-shell flag disables shell tool."""
        from evosys.agents.agent import AgentResult
        from evosys.config import EvoSysConfig

        fake_result = AgentResult(answer="ok", total_tokens=1,
                                   total_latency_ms=1.0, session_id="s", iterations=1)
        captured_cfg: list[EvoSysConfig] = []

        async def fake_run_agent(cfg: EvoSysConfig, task: str):
            captured_cfg.append(cfg)
            return fake_result

        from unittest.mock import patch
        with patch("evosys.cli._run_agent", side_effect=fake_run_agent):
            runner.invoke(app, ["run", "task", "--no-shell",
                                "--db", "sqlite+aiosqlite:///:memory:"])

        assert captured_cfg[0].enable_shell_tool is False
        assert captured_cfg[0].enable_python_eval_tool is True  # still on

    def test_run_no_python_disables_python_eval(self):
        """--no-python flag disables python_eval tool."""
        from evosys.agents.agent import AgentResult
        from evosys.config import EvoSysConfig

        fake_result = AgentResult(answer="ok", total_tokens=1,
                                   total_latency_ms=1.0, session_id="s", iterations=1)
        captured_cfg: list[EvoSysConfig] = []

        async def fake_run_agent(cfg: EvoSysConfig, task: str):
            captured_cfg.append(cfg)
            return fake_result

        from unittest.mock import patch
        with patch("evosys.cli._run_agent", side_effect=fake_run_agent):
            runner.invoke(app, ["run", "task", "--no-python",
                                "--db", "sqlite+aiosqlite:///:memory:"])

        assert captured_cfg[0].enable_python_eval_tool is False
        assert captured_cfg[0].enable_shell_tool is True  # still on

