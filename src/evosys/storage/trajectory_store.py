"""CRUD operations for trajectory records."""

from __future__ import annotations

import orjson
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ulid import ULID

from evosys.schemas.trajectory import TrajectoryRecord
from evosys.storage.models import TrajectoryRow


class TrajectoryStore:
    """Persist and retrieve :class:`TrajectoryRecord` instances."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, record: TrajectoryRecord) -> None:
        """Insert a single trajectory record."""
        row = self._to_row(record)
        async with self._session_factory() as session, session.begin():
            session.add(row)

    async def save_many(self, records: list[TrajectoryRecord]) -> None:
        """Insert multiple trajectory records in a single transaction."""
        rows = [self._to_row(r) for r in records]
        async with self._session_factory() as session, session.begin():
            session.add_all(rows)

    async def get_by_trace_id(self, trace_id: str) -> TrajectoryRecord | None:
        """Retrieve a single record by its trace_id, or ``None``."""
        async with self._session_factory() as session:
            row = await session.get(TrajectoryRow, trace_id)
            if row is None:
                return None
            return self._from_row(row)

    async def get_by_session_id(self, session_id: str) -> list[TrajectoryRecord]:
        """Retrieve all records for a session, ordered by iteration_index."""
        async with self._session_factory() as session:
            stmt = (
                select(TrajectoryRow)
                .where(TrajectoryRow.session_id == session_id)
                .order_by(TrajectoryRow.iteration_index)
            )
            result = await session.execute(stmt)
            return [self._from_row(row) for row in result.scalars().all()]

    @staticmethod
    def _to_row(record: TrajectoryRecord) -> TrajectoryRow:
        """Convert a Pydantic record to an ORM row."""
        return TrajectoryRow(
            trace_id=str(record.trace_id),
            session_id=str(record.session_id),
            parent_task_id=str(record.parent_task_id) if record.parent_task_id else None,
            timestamp_utc=record.timestamp_utc,
            iteration_index=record.iteration_index,
            context_summary=record.context_summary,
            llm_reasoning=record.llm_reasoning,
            action_name=record.action_name,
            action_params_json=orjson.dumps(record.action_params).decode(),
            action_result_json=orjson.dumps(record.action_result).decode(),
            token_cost=record.token_cost,
            latency_ms=record.latency_ms,
            skill_used=record.skill_used,
        )

    @staticmethod
    def _from_row(row: TrajectoryRow) -> TrajectoryRecord:
        """Convert an ORM row back to a Pydantic record."""
        return TrajectoryRecord(
            trace_id=ULID.from_str(row.trace_id),
            session_id=ULID.from_str(row.session_id),
            parent_task_id=ULID.from_str(row.parent_task_id) if row.parent_task_id else None,
            timestamp_utc=row.timestamp_utc,
            iteration_index=row.iteration_index,
            context_summary=row.context_summary,
            llm_reasoning=row.llm_reasoning,
            action_name=row.action_name,
            action_params=orjson.loads(row.action_params_json),
            action_result=orjson.loads(row.action_result_json),
            token_cost=row.token_cost,
            latency_ms=row.latency_ms,
            skill_used=row.skill_used,
        )
