"""Tier strategy — route tasks to local or cloud models based on complexity.

Simple tasks (short prompts, no tool use) go to a cheap/fast local model.
Complex tasks (long context, tool calls, structured output) go to cloud.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class TierDecision:
    """Result of a tier routing decision."""

    tier: str  # "local" or "cloud"
    model: str
    reason: str


class TierStrategy:
    """Route tasks between local and cloud models.

    Parameters
    ----------
    local_model:
        LiteLLM model ID for the local model (e.g. "ollama/llama3").
    cloud_model:
        LiteLLM model ID for the cloud model.
    max_local_tokens:
        Maximum estimated input tokens for local routing.
    max_local_tools:
        Maximum number of tools before forcing cloud.
    """

    def __init__(
        self,
        local_model: str,
        cloud_model: str,
        *,
        max_local_tokens: int = 2000,
        max_local_tools: int = 3,
    ) -> None:
        self._local = local_model
        self._cloud = cloud_model
        self._max_local_tokens = max_local_tokens
        self._max_local_tools = max_local_tools

    def decide(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, object]] | None = None,
    ) -> TierDecision:
        """Decide whether to route to local or cloud.

        Uses heuristics based on message length and tool count.
        """
        # Estimate token count from message text
        total_chars = sum(
            len(str(m.get("content", ""))) for m in messages
        )
        est_tokens = total_chars // 4

        # Too many tools → cloud (local models struggle with complex tool schemas)
        tool_count = len(tools) if tools else 0
        if tool_count > self._max_local_tools:
            return TierDecision(
                tier="cloud",
                model=self._cloud,
                reason=f"Too many tools ({tool_count} > {self._max_local_tools})",
            )

        # Long context → cloud
        if est_tokens > self._max_local_tokens:
            return TierDecision(
                tier="cloud",
                model=self._cloud,
                reason=f"Long context (~{est_tokens} tokens > {self._max_local_tokens})",
            )

        # Tool-use requests → cloud (local models are unreliable with tools)
        if tool_count > 0:
            # Check if last message looks like it needs tools
            last_content = str(messages[-1].get("content", "")).lower() if messages else ""
            complex_indicators = [
                "search", "fetch", "download", "extract", "analyze",
                "write to", "save", "execute", "run",
            ]
            if any(ind in last_content for ind in complex_indicators):
                return TierDecision(
                    tier="cloud",
                    model=self._cloud,
                    reason="Task likely requires tool use",
                )

        # Simple task → local
        return TierDecision(
            tier="local",
            model=self._local,
            reason="Simple task routed to local model",
        )
