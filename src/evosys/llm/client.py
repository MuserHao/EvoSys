"""Thin wrapper around litellm for unified LLM access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import litellm


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Immutable DTO for an LLM completion result."""

    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str


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
