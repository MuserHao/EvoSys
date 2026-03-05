"""Model router — drop-in replacement for LLMClient with ordered fallback.

Wraps multiple LLMClient instances in a priority chain.  On failure the
router tries the next healthy model until one succeeds or all are
exhausted.  Health tracking + cooldown prevent hammering a broken
provider.
"""

from __future__ import annotations

from typing import Any

import structlog

from evosys.llm.client import LLMClient, LLMError, LLMResponse, LLMToolCallResponse
from evosys.llm.health import ModelHealth

log = structlog.get_logger()


class ModelRouter:
    """LLM client with ordered failover across multiple models.

    Drop-in replacement for :class:`LLMClient` — exposes the same
    ``complete()`` and ``complete_with_tools()`` interface.  The first
    model in *models* is the primary; subsequent models are fallbacks.

    Parameters
    ----------
    models:
        Ordered list of model identifiers (litellm format).
    temperature:
        Default temperature for completions.
    max_tokens:
        Default max_tokens for completions.
    cooldown_s:
        Per-model cooldown after consecutive failures.
    max_consecutive_failures:
        Failures before a model enters cooldown.
    """

    def __init__(
        self,
        models: list[str],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        cooldown_s: float = 60.0,
        max_consecutive_failures: int = 3,
    ) -> None:
        if not models:
            raise ValueError("ModelRouter requires at least one model")

        self._clients: list[LLMClient] = []
        self._health: list[ModelHealth] = []

        for model_id in models:
            self._clients.append(
                LLMClient(model=model_id, temperature=temperature, max_tokens=max_tokens)
            )
            self._health.append(
                ModelHealth(
                    model=model_id,
                    cooldown_s=cooldown_s,
                    max_consecutive_failures=max_consecutive_failures,
                )
            )

        # Expose primary model for compatibility with code that reads llm.model
        self.model = models[0]
        self.temperature = temperature
        self.max_tokens = max_tokens

    @property
    def models(self) -> list[str]:
        """Return ordered list of model identifiers."""
        return [h.model for h in self._health]

    @property
    def health(self) -> list[ModelHealth]:
        """Return health state for each model (read-only access)."""
        return list(self._health)

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict[str, str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send a chat completion, falling back on failure."""
        last_error: Exception | None = None

        for client, health in zip(self._clients, self._health, strict=True):
            if not health.is_healthy:
                log.debug("router.skip_unhealthy", model=health.model)
                continue

            try:
                resp = await client.complete(
                    messages,
                    response_format=response_format,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                health.record_success()
                return resp
            except (LLMError, Exception) as exc:
                health.record_failure()
                last_error = exc
                log.warning(
                    "router.model_failed",
                    model=health.model,
                    error=str(exc),
                    consecutive=health.consecutive_failures,
                )

        raise LLMError(
            f"All models exhausted. Last error: {last_error}"
        ) from last_error

    async def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, object]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMToolCallResponse:
        """Send a tool-calling completion, falling back on failure."""
        last_error: Exception | None = None

        for client, health in zip(self._clients, self._health, strict=True):
            if not health.is_healthy:
                log.debug("router.skip_unhealthy", model=health.model)
                continue

            try:
                resp = await client.complete_with_tools(
                    messages,
                    tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                health.record_success()
                return resp
            except (LLMError, Exception) as exc:
                health.record_failure()
                last_error = exc
                log.warning(
                    "router.model_failed",
                    model=health.model,
                    error=str(exc),
                    consecutive=health.consecutive_failures,
                )

        raise LLMError(
            f"All models exhausted. Last error: {last_error}"
        ) from last_error

    async def extract_json(
        self,
        *,
        system_prompt: str,
        user_content: str,
        target_schema_description: str,
    ) -> LLMResponse:
        """Convenience: extract JSON with fallback (delegates to complete)."""
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
