"""Tests for ClaudeCodeTool and related helpers."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from evosys.config import EvoSysConfig
from evosys.tools.external_agent import (
    ClaudeCodeTool,
    _find_claude_binary,
    _parse_stream_json,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ndjson(*messages: dict) -> bytes:
    """Build NDJSON bytes from message dicts."""
    return b"\n".join(json.dumps(m).encode() for m in messages)


def _make_proc(
    stdout: bytes = b"",
    stderr: bytes = b"",
    returncode: int = 0,
    *,
    hang: bool = False,
) -> AsyncMock:
    """Return a mock Process whose communicate() returns the given data."""
    proc = AsyncMock(spec=asyncio.subprocess.Process)
    proc.returncode = returncode
    if hang:
        async def _hang() -> tuple[bytes, bytes]:
            await asyncio.sleep(9999)
            return stdout, stderr  # pragma: no cover
        proc.communicate = _hang
    else:
        proc.communicate.return_value = (stdout, stderr)
    proc.kill = MagicMock()
    proc.wait = AsyncMock()
    return proc


# ---------------------------------------------------------------------------
# TestStreamJsonParsing
# ---------------------------------------------------------------------------


class TestStreamJsonParsing:
    """Tests for _parse_stream_json helper."""

    def test_parses_result_and_steps(self):
        raw = "\n".join([
            json.dumps({"type": "assistant", "content": "thinking..."}),
            json.dumps({"type": "tool_use", "tool": "Bash", "input": "ls"}),
            json.dumps({"type": "tool_result", "tool": "Bash", "output": "file.py"}),
            json.dumps({"type": "result", "result": "Done.", "session_id": "s1", "cost_usd": 0.02}),
        ])
        final, steps = _parse_stream_json(raw)
        assert final["result"] == "Done."
        assert final["session_id"] == "s1"
        assert len(steps) == 3

    def test_empty_input(self):
        final, steps = _parse_stream_json("")
        assert final == {}
        assert steps == []

    def test_invalid_json_lines_skipped(self):
        raw = "not json\n{\"type\": \"result\", \"result\": \"ok\"}\nalso bad"
        final, steps = _parse_stream_json(raw)
        assert final["result"] == "ok"
        assert steps == []

    def test_no_result_message(self):
        raw = json.dumps({"type": "assistant", "content": "hello"})
        final, steps = _parse_stream_json(raw)
        assert final == {}
        assert len(steps) == 1
        assert steps[0]["type"] == "assistant"


# ---------------------------------------------------------------------------
# TestIntermediateStepLogging
# ---------------------------------------------------------------------------


class TestIntermediateStepLogging:
    """Tests for intermediate step trajectory logging."""

    @pytest.mark.asyncio
    async def test_logs_intermediate_steps(self):
        mock_store = AsyncMock()
        mock_store.save = AsyncMock()
        from evosys.trajectory.logger import TrajectoryLogger
        logger = TrajectoryLogger(mock_store)

        ndjson_output = _ndjson(
            {"type": "tool_use", "tool": "Bash", "input": "ls"},
            {"type": "tool_result", "tool": "Bash", "output": "ok"},
            {"type": "result", "result": "Done.", "session_id": "s1", "cost_usd": 0.01},
        )
        proc = _make_proc(stdout=ndjson_output)
        tool = ClaudeCodeTool("/usr/bin/claude", trajectory_logger=logger)

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await tool(task="test task")

        assert result["answer"] == "Done."
        assert len(result["internal_steps"]) == 2
        # Logger should have been called for each intermediate step
        assert mock_store.save.call_count == 2
        saved = mock_store.save.call_args_list[0][0][0]
        assert saved.action_name.startswith("tool:claude_code:")

    @pytest.mark.asyncio
    async def test_no_logging_without_logger(self):
        ndjson_output = _ndjson(
            {"type": "tool_use", "tool": "Read"},
            {"type": "result", "result": "ok"},
        )
        proc = _make_proc(stdout=ndjson_output)
        tool = ClaudeCodeTool("/usr/bin/claude")  # no trajectory_logger

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await tool(task="test")

        assert result["answer"] == "ok"
        assert len(result["internal_steps"]) == 1


# ---------------------------------------------------------------------------
# TestClaudeCodeTool
# ---------------------------------------------------------------------------

class TestClaudeCodeTool:
    """Unit tests for ClaudeCodeTool.__call__."""

    def _tool(self, **kw: object) -> ClaudeCodeTool:
        return ClaudeCodeTool(claude_path="/usr/bin/claude", **kw)

    @pytest.mark.asyncio
    async def test_successful_stream_json_output(self):
        ndjson_output = _ndjson(
            {"type": "assistant", "content": "Working on it..."},
            {
                "type": "result",
                "result": "Files listed successfully.",
                "session_id": "sess-abc",
                "cost_usd": 0.01,
            },
        )
        proc = _make_proc(stdout=ndjson_output)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await self._tool()(task="list files")
        assert result["answer"] == "Files listed successfully."
        assert result["session_id"] == "sess-abc"
        assert result["cost_usd"] == 0.01
        assert result["return_code"] == 0
        assert isinstance(result["internal_steps"], list)

    @pytest.mark.asyncio
    async def test_fallback_to_single_json(self):
        """If stream-json isn't available, fall back to single JSON."""
        payload = {"result": "ok", "session_id": "s1", "cost_usd": 0.0}
        proc = _make_proc(stdout=json.dumps(payload).encode())
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await self._tool()(task="test")
        assert result["answer"] == "ok"
        assert result["internal_steps"] == []

    @pytest.mark.asyncio
    async def test_fallback_to_text_on_invalid_json(self):
        proc = _make_proc(stdout=b"plain text output")
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await self._tool()(task="do something")
        assert result["answer"] == "plain text output"
        assert result["return_code"] == 0

    @pytest.mark.asyncio
    async def test_timeout_kills_process(self):
        proc = _make_proc(hang=True)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await self._tool(timeout_s=0.05)(task="slow task")
        assert "timed out" in result["error"]
        proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_nonzero_exit_code(self):
        proc = _make_proc(stderr=b"something went wrong", returncode=1)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await self._tool()(task="bad task")
        assert "error" in result
        assert "exit 1" in result["error"]
        assert "something went wrong" in result["error"]

    @pytest.mark.asyncio
    async def test_empty_task_returns_error(self):
        result = await self._tool()(task="")
        assert result == {"error": "task must not be empty"}

    @pytest.mark.asyncio
    async def test_working_dir_forwarded(self):
        proc = _make_proc(stdout=_ndjson({"type": "result", "result": "ok"}))
        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await self._tool()(task="test", working_dir="/tmp")
        _, call_kwargs = mock_exec.call_args
        assert call_kwargs["cwd"] == "/tmp"

    @pytest.mark.asyncio
    async def test_model_flag_added(self):
        proc = _make_proc(stdout=_ndjson({"type": "result", "result": "ok"}))
        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await self._tool()(task="test", model="opus")
        args = mock_exec.call_args[0]
        assert "--model" in args
        idx = args.index("--model")
        assert args[idx + 1] == "opus"

    @pytest.mark.asyncio
    async def test_budget_flag_added(self):
        proc = _make_proc(stdout=_ndjson({"type": "result", "result": "ok"}))
        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await self._tool()(task="test", max_budget_usd=1.5)
        args = mock_exec.call_args[0]
        assert "--max-budget-usd" in args
        idx = args.index("--max-budget-usd")
        assert args[idx + 1] == "1.5"

    @pytest.mark.asyncio
    async def test_allowed_tools_flag(self):
        proc = _make_proc(stdout=_ndjson({"type": "result", "result": "ok"}))
        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await self._tool()(task="test", allowed_tools="Bash,Read,Write")
        args = mock_exec.call_args[0]
        assert "--allowed-tools" in args
        idx = args.index("--allowed-tools")
        assert args[idx + 1] == "Bash,Read,Write"

    @pytest.mark.asyncio
    async def test_uses_stream_json_format(self):
        proc = _make_proc(stdout=_ndjson({"type": "result", "result": "ok"}))
        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await self._tool()(task="test")
        args = mock_exec.call_args[0]
        assert "--output-format" in args
        idx = args.index("--output-format")
        assert args[idx + 1] == "stream-json"

    def test_to_openai_tool_schema(self):
        schema = self._tool().to_openai_tool()
        assert schema["type"] == "function"
        fn = schema["function"]
        assert fn["name"] == "claude_code"
        props = fn["parameters"]["properties"]
        assert "task" in props
        assert "working_dir" in props
        assert "model" in props
        assert "allowed_tools" in props
        assert "max_budget_usd" in props
        assert fn["parameters"]["required"] == ["task"]


