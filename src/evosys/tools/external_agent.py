"""External agent tool — delegate tasks to Claude Code CLI.

Runs the ``claude`` CLI in non-interactive mode as a subprocess and
returns the structured JSON result.  The tool is registered like any
other external tool and its invocations flow through the normal
trajectory logging / evolution pipeline.

Uses ``--output-format stream-json`` to capture Claude Code's
intermediate tool-use events (NDJSON) alongside the final result.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from evosys.trajectory.logger import TrajectoryLogger

log = structlog.get_logger()


def _find_claude_binary() -> str | None:
    """Locate the ``claude`` binary on ``$PATH``, or return *None*."""
    return shutil.which("claude")


def _parse_stream_json(
    raw: str,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Parse NDJSON stream-json output from Claude Code.

    Returns ``(final_result, intermediate_steps)`` where
    *final_result* is the ``type: "result"`` message and
    *intermediate_steps* is a list of all other messages
    (typically ``assistant``, ``tool_use``, ``tool_result`` events).
    """
    final_result: dict[str, object] = {}
    intermediate_steps: list[dict[str, object]] = []

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue

        msg_type = msg.get("type", "")
        if msg_type == "result":
            final_result = msg
        else:
            intermediate_steps.append(msg)

    return final_result, intermediate_steps


class ClaudeCodeTool:
    """Delegate a task to Claude Code and return the result.

    Uses ``asyncio.create_subprocess_exec`` (not ``_shell``) with an
    explicit args list to avoid shell-injection risks.
    """

    def __init__(
        self,
        claude_path: str,
        *,
        timeout_s: float = 300.0,
        max_budget_usd: float = 0.0,
        model: str = "",
        max_output_bytes: int = 2_000_000,
        trajectory_logger: TrajectoryLogger | None = None,
    ) -> None:
        self._claude_path = claude_path
        self._timeout_s = timeout_s
        self._max_budget_usd = max_budget_usd
        self._model = model
        self._max_output_bytes = max_output_bytes
        self._trajectory_logger = trajectory_logger

    @property
    def name(self) -> str:
        return "claude_code"

    @property
    def description(self) -> str:
        return (
            "Delegate a task to Claude Code, an external AI coding agent "
            "with file editing, shell access, and agentic planning. Use "
            "this for complex software engineering tasks that benefit from "
            "Claude Code's built-in capabilities."
        )

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {
            "task": {
                "type": "string",
                "description": "The task description to delegate to Claude Code",
            },
            "working_dir": {
                "type": "string",
                "description": "Working directory for file operations",
            },
            "model": {
                "type": "string",
                "description": "Model override (sonnet, opus, haiku)",
            },
            "allowed_tools": {
                "type": "string",
                "description": (
                    "Comma-separated list of tools Claude Code can use"
                ),
            },
            "max_budget_usd": {
                "type": "number",
                "description": "Per-call cost ceiling in USD (0 = no limit)",
            },
        }

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        task = str(kwargs.get("task", "")).strip()
        if not task:
            return {"error": "task must not be empty"}

        working_dir = kwargs.get("working_dir")
        model = str(kwargs.get("model", "") or self._model).strip()
        allowed_tools = str(kwargs.get("allowed_tools", "")).strip()
        budget = float(str(kwargs.get("max_budget_usd", 0) or self._max_budget_usd))

        cwd: str | None = str(working_dir) if working_dir else None
        if cwd and not Path(cwd).is_dir():
            return {"error": f"working_dir does not exist: {cwd}"}

        args = [
            self._claude_path,
            "-p",
            task,
            "--output-format",
            "stream-json",
            "--dangerously-skip-permissions",
        ]
        if model:
            args.extend(["--model", model])
        if budget > 0:
            args.extend(["--max-budget-usd", str(budget)])
        if allowed_tools:
            args.extend(["--allowed-tools", allowed_tools])

        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout_s
            )
        except TimeoutError:
            if proc is not None:
                proc.kill()
                await proc.wait()
            return {"error": f"Claude Code timed out after {self._timeout_s}s"}

        stdout = stdout_bytes[: self._max_output_bytes].decode(errors="replace")
        stderr = stderr_bytes[: self._max_output_bytes].decode(errors="replace")

        if proc.returncode != 0:
            excerpt = stderr[:500] if stderr else stdout[:500]
            return {
                "error": (
                    f"Claude Code failed (exit {proc.returncode}): {excerpt}"
                )
            }

        # Parse NDJSON stream output
        final_result, intermediate_steps = _parse_stream_json(stdout)

        # Log intermediate steps as trajectory records
        await self._log_intermediate_steps(intermediate_steps, task)

        if final_result:
            return {
                "answer": final_result.get("result", stdout),
                "session_id": final_result.get("session_id", ""),
                "cost_usd": final_result.get("cost_usd", 0.0),
                "return_code": 0,
                "internal_steps": intermediate_steps,
            }

        # Fallback: try parsing entire stdout as single JSON
        try:
            data = json.loads(stdout)
            return {
                "answer": data.get("result", stdout),
                "session_id": data.get("session_id", ""),
                "cost_usd": data.get("cost_usd", 0.0),
                "return_code": 0,
                "internal_steps": [],
            }
        except (json.JSONDecodeError, TypeError):
            return {
                "answer": stdout,
                "session_id": "",
                "cost_usd": 0.0,
                "return_code": 0,
                "internal_steps": [],
            }

    async def _log_intermediate_steps(
        self,
        steps: list[dict[str, object]],
        task: str,
    ) -> None:
        """Log each intermediate Claude Code step as a trajectory record."""
        if not self._trajectory_logger or not steps:
            return

        for step in steps:
            step_type = str(step.get("type", "unknown"))
            # Extract tool name for tool_use/tool_result events
            tool_name = str(step.get("tool", step.get("name", step_type)))
            action_name = f"tool:claude_code:{tool_name}"

            try:
                await self._trajectory_logger.log(
                    action_name=action_name,
                    context_summary=f"Claude Code internal step: {task[:300]}",
                    action_params={
                        "step_type": step_type,
                        "tool": tool_name,
                    },
                    action_result={
                        k: v
                        for k, v in step.items()
                        if k not in ("type", "tool", "name")
                        and isinstance(v, (str, int, float, bool, type(None)))
                    },
                )
            except Exception:
                log.exception(
                    "claude_code.log_step_failed",
                    step_type=step_type,
                    tool=tool_name,
                )

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
