"""Trajectory logger — auto-sanitizes and auto-increments."""

from __future__ import annotations

import structlog
from ulid import ULID

from evosys.schemas._types import new_ulid
from evosys.schemas.trajectory import TrajectoryRecord
from evosys.storage.trajectory_store import TrajectoryStore
from evosys.trajectory.sanitizer import sanitize_dict

log = structlog.get_logger()


class TrajectoryLogger:
    """Log agent actions to the trajectory store with auto-sanitization."""

    def __init__(
        self,
        store: TrajectoryStore,
        session_id: ULID | None = None,
    ) -> None:
        self._store = store
        self.session_id = session_id or new_ulid()
        self._iteration = 0

    async def log(
        self,
        *,
        action_name: str,
        context_summary: str,
        action_params: dict[str, object] | None = None,
        action_result: dict[str, object] | None = None,
        llm_reasoning: str = "",
        token_cost: int = 0,
        latency_ms: float = 0.0,
        skill_used: str | None = None,
        parent_task_id: ULID | None = None,
        success: bool = True,
    ) -> TrajectoryRecord:
        """Create, sanitize, persist, and return a trajectory record."""
        sanitized_params = sanitize_dict(action_params) if action_params else {}
        sanitized_result = sanitize_dict(action_result) if action_result else {}

        record = TrajectoryRecord(
            session_id=self.session_id,
            parent_task_id=parent_task_id,
            iteration_index=self._iteration,
            context_summary=context_summary,
            llm_reasoning=llm_reasoning,
            action_name=action_name,
            action_params=sanitized_params,
            action_result=sanitized_result,
            token_cost=token_cost,
            latency_ms=latency_ms,
            skill_used=skill_used,
            success=success,
        )

        await self._store.save(record)
        self._iteration += 1

        log.info(
            "trajectory.logged",
            trace_id=str(record.trace_id),
            session_id=str(self.session_id),
            action_name=action_name,
            iteration=record.iteration_index,
        )

        return record
