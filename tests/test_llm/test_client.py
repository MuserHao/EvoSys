"""Tests for LLM client (mocked litellm)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from evosys.llm.client import LLMClient, LLMError, LLMResponse


def _mock_response(
    content: str = '{"key": "value"}',
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
    total_tokens: int = 30,
    model: str = "test-model",
) -> SimpleNamespace:
    """Build a fake litellm response."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
        model=model,
    )


class TestComplete:
    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_returns_llm_response(self, mock_acomp: AsyncMock):
        mock_acomp.return_value = _mock_response()
        client = LLMClient(model="test-model")
        resp = await client.complete([{"role": "user", "content": "hi"}])
        assert isinstance(resp, LLMResponse)
        assert resp.content == '{"key": "value"}'
        assert resp.total_tokens == 30

    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_passes_model_and_temperature(self, mock_acomp: AsyncMock):
        mock_acomp.return_value = _mock_response()
        client = LLMClient(model="my-model", temperature=0.5)
        await client.complete([{"role": "user", "content": "hi"}])
        call_kwargs = mock_acomp.call_args.kwargs
        assert call_kwargs["model"] == "my-model"
        assert call_kwargs["temperature"] == 0.5

    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_override_temperature(self, mock_acomp: AsyncMock):
        mock_acomp.return_value = _mock_response()
        client = LLMClient(model="m", temperature=0.0)
        await client.complete(
            [{"role": "user", "content": "hi"}], temperature=0.9
        )
        assert mock_acomp.call_args.kwargs["temperature"] == 0.9

    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_raises_llm_error_on_failure(self, mock_acomp: AsyncMock):
        mock_acomp.side_effect = RuntimeError("provider down")
        client = LLMClient(model="m")
        with pytest.raises(LLMError, match="provider down"):
            await client.complete([{"role": "user", "content": "hi"}])


class TestExtractJson:
    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_constructs_correct_messages(self, mock_acomp: AsyncMock):
        mock_acomp.return_value = _mock_response()
        client = LLMClient(model="m")
        await client.extract_json(
            system_prompt="Be precise.",
            user_content="<html>data</html>",
            target_schema_description='{"name": "string"}',
        )
        messages = mock_acomp.call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "Be precise." in messages[0]["content"]
        assert "Target schema" in messages[1]["content"]
        assert "<html>data</html>" in messages[1]["content"]

    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_uses_json_response_format(self, mock_acomp: AsyncMock):
        mock_acomp.return_value = _mock_response()
        client = LLMClient(model="m")
        await client.extract_json(
            system_prompt="s",
            user_content="c",
            target_schema_description="d",
        )
        assert mock_acomp.call_args.kwargs["response_format"] == {"type": "json_object"}

    @patch("evosys.llm.client.litellm.acompletion", new_callable=AsyncMock)
    async def test_token_counting(self, mock_acomp: AsyncMock):
        mock_acomp.return_value = _mock_response(
            prompt_tokens=100, completion_tokens=50, total_tokens=150
        )
        client = LLMClient(model="m")
        resp = await client.extract_json(
            system_prompt="s",
            user_content="c",
            target_schema_description="d",
        )
        assert resp.prompt_tokens == 100
        assert resp.completion_tokens == 50
        assert resp.total_tokens == 150
