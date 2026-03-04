"""Tests for complete_with_tools() and LLMToolCallResponse."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from evosys.core.types import ToolCall
from evosys.llm.client import LLMClient, LLMError, LLMToolCallResponse


def _mock_tool_call_response(
    content: str | None = None,
    tool_calls: list[SimpleNamespace] | None = None,
    finish_reason: str = "stop",
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
    total_tokens: int = 30,
    model: str = "test-model",
) -> SimpleNamespace:
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=msg, finish_reason=finish_reason)],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
        model=model,
    )


def _make_tc(
    call_id: str = "call_1",
    name: str = "web_fetch",
    arguments: str | dict[str, object] = '{"url": "http://example.com"}',
) -> SimpleNamespace:
    args = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=args),
    )


_SAMPLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch a URL",
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}}},
        },
    }
]


class TestCompleteWithTools:
    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_content_response(self, mock_acomp: AsyncMock) -> None:
        mock_acomp.return_value = _mock_tool_call_response(
            content="The answer is 42.", finish_reason="stop"
        )
        client = LLMClient(model="m")
        resp = await client.complete_with_tools(
            [{"role": "user", "content": "hi"}], _SAMPLE_TOOLS
        )
        assert isinstance(resp, LLMToolCallResponse)
        assert resp.content == "The answer is 42."
        assert resp.tool_calls == []
        assert resp.finish_reason == "stop"

    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_tool_call_response(self, mock_acomp: AsyncMock) -> None:
        tc = _make_tc(call_id="call_1", name="web_fetch", arguments='{"url": "http://x.com"}')
        mock_acomp.return_value = _mock_tool_call_response(
            content=None,
            tool_calls=[tc],
            finish_reason="tool_calls",
        )
        client = LLMClient(model="m")
        resp = await client.complete_with_tools(
            [{"role": "user", "content": "fetch x.com"}], _SAMPLE_TOOLS
        )
        assert resp.content is None
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].call_id == "call_1"
        assert resp.tool_calls[0].tool_name == "web_fetch"
        assert resp.tool_calls[0].arguments == {"url": "http://x.com"}
        assert resp.finish_reason == "tool_calls"

    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_multiple_tool_calls(self, mock_acomp: AsyncMock) -> None:
        tcs = [
            _make_tc(call_id="c1", name="web_fetch", arguments='{"url": "http://a.com"}'),
            _make_tc(call_id="c2", name="extract", arguments='{"schema": "title"}'),
        ]
        mock_acomp.return_value = _mock_tool_call_response(
            content=None, tool_calls=tcs, finish_reason="tool_calls"
        )
        client = LLMClient(model="m")
        resp = await client.complete_with_tools(
            [{"role": "user", "content": "go"}], _SAMPLE_TOOLS
        )
        assert len(resp.tool_calls) == 2
        assert resp.tool_calls[0].tool_name == "web_fetch"
        assert resp.tool_calls[1].tool_name == "extract"

    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_token_counting(self, mock_acomp: AsyncMock) -> None:
        mock_acomp.return_value = _mock_tool_call_response(
            content="ok", prompt_tokens=100, completion_tokens=50, total_tokens=150
        )
        client = LLMClient(model="m")
        resp = await client.complete_with_tools(
            [{"role": "user", "content": "hi"}], _SAMPLE_TOOLS
        )
        assert resp.prompt_tokens == 100
        assert resp.completion_tokens == 50
        assert resp.total_tokens == 150

    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_passes_tools_to_litellm(self, mock_acomp: AsyncMock) -> None:
        mock_acomp.return_value = _mock_tool_call_response(content="ok")
        client = LLMClient(model="m")
        await client.complete_with_tools(
            [{"role": "user", "content": "hi"}], _SAMPLE_TOOLS
        )
        assert mock_acomp.call_args.kwargs["tools"] == _SAMPLE_TOOLS

    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_override_temperature(self, mock_acomp: AsyncMock) -> None:
        mock_acomp.return_value = _mock_tool_call_response(content="ok")
        client = LLMClient(model="m", temperature=0.0)
        await client.complete_with_tools(
            [{"role": "user", "content": "hi"}], _SAMPLE_TOOLS, temperature=0.7
        )
        assert mock_acomp.call_args.kwargs["temperature"] == 0.7

    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_override_max_tokens(self, mock_acomp: AsyncMock) -> None:
        mock_acomp.return_value = _mock_tool_call_response(content="ok")
        client = LLMClient(model="m", max_tokens=4096)
        await client.complete_with_tools(
            [{"role": "user", "content": "hi"}], _SAMPLE_TOOLS, max_tokens=1024
        )
        assert mock_acomp.call_args.kwargs["max_tokens"] == 1024

    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_raises_llm_error_on_failure(self, mock_acomp: AsyncMock) -> None:
        mock_acomp.side_effect = RuntimeError("provider down")
        client = LLMClient(model="m")
        with pytest.raises(LLMError, match="provider down"):
            await client.complete_with_tools(
                [{"role": "user", "content": "hi"}], _SAMPLE_TOOLS
            )

    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_malformed_json_arguments(self, mock_acomp: AsyncMock) -> None:
        tc = _make_tc(call_id="c1", name="tool", arguments="not json")
        mock_acomp.return_value = _mock_tool_call_response(
            content=None, tool_calls=[tc], finish_reason="tool_calls"
        )
        client = LLMClient(model="m")
        resp = await client.complete_with_tools(
            [{"role": "user", "content": "hi"}], _SAMPLE_TOOLS
        )
        assert resp.tool_calls[0].arguments == {}

    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_dict_arguments(self, mock_acomp: AsyncMock) -> None:
        """Some providers return arguments as dict instead of string."""
        tc = SimpleNamespace(
            id="c1",
            type="function",
            function=SimpleNamespace(name="tool", arguments={"key": "val"}),
        )
        mock_acomp.return_value = _mock_tool_call_response(
            content=None, tool_calls=[tc], finish_reason="tool_calls"
        )
        client = LLMClient(model="m")
        resp = await client.complete_with_tools(
            [{"role": "user", "content": "hi"}], _SAMPLE_TOOLS
        )
        assert resp.tool_calls[0].arguments == {"key": "val"}

    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_no_tool_calls_attribute(self, mock_acomp: AsyncMock) -> None:
        """When message has no tool_calls attribute at all."""
        msg = SimpleNamespace(content="just text")
        # no tool_calls attr
        mock_acomp.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=msg, finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5, total_tokens=10),
            model="m",
        )
        client = LLMClient(model="m")
        resp = await client.complete_with_tools(
            [{"role": "user", "content": "hi"}], _SAMPLE_TOOLS
        )
        assert resp.tool_calls == []
        assert resp.content == "just text"

    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_model_fallback(self, mock_acomp: AsyncMock) -> None:
        mock_acomp.return_value = _mock_tool_call_response(content="ok", model=None)
        # When model is None, should fall back to client's model
        mock_acomp.return_value.model = None
        client = LLMClient(model="fallback-model")
        resp = await client.complete_with_tools(
            [{"role": "user", "content": "hi"}], _SAMPLE_TOOLS
        )
        assert resp.model == "fallback-model"


class TestLLMToolCallResponse:
    def test_defaults(self) -> None:
        resp = LLMToolCallResponse(content=None)
        assert resp.tool_calls == []
        assert resp.prompt_tokens == 0
        assert resp.completion_tokens == 0
        assert resp.total_tokens == 0
        assert resp.model == ""
        assert resp.finish_reason == "stop"

    def test_with_tool_calls(self) -> None:
        tc = ToolCall(call_id="c1", tool_name="t", arguments={"a": 1})
        resp = LLMToolCallResponse(content=None, tool_calls=[tc], finish_reason="tool_calls")
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].tool_name == "t"

    def test_immutable(self) -> None:
        resp = LLMToolCallResponse(content="ok")
        with pytest.raises(AttributeError):
            resp.content = "changed"  # type: ignore[misc]
