"""Tests for built-in tools (WebFetchTool, ExtractStructuredTool)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from evosys.core.tool import Tool
from evosys.core.types import Observation
from evosys.executors.http_executor import HttpExecutor
from evosys.schemas._types import new_ulid
from evosys.tools.builtins import ExtractStructuredTool, WebFetchTool


class TestWebFetchTool:
    def test_satisfies_protocol(self) -> None:
        tool = WebFetchTool(HttpExecutor())
        assert isinstance(tool, Tool)

    def test_name(self) -> None:
        tool = WebFetchTool(HttpExecutor())
        assert tool.name == "web_fetch"

    def test_description(self) -> None:
        tool = WebFetchTool(HttpExecutor())
        assert "URL" in tool.description or "url" in tool.description.lower()

    def test_parameters_schema(self) -> None:
        tool = WebFetchTool(HttpExecutor())
        assert "url" in tool.parameters_schema

    def test_to_openai_tool_format(self) -> None:
        tool = WebFetchTool(HttpExecutor())
        fmt = tool.to_openai_tool()
        assert fmt["type"] == "function"
        fn = fmt["function"]
        assert fn["name"] == "web_fetch"
        assert "required" in fn["parameters"]

    async def test_call_success(self) -> None:
        http = HttpExecutor()
        http.execute = AsyncMock(  # type: ignore[method-assign]
            return_value=Observation(
                action_id=new_ulid(),
                success=True,
                result={
                    "html": "<h1>Hello</h1>",
                    "status_code": 200,
                    "url": "http://example.com",
                },
                latency_ms=100,
            )
        )
        tool = WebFetchTool(http)
        result = await tool(url="http://example.com")
        assert result["html"] == "<h1>Hello</h1>"
        assert result["status_code"] == 200

    async def test_call_failure(self) -> None:
        http = HttpExecutor()
        http.execute = AsyncMock(  # type: ignore[method-assign]
            return_value=Observation(
                action_id=new_ulid(),
                success=False,
                error="Timeout",
            )
        )
        tool = WebFetchTool(http)
        result = await tool(url="http://example.com")
        assert "error" in result


class TestExtractStructuredTool:
    def test_satisfies_protocol(self) -> None:
        mock_agent = AsyncMock()
        tool = ExtractStructuredTool(mock_agent)
        assert isinstance(tool, Tool)

    def test_name(self) -> None:
        tool = ExtractStructuredTool(AsyncMock())
        assert tool.name == "extract_structured"

    def test_to_openai_tool_format(self) -> None:
        tool = ExtractStructuredTool(AsyncMock())
        fmt = tool.to_openai_tool()
        assert fmt["type"] == "function"
        fn = fmt["function"]
        assert fn["name"] == "extract_structured"

    async def test_call_success(self) -> None:
        from dataclasses import dataclass

        @dataclass
        class _FakeResult:
            data: dict[str, object]

        mock_agent = AsyncMock()
        mock_agent.extract = AsyncMock(return_value=_FakeResult(data={"title": "Test"}))
        tool = ExtractStructuredTool(mock_agent)
        result = await tool(url="http://example.com", schema_description='{"title":"string"}')
        assert result == {"title": "Test"}

    async def test_call_failure(self) -> None:
        mock_agent = AsyncMock()
        mock_agent.extract = AsyncMock(side_effect=RuntimeError("boom"))
        tool = ExtractStructuredTool(mock_agent)
        result = await tool(url="http://example.com")
        assert "error" in result
