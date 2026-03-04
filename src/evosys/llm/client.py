"""Thin wrapper around litellm for unified LLM access."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import litellm

from evosys.core.types import ToolCall


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Immutable DTO for an LLM completion result."""

    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str


@dataclass(frozen=True, slots=True)
class LLMToolCallResponse:
    """Response from a tool-calling completion."""

    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    finish_reason: str = "stop"


class LLMError(Exception):
    """Wraps all litellm / provider errors."""


class LLMClient:
    """Async LLM client backed by :func:`litellm.acompletion`."""

    def __init__(
        self,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict[str, str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send a chat completion request and return an :class:`LLMResponse`."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        try:
            resp = await litellm.acompletion(**kwargs)
        except Exception as exc:
            raise LLMError(str(exc)) from exc

        choice = resp.choices[0]  # type: ignore[union-attr]
        usage = resp.usage  # type: ignore[union-attr]
        return LLMResponse(
            content=choice.message.content or "",  # type: ignore[union-attr]
            prompt_tokens=usage.prompt_tokens,  # type: ignore[union-attr]
            completion_tokens=usage.completion_tokens,  # type: ignore[union-attr]
            total_tokens=usage.total_tokens,  # type: ignore[union-attr]
            model=resp.model or self.model,  # type: ignore[union-attr]
        )

    async def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, object]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMToolCallResponse:
        """Send a chat completion with tools and parse tool-call responses.

        LiteLLM translates the OpenAI tool-call format to provider-specific
        formats (Anthropic, Google, etc.), so multi-model support is free.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "tools": tools,
        }

        try:
            resp = await litellm.acompletion(**kwargs)
        except Exception as exc:
            raise LLMError(str(exc)) from exc

        choice = resp.choices[0]  # type: ignore[union-attr]
        usage = resp.usage  # type: ignore[union-attr]
        finish_reason = choice.finish_reason or "stop"  # type: ignore[union-attr]

        # Parse tool calls from the response
        tool_calls: list[ToolCall] = []
        raw_tool_calls = getattr(choice.message, "tool_calls", None)  # type: ignore[union-attr]
        if raw_tool_calls:
            import json as _json

            for tc in raw_tool_calls:
                args_raw = tc.function.arguments
                if isinstance(args_raw, str):
                    try:
                        args = _json.loads(args_raw)
                    except _json.JSONDecodeError:
                        args = {}
                elif isinstance(args_raw, dict):
                    args = args_raw
                else:
                    args = {}

                tool_calls.append(
                    ToolCall(
                        call_id=tc.id or "",
                        tool_name=tc.function.name or "",
                        arguments=args,
                    )
                )

        content = choice.message.content  # type: ignore[union-attr]

        return LLMToolCallResponse(
            content=content,
            tool_calls=tool_calls,
            prompt_tokens=usage.prompt_tokens,  # type: ignore[union-attr]
            completion_tokens=usage.completion_tokens,  # type: ignore[union-attr]
            total_tokens=usage.total_tokens,  # type: ignore[union-attr]
            model=resp.model or self.model,  # type: ignore[union-attr]
            finish_reason=finish_reason,
        )

    async def extract_json(
        self,
        *,
        system_prompt: str,
        user_content: str,
        target_schema_description: str,
    ) -> LLMResponse:
        """Convenience: ask the LLM to extract JSON matching a schema."""
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Extract structured data from the following content.\n\n"
                    f"Target schema:\n{target_schema_description}\n\n"
                    f"Content:\n{user_content}"
                ),
            },
        ]
        return await self.complete(
            messages,
            response_format={"type": "json_object"},
        )
