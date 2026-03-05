"""Sub-agent system — spawn child agents as asyncio tasks.

Enables the main agent to delegate sub-tasks to independent agent
instances that run concurrently.  Depth-limited to prevent runaway
recursion.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from evosys.agents.agent import AgentResult

log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class SubAgentResult:
    """Result from a sub-agent task."""

    task: str
    answer: str
    total_tokens: int = 0
    iterations: int = 0
    success: bool = True
    error: str | None = None


class SubAgentManager:
    """Spawn and manage child agent tasks with depth limiting.

    Each sub-agent gets its own ``Agent`` instance (sharing the same
    LLM client and tool registry) and runs as an asyncio Task.
    Depth tracking prevents recursive sub-agent calls from running
    away.

    Parameters
    ----------
    agent_factory:
        Callable that creates a new Agent instance for a given depth.
    max_depth:
        Maximum nesting depth for sub-agents (1 = no sub-agent spawning
        from sub-agents).
    max_concurrent:
        Maximum number of concurrent sub-agent tasks.
    """

    def __init__(
        self,
        agent_factory: object,  # Callable[..., Agent] — loose type to avoid circular
        *,
        max_depth: int = 2,
        max_concurrent: int = 3,
    ) -> None:
        self._agent_factory = agent_factory
        self._max_depth = max_depth
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_tasks: list[asyncio.Task[SubAgentResult]] = []

    @property
    def max_depth(self) -> int:
        return self._max_depth

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    async def delegate(
        self,
        task: str,
        *,
        current_depth: int = 0,
        context: dict[str, object] | None = None,
    ) -> SubAgentResult:
        """Run a sub-task in a child agent.

        Returns the result directly (awaited). For parallel execution,
        use :meth:`delegate_parallel`.
        """
        if current_depth >= self._max_depth:
            return SubAgentResult(
                task=task,
                answer="",
                success=False,
                error=f"Max sub-agent depth ({self._max_depth}) exceeded",
            )

        async with self._semaphore:
            try:
                agent = self._agent_factory(depth=current_depth + 1)
                result: AgentResult = await agent.run(task, context=context)
                return SubAgentResult(
                    task=task,
                    answer=result.answer,
                    total_tokens=result.total_tokens,
                    iterations=result.iterations,
                )
            except Exception as exc:
                log.exception("sub_agent.failed", task=task[:100])
                return SubAgentResult(
                    task=task,
                    answer="",
                    success=False,
                    error=str(exc),
                )

    async def delegate_parallel(
        self,
        tasks: list[str],
        *,
        current_depth: int = 0,
        context: dict[str, object] | None = None,
    ) -> list[SubAgentResult]:
        """Run multiple sub-tasks concurrently and return all results.

        Respects ``max_concurrent`` via semaphore — excess tasks queue.
        """
        if current_depth >= self._max_depth:
            return [
                SubAgentResult(
                    task=t,
                    answer="",
                    success=False,
                    error=f"Max sub-agent depth ({self._max_depth}) exceeded",
                )
                for t in tasks
            ]

        coros = [
            self.delegate(t, current_depth=current_depth, context=context)
            for t in tasks
        ]
        return list(await asyncio.gather(*coros, return_exceptions=False))