# ---------------------------------------------------------------------------
# TestFindClaudeBinary
# ---------------------------------------------------------------------------

class TestFindClaudeBinary:
    def test_found(self):
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            assert _find_claude_binary() == "/usr/local/bin/claude"

    def test_not_found(self):
        with patch("shutil.which", return_value=None):
            assert _find_claude_binary() is None


# ---------------------------------------------------------------------------
# TestConfig
# ---------------------------------------------------------------------------

class TestClaudeCodeConfig:
    def test_defaults(self):
        cfg = EvoSysConfig()
        assert cfg.enable_claude_code is False
        assert cfg.claude_code_path == ""
        assert cfg.claude_code_timeout_s == 300.0
        assert cfg.claude_code_max_budget_usd == 0.0
        assert cfg.claude_code_model == ""

    def test_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("EVOSYS_ENABLE_CLAUDE_CODE", "1")
        monkeypatch.setenv("EVOSYS_CLAUDE_CODE_PATH", "/opt/claude")
        monkeypatch.setenv("EVOSYS_CLAUDE_CODE_TIMEOUT_S", "120")
        monkeypatch.setenv("EVOSYS_CLAUDE_CODE_MAX_BUDGET_USD", "5.0")
        monkeypatch.setenv("EVOSYS_CLAUDE_CODE_MODEL", "opus")
        cfg = EvoSysConfig.from_env()
        assert cfg.enable_claude_code is True
        assert cfg.claude_code_path == "/opt/claude"
        assert cfg.claude_code_timeout_s == 120.0
        assert cfg.claude_code_max_budget_usd == 5.0
        assert cfg.claude_code_model == "opus"
