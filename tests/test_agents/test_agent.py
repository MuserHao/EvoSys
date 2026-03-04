"""Tests for the general-purpose Agent."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from evosys.agents.agent import Agent, AgentResult
from evosys.core.types import ToolCall
from evosys.llm.client import LLMClient, LLMToolCallResponse
from evosys.skills.registry import SkillRegistry
from evosys.tools.registry import ToolRegistry
from evosys.trajectory.logger import TrajectoryLogger

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeTool:
    def __init__(self, name: str = "test_tool", result: dict[str, object] | None = None) -> None:
        self._name = name
        self._result = result or {"data": "ok"}

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"A fake tool named {self._name}"

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {"input": {"type": "string"}}

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        return self._result

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": self.description,
                "parameters": {"type": "object", "properties": self.parameters_schema},
            },
        }


class _ErrorTool:
    @property
    def name(self) -> str:
        return "error_tool"

    @property
    def description(self) -> str:
        return "Always raises"

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {}

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("tool exploded")

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {"name": "error_tool", "description": "err", "parameters": {}},
        }


def _make_tool_response(
    tool_calls: list[ToolCall] | None = None,
    content: str | None = None,
    tokens: int = 10,
) -> LLMToolCallResponse:
    return LLMToolCallResponse(
        content=content,
        tool_calls=tool_calls or [],
        prompt_tokens=tokens // 2,
        completion_tokens=tokens // 2,
        total_tokens=tokens,
        model="test",
        finish_reason="tool_calls" if tool_calls else "stop",
    )


def _make_stop_response(content: str = "Done.", tokens: int = 10) -> LLMToolCallResponse:
    return _make_tool_response(content=content, tokens=tokens)


def _setup_agent(
    llm_responses: list[LLMToolCallResponse],
    tools: list[object] | None = None,
    max_iterations: int = 20,
) -> Agent:
    """Create an Agent with mocked LLM and trajectory logger."""
    mock_llm = LLMClient(model="test")
    mock_llm.complete_with_tools = AsyncMock(side_effect=llm_responses)  # type: ignore[method-assign]

    sr = SkillRegistry()
    tr = ToolRegistry(sr)
    for t in (tools or []):
        tr.register_external(t)  # type: ignore[arg-type]

    mock_store = AsyncMock()
    mock_store.save = AsyncMock()
    mock_logger = TrajectoryLogger(mock_store)

    return Agent(
        llm=mock_llm,
        tool_registry=tr,
        trajectory_logger=mock_logger,
        max_iterations=max_iterations,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAgentBasic:
    async def test_direct_answer_no_tools(self) -> None:
        agent = _setup_agent([_make_stop_response("42")])
        result = await agent.run("What is 6 * 7?")
        assert isinstance(result, AgentResult)
        assert result.answer == "42"
        assert result.tool_calls_made == []
        assert result.iterations == 1

    async def test_single_tool_call(self) -> None:
        tool = _FakeTool("web_fetch", {"html": "<h1>Hi</h1>"})
        tc = ToolCall(call_id="c1", tool_name="web_fetch", arguments={"url": "http://x.com"})
        agent = _setup_agent(
            [
                _make_tool_response(tool_calls=[tc]),
                _make_stop_response("The page says Hi"),
            ],
            tools=[tool],
        )
        result = await agent.run("Fetch x.com")
        assert result.answer == "The page says Hi"
        assert len(result.tool_calls_made) == 1
        assert result.tool_calls_made[0].tool_name == "web_fetch"
        assert len(result.tool_results) == 1
        assert result.tool_results[0].success
        assert result.iterations == 2

    async def test_multi_step_tool_calls(self) -> None:
        fetch_tool = _FakeTool("web_fetch", {"html": "<p>data</p>"})
        extract_tool = _FakeTool("extract", {"title": "EvoSys"})

        tc1 = ToolCall(call_id="c1", tool_name="web_fetch", arguments={"url": "http://x.com"})
        tc2 = ToolCall(call_id="c2", tool_name="extract", arguments={"html": "<p>data</p>"})

        agent = _setup_agent(
            [
                _make_tool_response(tool_calls=[tc1]),
                _make_tool_response(tool_calls=[tc2]),
                _make_stop_response("Title is EvoSys"),
            ],
            tools=[fetch_tool, extract_tool],
        )
        result = await agent.run("Get the title of x.com")
        assert result.answer == "Title is EvoSys"
        assert len(result.tool_calls_made) == 2
        assert result.iterations == 3

    async def test_parallel_tool_calls(self) -> None:
        tool_a = _FakeTool("tool_a", {"a": 1})
        tool_b = _FakeTool("tool_b", {"b": 2})

        tc_a = ToolCall(call_id="c1", tool_name="tool_a", arguments={})
        tc_b = ToolCall(call_id="c2", tool_name="tool_b", arguments={})

        agent = _setup_agent(
            [
                _make_tool_response(tool_calls=[tc_a, tc_b]),
                _make_stop_response("Both done"),
            ],
            tools=[tool_a, tool_b],
        )
        result = await agent.run("Do both")
        assert len(result.tool_calls_made) == 2
        assert len(result.tool_results) == 2


class TestAgentMaxIterations:
    async def test_max_iterations_guard(self) -> None:
        tool = _FakeTool("looper", {"loop": True})
        tc = ToolCall(call_id="c1", tool_name="looper", arguments={})
        # LLM always calls tool, never stops
        responses = [_make_tool_response(tool_calls=[tc]) for _ in range(5)]
        agent = _setup_agent(responses, tools=[tool], max_iterations=3)
        result = await agent.run("Loop forever")
        assert result.iterations == 3
        assert "maximum" in result.answer.lower()


class TestAgentToolErrors:
    async def test_unknown_tool(self) -> None:
        tc = ToolCall(call_id="c1", tool_name="nonexistent", arguments={})
        agent = _setup_agent([
            _make_tool_response(tool_calls=[tc]),
            _make_stop_response("Could not find tool"),
        ])
        result = await agent.run("Use nonexistent tool")
        assert len(result.tool_results) == 1
        assert not result.tool_results[0].success
        assert "Unknown tool" in (result.tool_results[0].error or "")

    async def test_tool_raises_exception(self) -> None:
        error_tool = _ErrorTool()
        tc = ToolCall(call_id="c1", tool_name="error_tool", arguments={})
        agent = _setup_agent(
            [
                _make_tool_response(tool_calls=[tc]),
                _make_stop_response("Tool failed, sorry"),
            ],
            tools=[error_tool],
        )
        result = await agent.run("Try error tool")
        assert len(result.tool_results) == 1
        assert not result.tool_results[0].success
        assert "tool exploded" in (result.tool_results[0].error or "")


class TestAgentTokenTracking:
    async def test_token_accumulation(self) -> None:
        tool = _FakeTool()
        tc = ToolCall(call_id="c1", tool_name="test_tool", arguments={})
        agent = _setup_agent(
            [
                _make_tool_response(tool_calls=[tc], tokens=100),
                _make_stop_response("Done", tokens=50),
            ],
            tools=[tool],
        )
        result = await agent.run("Task")
        assert result.total_tokens == 150


class TestAgentContext:
    async def test_context_passed(self) -> None:
        mock_llm = LLMClient(model="test")
        calls = []

        async def _capture_call(messages, tools, **kwargs):
            calls.append(messages)
            return _make_stop_response("ok")

        mock_llm.complete_with_tools = _capture_call  # type: ignore[assignment]
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        mock_store = AsyncMock()
        mock_store.save = AsyncMock()
        mock_logger = TrajectoryLogger(mock_store)

        agent = Agent(llm=mock_llm, tool_registry=tr, trajectory_logger=mock_logger)
        await agent.run("task", context={"key": "val"})

        # Should have system + context + user messages
        messages = calls[0]
        assert len(messages) == 3
        assert "Context" in messages[1]["content"]
        assert "val" in messages[1]["content"]


class TestAgentTrajectoryLogging:
    async def test_tool_calls_logged(self) -> None:
        tool = _FakeTool("logged_tool", {"out": True})
        tc = ToolCall(call_id="c1", tool_name="logged_tool", arguments={"x": "y"})

        mock_store = AsyncMock()
        mock_store.save = AsyncMock()
        mock_logger = TrajectoryLogger(mock_store)

        mock_llm = LLMClient(model="test")
        mock_llm.complete_with_tools = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                _make_tool_response(tool_calls=[tc]),
                _make_stop_response("ok"),
            ]
        )

        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        tr.register_external(tool)

        agent = Agent(llm=mock_llm, tool_registry=tr, trajectory_logger=mock_logger)
        await agent.run("Do something")

        # Trajectory store should have been called with save()
        assert mock_store.save.call_count >= 1
        saved_record = mock_store.save.call_args[0][0]
        assert saved_record.action_name == "tool:logged_tool"


class TestAgentSessionId:
    async def test_session_id_set(self) -> None:
        agent = _setup_agent([_make_stop_response("ok")])
        result = await agent.run("task")
        assert result.session_id != ""
        assert len(result.session_id) > 0


class TestAgentResult:
    def test_defaults(self) -> None:
        result = AgentResult(answer="test")
        assert result.tool_calls_made == []
        assert result.tool_results == []
        assert result.total_tokens == 0
        assert result.total_latency_ms == 0
        assert result.session_id == ""
        assert result.iterations == 0

    def test_immutable(self) -> None:
        result = AgentResult(answer="test")
        with pytest.raises(AttributeError):
            result.answer = "changed"  # type: ignore[misc]
