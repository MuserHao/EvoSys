"""Tests for SubAgentManager and SubAgentTool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from evosys.agents.sub_agent import SubAgentManager
from evosys.tools.sub_agent_tool import SubAgentTool

# --- Fixtures ---


def _make_mock_agent(answer: str = "mock answer", tokens: int = 100):
    """Create a mock Agent that returns a fixed result."""
    agent = AsyncMock()
    result = MagicMock()
    result.answer = answer
    result.total_tokens = tokens
    result.iterations = 1
    result.session_id = "test-session"
    result.tool_calls_made = []
    result.tool_results = []
    agent.run = AsyncMock(return_value=result)
    return agent


def _make_factory(answer: str = "mock answer"):
    """Create an agent factory that returns mock agents."""
    def factory(depth: int = 0):
        return _make_mock_agent(answer)
    return factory


# --- SubAgentManager ---


class TestSubAgentManager:
    async def test_delegate_returns_result(self) -> None:
        manager = SubAgentManager(_make_factory("hello"), max_depth=2)
        result = await manager.delegate("test task", current_depth=0)
        assert result.success is True
        assert result.answer == "hello"

    async def test_delegate_respects_max_depth(self) -> None:
        manager = SubAgentManager(_make_factory(), max_depth=1)
        result = await manager.delegate("test", current_depth=1)
        assert result.success is False
        assert "depth" in result.error.lower()

    async def test_delegate_parallel(self) -> None:
        manager = SubAgentManager(
            _make_factory("parallel answer"),
            max_depth=3,
            max_concurrent=2,
        )
        results = await manager.delegate_parallel(
            ["task1", "task2", "task3"],
            current_depth=0,
        )
        assert len(results) == 3
        assert all(r.success for r in results)

    async def test_delegate_parallel_depth_exceeded(self) -> None:
        manager = SubAgentManager(_make_factory(), max_depth=1)
        results = await manager.delegate_parallel(
            ["t1", "t2"], current_depth=1
        )
        assert len(results) == 2
        assert all(not r.success for r in results)

    async def test_delegate_handles_exception(self) -> None:
        def bad_factory(depth: int = 0):
            agent = AsyncMock()
            agent.run = AsyncMock(side_effect=RuntimeError("boom"))
            return agent

        manager = SubAgentManager(bad_factory, max_depth=2)
        result = await manager.delegate("test", current_depth=0)
        assert result.success is False
        assert "boom" in result.error


# --- SubAgentTool ---


class TestSubAgentTool:
    async def test_single_task(self) -> None:
        manager = SubAgentManager(_make_factory("tool answer"), max_depth=2)
        tool = SubAgentTool(manager)

        result = await tool(task="do something")
        assert "answer" in result
        assert result["answer"] == "tool answer"

    async def test_parallel_tasks(self) -> None:
        manager = SubAgentManager(_make_factory("par"), max_depth=2)
        tool = SubAgentTool(manager)

        result = await tool(task="task1 ||| task2")
        assert "results" in result
        assert result["total_tasks"] == 2

    async def test_empty_task(self) -> None:
        manager = SubAgentManager(_make_factory(), max_depth=2)
        tool = SubAgentTool(manager)

        result = await tool(task="")
        assert "error" in result

    def test_tool_interface(self) -> None:
        manager = SubAgentManager(_make_factory(), max_depth=2)
        tool = SubAgentTool(manager)

        assert tool.name == "delegate_task"
        assert "delegate" in tool.description.lower()
        schema = tool.parameters_schema
        assert "task" in schema

        openai = tool.to_openai_tool()
        assert openai["type"] == "function"
        assert openai["function"]["name"] == "delegate_task"
