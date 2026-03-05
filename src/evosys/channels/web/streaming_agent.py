"""Streaming agent wrapper — emits real-time events over WebSocket.

Wraps the standard Agent to provide tool-call-by-tool-call streaming
feedback to connected WebSocket clients.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import structlog

from evosys.channels.web.frames import ChatResponse, ErrorFrame, StreamEvent
from evosys.schemas._types import new_ulid

if TYPE_CHECKING:
    from evosys.agents.agent import Agent

log = structlog.get_logger()


class StreamingAgent:
    """Wraps an Agent to yield streaming events for WebSocket clients.

    Instead of waiting for the full agent run to complete, this wrapper
    yields events as each tool call starts, completes, and when the
    final answer is ready.

    Parameters
    ----------
    agent:
        The underlying Agent to run.
    """

    def __init__(self, agent: Agent) -> None:
        self._agent = agent

    async def run_streaming(
        self,
        task: str,
        *,
        session_id: str | None = None,
        context: dict[str, object] | None = None,
    ) -> AsyncIterator[str]:
        """Run the agent and yield JSON-serialized event frames.

        Each yielded string is a JSON frame suitable for WebSocket send.
        """
        sid = session_id or str(new_ulid())

        # Emit start event
        yield StreamEvent(
            type="stream",
            data={"status": "started", "task": task[:200]},
            session_id=sid,
        ).model_dump_json()

        try:
            result = await self._agent.run(task=task, context=context)

            # Emit tool call summaries
            for tc, tr in zip(result.tool_calls_made, result.tool_results, strict=False):
                yield StreamEvent(
                    type="tool_result",
                    data={
                        "tool": tc.tool_name,
                        "success": tr.success,
                        "latency_ms": round(tr.latency_ms, 1),
                    },
                    session_id=sid,
                ).model_dump_json()

            # Emit final answer
            yield ChatResponse(
                text=result.answer,
                session_id=sid,
                done=True,
            ).model_dump_json()

        except TimeoutError:
            yield ErrorFrame(
                error="Agent timed out",
                session_id=sid,
            ).model_dump_json()

        except Exception as exc:
            log.exception("streaming_agent.error")
            yield ErrorFrame(
                error=str(exc),
                session_id=sid,
            ).model_dump_json()
