"""Smoke tests for the CLI."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from evosys.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# evosys --version
# ---------------------------------------------------------------------------

class TestVersion:
    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "evosys" in result.output
        assert "0.1.0" in result.output

    def test_version_short_flag(self):
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0
        assert "evosys" in result.output
        assert "0.1.0" in result.output


# ---------------------------------------------------------------------------
# evosys info (flat, no admin prefix)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# evosys skills (flat, no admin prefix)
# ---------------------------------------------------------------------------

class TestSkillsList:
    def test_lists_skills(self):
        result = runner.invoke(app, ["skills", "list"])
        assert result.exit_code == 0
        assert "ycombinato" in result.output
        assert "wikipedia" in result.output

    def test_active_filter(self):
        result = runner.invoke(app, ["skills", "list", "--active"])
        assert result.exit_code == 0
        assert "ycombinato" in result.output


# ---------------------------------------------------------------------------
# evosys reflect / evolve (flat, no admin prefix)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# One-shot mode (evosys "task")
# ---------------------------------------------------------------------------

class TestOneShot:
    def _fake_result(self, answer="42"):
        from evosys.agents.agent import AgentResult
        return AgentResult(
            answer=answer,
            total_tokens=5,
            total_latency_ms=10.0,
            session_id="cli-test-session",
            iterations=1,
        )

    def test_oneshot_pretty_output(self):
        with patch("evosys.cli._run_agent", new=AsyncMock(return_value=self._fake_result())):
            result = runner.invoke(
                app,
                ["What is 6 * 7?", "--db", "sqlite+aiosqlite:///:memory:"],
            )
        assert result.exit_code == 0
        assert "42" in result.output

    def test_oneshot_json_output(self):
        import json as json_mod

        from evosys.agents.agent import AgentResult

        fake = AgentResult(
            answer="Paris",
            total_tokens=8,
            total_latency_ms=20.0,
            session_id="json-session",
            iterations=2,
        )

        with patch("evosys.cli._run_agent", new=AsyncMock(return_value=fake)):
            result = runner.invoke(
                app,
                ["--format", "json", "Capital of France?",
                 "--db", "sqlite+aiosqlite:///:memory:"],
            )
        assert result.exit_code == 0
        data = json_mod.loads(result.output)
        assert data["answer"] == "Paris"
        assert data["iterations"] == 2
        assert "session_id" in data

    def test_oneshot_tools_enabled_by_default(self):
        from evosys.config import EvoSysConfig

        captured_cfg: list[EvoSysConfig] = []

        async def fake_run_agent(cfg: EvoSysConfig, task: str, **_kw: object):
            captured_cfg.append(cfg)
            return self._fake_result("done")

        with patch("evosys.cli._run_agent", side_effect=fake_run_agent):
            result = runner.invoke(
                app,
                ["do something", "--db", "sqlite+aiosqlite:///:memory:"],
            )
        assert result.exit_code == 0
        assert len(captured_cfg) == 1
        assert captured_cfg[0].enable_shell_tool is True
        assert captured_cfg[0].enable_python_eval_tool is True

    def test_no_shell_disables_shell(self):
        from evosys.config import EvoSysConfig

        captured_cfg: list[EvoSysConfig] = []

        async def fake_run_agent(cfg: EvoSysConfig, task: str, **_kw: object):
            captured_cfg.append(cfg)
            return self._fake_result("ok")

        with patch("evosys.cli._run_agent", side_effect=fake_run_agent):
            runner.invoke(
                app,
                ["--no-shell", "task", "--db", "sqlite+aiosqlite:///:memory:"],
            )
        assert captured_cfg[0].enable_shell_tool is False
        assert captured_cfg[0].enable_python_eval_tool is True

    def test_no_python_disables_python_eval(self):
        from evosys.config import EvoSysConfig

        captured_cfg: list[EvoSysConfig] = []

        async def fake_run_agent(cfg: EvoSysConfig, task: str, **_kw: object):
            captured_cfg.append(cfg)
            return self._fake_result("ok")

        with patch("evosys.cli._run_agent", side_effect=fake_run_agent):
            runner.invoke(
                app,
                ["--no-python", "task", "--db", "sqlite+aiosqlite:///:memory:"],
            )
        assert captured_cfg[0].enable_python_eval_tool is False
        assert captured_cfg[0].enable_shell_tool is True

    def test_multi_word_task(self):
        """Multiple words are joined into a single task string."""
        captured_tasks: list[str] = []

        async def fake_run_agent(cfg, task: str, **_kw):
            captured_tasks.append(task)
            return self._fake_result("done")

        with patch("evosys.cli._run_agent", side_effect=fake_run_agent):
            result = runner.invoke(
                app,
                ["summarize", "this", "repo", "--db", "sqlite+aiosqlite:///:memory:"],
            )
        assert result.exit_code == 0
        assert captured_tasks[0] == "summarize this repo"

    def test_options_before_task(self):
        """Global options can precede the task string."""
        captured_tasks: list[str] = []

        async def fake_run_agent(cfg, task: str, **_kw):
            captured_tasks.append(task)
            return self._fake_result("done")

        with patch("evosys.cli._run_agent", side_effect=fake_run_agent):
            result = runner.invoke(
                app,
                ["--db", "sqlite+aiosqlite:///:memory:", "--max-iter", "5",
                 "what is 2+2"],
            )
        assert result.exit_code == 0
        assert captured_tasks[0] == "what is 2+2"


# ---------------------------------------------------------------------------
# ``--`` separator forces task mode
# ---------------------------------------------------------------------------

class TestDoubleDashSeparator:
    def _fake_result(self, answer="done"):
        from evosys.agents.agent import AgentResult
        return AgentResult(
            answer=answer,
            total_tokens=5,
            total_latency_ms=10.0,
            session_id="sep-test",
            iterations=1,
        )

    def test_double_dash_forces_task_mode(self):
        """``evosys -- serve me a joke`` should be a task, not the serve command."""
        captured_tasks: list[str] = []

        async def fake_run_agent(cfg, task: str, **_kw):
            captured_tasks.append(task)
            return self._fake_result()

        with patch("evosys.cli._run_agent", side_effect=fake_run_agent):
            result = runner.invoke(
                app,
                ["--", "serve", "me", "a", "joke"],
            )
        assert result.exit_code == 0
        assert captured_tasks[0] == "serve me a joke"

    def test_double_dash_with_options_before(self):
        """Options before ``--`` are parsed normally."""
        captured_tasks: list[str] = []

        async def fake_run_agent(cfg, task: str, **_kw):
            captured_tasks.append(task)
            return self._fake_result()

        with patch("evosys.cli._run_agent", side_effect=fake_run_agent):
            result = runner.invoke(
                app,
                ["--db", "sqlite+aiosqlite:///:memory:", "--", "info", "about", "cats"],
            )
        assert result.exit_code == 0
        assert captured_tasks[0] == "info about cats"


# ---------------------------------------------------------------------------
# Chat mode (no args → interactive)
# ---------------------------------------------------------------------------

class TestChatMode:
    def test_no_args_enters_chat(self):
        """Invoking with no args should call _run_chat (chat mode)."""
        with patch("evosys.cli._run_chat", new=AsyncMock()) as mock_chat:
            result = runner.invoke(app, [])
        assert result.exit_code == 0
        mock_chat.assert_called_once()


# ---------------------------------------------------------------------------
# Welcome banner
# ---------------------------------------------------------------------------

class TestWelcomeBanner:
    def test_welcome_shows_key_status(self):
        """Welcome banner should show checkmarks for set keys and X for unset."""
        env = {"ANTHROPIC_API_KEY": "sk-test", "GOOGLE_API_KEY": "", "OPENAI_API_KEY": ""}

        with (
            patch("evosys.cli._run_chat", new=AsyncMock()),
            patch.dict(os.environ, env, clear=False),
            patch.dict(os.environ, {"GOOGLE_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False),
        ):
            # Remove keys that should appear unset
            os.environ.pop("GOOGLE_API_KEY", None)
            os.environ.pop("OPENAI_API_KEY", None)
            result = runner.invoke(app, [])

        assert result.exit_code == 0
        assert "ANTHROPIC_API_KEY" in result.output
        assert "Claude" in result.output
        assert "Gemini" in result.output
        assert "GPT" in result.output

    def test_welcome_warns_when_no_key(self):
        """Warning line when no API keys are set."""
        with (
            patch("evosys.cli._run_chat", new=AsyncMock()),
            patch.dict(
                os.environ,
                {"ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "OPENAI_API_KEY": ""},
                clear=False,
            ),
        ):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            os.environ.pop("OPENAI_API_KEY", None)
            result = runner.invoke(app, [])

        assert result.exit_code == 0
        assert "Warning" in result.output or "No API key" in result.output


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

class TestHelp:
    def test_help_shows_modes(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "serve" in result.output
        # admin should NOT appear (flattened)
        assert "info" in result.output
        assert "evolve" in result.output
        assert "reflect" in result.output
        assert "skills" in result.output

    def test_skills_help(self):
        result = runner.invoke(app, ["skills", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "export" in result.output
        assert "import" in result.output
        assert "search" in result.output
