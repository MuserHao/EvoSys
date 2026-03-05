"""CRUD operations for scheduled tasks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import orjson
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from evosys.storage.models import ScheduledTaskRow


def _new_task_id() -> str:
    from evosys.schemas._types import new_ulid
    return str(new_ulid())


class ScheduleStore:
    """Create, read, update, and delete scheduled agent tasks."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(
        self,
        description: str,
        interval_seconds: int,
    ) -> str:
        """Create a new scheduled task and return its task_id."""
        now = datetime.now(UTC)
        task_id = _new_task_id()
        row = ScheduledTaskRow(
            task_id=task_id,
            description=description,
            interval_seconds=interval_seconds,
            next_run_at=now,  # run immediately on first tick
            last_run_at=None,
            last_result_json="",
            enabled=True,
            created_at=now,
        )
        async with self._session_factory() as session, session.begin():
            session.add(row)
        return task_id

    async def get(self, task_id: str) -> ScheduledTaskRow | None:
        """Return the row for *task_id*, or ``None`` if not found."""
        async with self._session_factory() as session:
            return await session.get(ScheduledTaskRow, task_id)

    async def list_enabled(self) -> list[ScheduledTaskRow]:
        """Return all enabled tasks, ordered by next_run_at."""
        async with self._session_factory() as session:
            stmt = (
                select(ScheduledTaskRow)
                .where(ScheduledTaskRow.enabled.is_(True))
                .order_by(ScheduledTaskRow.next_run_at)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_due(self, *, now: datetime | None = None) -> list[ScheduledTaskRow]:
        """Return enabled tasks whose next_run_at is at or before *now*."""
        now = now or datetime.now(UTC)
        async with self._session_factory() as session:
            stmt = (
                select(ScheduledTaskRow)
                .where(ScheduledTaskRow.enabled.is_(True))
                .where(ScheduledTaskRow.next_run_at <= now)
                .order_by(ScheduledTaskRow.next_run_at)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def record_result(
        self,
        task_id: str,
        result: dict[str, object],
    ) -> None:
        """Store the result of a completed run and advance next_run_at."""
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            row = await session.get(ScheduledTaskRow, task_id)
            if row is None:
                return
            row.last_run_at = now
            row.last_result_json = orjson.dumps(result).decode()
            row.next_run_at = now + timedelta(seconds=row.interval_seconds)

    async def disable(self, task_id: str) -> None:
        """Disable a scheduled task (stops it running but keeps the record)."""
        async with self._session_factory() as session, session.begin():
            row = await session.get(ScheduledTaskRow, task_id)
            if row is not None:
                row.enabled = False

    async def delete(self, task_id: str) -> None:
        """Permanently delete a scheduled task."""
        async with self._session_factory() as session, session.begin():
            row = await session.get(ScheduledTaskRow, task_id)
            if row is not None:
                await session.delete(row)
