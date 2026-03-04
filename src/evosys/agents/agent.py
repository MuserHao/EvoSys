"""General-purpose agent — ReAct loop with tool calling."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from evosys.core.types import ToolCall, ToolResult
from evosys.llm.client import LLMClient
from evosys.schemas._types import new_ulid
from evosys.tools.registry import ToolRegistry
from evosys.trajectory.logger import TrajectoryLogger

log = structlog.get_logger()

_DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful general-purpose assistant. "
    "Use the available tools to accomplish the user's task. "
    "Think step by step. When you have enough information to "
    "answer, respond directly without calling more tools."
)


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Outcome of a completed agent run."""

    answer: str
    tool_calls_made: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    total_tokens: int = 0
    total_latency_ms: float = 0
    session_id: str = ""
    iterations: int = 0


class Agent:
    """ReAct-style agent that uses tools to solve arbitrary tasks.

    Loop:
    1. Send task + available tools to LLM via ``complete_with_tools()``
    2. If LLM returns tool calls: execute each, append results, goto 1
    3. If LLM returns content (finish_reason="stop"): return answer
    4. Every tool execution is logged via TrajectoryLogger
    """

    def __init__(
        self,
        llm: LLMClient,
        tool_registry: ToolRegistry,
        trajectory_logger: TrajectoryLogger,
        *,
        max_iterations: int = 20,
        system_prompt: str | None = None,
    ) -> None:
        self._llm = llm
        self._tool_registry = tool_registry
        self._logger = trajectory_logger
        self._max_iterations = max_iterations
        self._system_prompt = system_prompt or _DEFAULT_SYSTEM_PROMPT

    async def run(
        self,
        task: str,
        *,
        context: dict[str, object] | None = None,
    ) -> AgentResult:
        """Execute the agent loop for *task* and return the result."""
        t0 = time.monotonic()
        session_id = str(new_ulid())
        all_tool_calls: list[ToolCall] = []
        all_tool_results: list[ToolResult] = []
        total_tokens = 0

        # Build initial messages
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
        ]
        if context:
            messages.append({
                "role": "system",
                "content": f"Context: {json.dumps(context, default=str)}",
            })
        messages.append({"role": "user", "content": task})

        # Get tools in OpenAI format
        openai_tools = self._tool_registry.get_openai_tools()

        for iteration in range(self._max_iterations):
            # Call LLM with tools
            resp = await self._llm.complete_with_tools(
                messages=messages,
                tools=openai_tools,
            )
            total_tokens += resp.total_tokens

            # If no tool calls, we have the final answer
            if not resp.tool_calls:
                total_latency = (time.monotonic() - t0) * 1000
                return AgentResult(
                    answer=resp.content or "",
                    tool_calls_made=all_tool_calls,
                    tool_results=all_tool_results,
                    total_tokens=total_tokens,
                    total_latency_ms=total_latency,
                    session_id=session_id,
                    iterations=iteration + 1,
                )

            # Build assistant message with tool calls for conversation history
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": resp.content,
                "tool_calls": [
                    {
                        "id": tc.call_id,
                        "type": "function",
                        "function": {
                            "name": tc.tool_name,
                            "arguments": json.dumps(tc.arguments, default=str),
                        },
                    }
                    for tc in resp.tool_calls
                ],
            }
            messages.append(assistant_msg)

            # Execute each tool call
            for tc in resp.tool_calls:
                all_tool_calls.append(tc)
                tool_result = await self._execute_tool(
                    tc, session_id=session_id, task=task
                )
                all_tool_results.append(tool_result)

                # Append tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.call_id,
                    "content": json.dumps(
                        tool_result.result if tool_result.success
                        else {"error": tool_result.error},
                        default=str,
                    ),
                })

        # Max iterations reached — return what we have
        total_latency = (time.monotonic() - t0) * 1000
        log.warning(
            "agent.max_iterations",
            session_id=session_id,
            iterations=self._max_iterations,
        )
        return AgentResult(
            answer=(
                "I reached the maximum number of iterations. "
                "Here is what I found so far based on the tools I used."
            ),
            tool_calls_made=all_tool_calls,
            tool_results=all_tool_results,
            total_tokens=total_tokens,
            total_latency_ms=total_latency,
            session_id=session_id,
            iterations=self._max_iterations,
        )

    async def _execute_tool(
        self,
        tool_call: ToolCall,
        *,
        session_id: str,
        task: str,
    ) -> ToolResult:
        """Execute a single tool call, log trajectory, and return result."""
        tool = self._tool_registry.get_tool(tool_call.tool_name)
        if tool is None:
            result = ToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                success=False,
                error=f"Unknown tool: {tool_call.tool_name}",
            )
            await self._log_tool_execution(
                tool_call, result, session_id=session_id, task=task
            )
            return result

        t0 = time.monotonic()
        try:
            output = await tool(**tool_call.arguments)
            latency_ms = (time.monotonic() - t0) * 1000
            # Check if the tool returned an error
            if "error" in output and len(output) == 1:
                result = ToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    success=False,
                    error=str(output["error"]),
                    latency_ms=latency_ms,
                )
            else:
                result = ToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    success=True,
                    result=output,
                    latency_ms=latency_ms,
                )
        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            result = ToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                success=False,
                error=str(exc),
                latency_ms=latency_ms,
            )

        await self._log_tool_execution(
            tool_call, result, session_id=session_id, task=task
        )
        return result

    async def _log_tool_execution(
        self,
        tool_call: ToolCall,
        tool_result: ToolResult,
        *,
        session_id: str,
        task: str,
    ) -> None:
        """Log a tool execution as a trajectory record."""
        try:
            await self._logger.log(
                action_name=f"tool:{tool_call.tool_name}",
                context_summary=f"Agent task: {task[:500]}",
                action_params=dict(tool_call.arguments),
                action_result=(
                    dict(tool_result.result) if tool_result.success
                    else {"error": tool_result.error}
                ),
                latency_ms=tool_result.latency_ms,
            )
        except Exception:
            log.exception("agent.log_failed", tool_name=tool_call.tool_name)
