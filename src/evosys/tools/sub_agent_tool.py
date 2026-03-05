"""Sub-agent tool — delegate_task for the general agent.

Exposes the SubAgentManager as a tool the agent can call to break
complex tasks into simpler sub-tasks handled by child agents.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evosys.agents.sub_agent import SubAgentManager


class SubAgentTool:
    """Tool that delegates a sub-task to a child agent.

    The agent calls ``delegate_task(task="...")`` and receives the
    sub-agent's answer.  Supports both single tasks and parallel
    batches (via comma-separated tasks).
    """

    def __init__(
        self,
        sub_agent_manager: SubAgentManager,
        *,
        current_depth: int = 0,
    ) -> None:
        self._manager = sub_agent_manager
        self._current_depth = current_depth

    @property
    def name(self) -> str:
        return "delegate_task"

    @property
    def description(self) -> str:
        return (
            "Delegate a sub-task to a child agent that works independently. "
            "Use this to break complex tasks into simpler pieces. The child "
            "agent has access to the same tools. Provide a clear, self-contained "
            "task description. For multiple independent sub-tasks, separate "
            "them with '|||' to run them in parallel."
        )

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {
            "task": {
                "type": "string",
                "description": (
                    "The sub-task to delegate. For parallel tasks, "
                    "separate with '|||'"
                ),
            },
            "context": {
                "type": "string",
                "description": (
                    "Optional JSON context to pass to the sub-agent"
                ),
            },
        }

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        task_str = str(kwargs.get("task", "")).strip()
        context_str = str(kwargs.get("context", "")).strip()

        if not task_str:
            return {"error": "task must not be empty"}

        context: dict[str, object] | None = None
        if context_str:
            try:
                context = json.loads(context_str)
            except json.JSONDecodeError:
                context = {"raw_context": context_str}

        # Check for parallel tasks
        tasks = [t.strip() for t in task_str.split("|||") if t.strip()]

        if len(tasks) == 1:
            result = await self._manager.delegate(
                tasks[0],
                current_depth=self._current_depth,
                context=context,
            )
            if not result.success:
                return {"error": result.error or "Sub-agent failed"}
            return {
                "answer": result.answer,
                "total_tokens": result.total_tokens,
                "iterations": result.iterations,
            }

        results = await self._manager.delegate_parallel(
            tasks,
            current_depth=self._current_depth,
            context=context,
        )
        return {
            "results": [
                {
                    "task": r.task,
                    "answer": r.answer,
                    "success": r.success,
                    "error": r.error,
                }
                for r in results
            ],
            "total_tasks": len(results),
            "succeeded": sum(1 for r in results if r.success),
        }

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters_schema,
                    "required": ["task"],
                },
            },
        }
