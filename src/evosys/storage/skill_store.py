"""Persistence layer for forged skills.

Only runtime-synthesised skills are stored here.  Built-in hand-crafted
skills (HackerNews, GitHub, etc.) reload from Python source on every
startup and are never written to this table.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NamedTuple

import orjson
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from evosys.schemas._types import SkillStatus
from evosys.schemas.skill import SkillRecord
from evosys.storage.engine import upsert_stmt
from evosys.storage.models import SkillRow


class PersistedSkill(NamedTuple):
    """A record loaded from the DB, ready to be recompiled and re-registered."""

    record: SkillRecord
    source_code: str


class SkillStore:
    """Save and reload forged skills across process restarts."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, record: SkillRecord, source_code: str) -> None:
        """Upsert a forged skill.  Overwrites if the name already exists."""
        now = datetime.now(UTC)
        record_json = orjson.dumps(record.model_dump(mode="json")).decode()
        stmt = upsert_stmt(
            SkillRow,
            values={
                "name": record.name,
                "record_json": record_json,
                "source_code": source_code,
                "created_at": now,
                "updated_at": now,
            },
            index_elements=["name"],
            update_set={
                "record_json": record_json,
                "source_code": source_code,
                "updated_at": now,
            },
        )
        async with self._session_factory() as session, session.begin():
            await session.execute(stmt)

    async def load_all(self) -> list[PersistedSkill]:
        """Return all persisted forged skills, ordered by creation time."""
        async with self._session_factory() as session:
            stmt = select(SkillRow).order_by(SkillRow.created_at)
            result = await session.execute(stmt)
            rows = result.scalars().all()

        out: list[PersistedSkill] = []
        for row in rows:
            try:
                record = SkillRecord.model_validate(orjson.loads(row.record_json))
                out.append(PersistedSkill(record=record, source_code=row.source_code))
            except Exception:
                # Corrupted or schema-incompatible row — skip silently.
                # The evolution loop will re-forge from trajectory data.
                pass
        return out

    async def update_status(self, name: str, status: SkillStatus) -> None:
        """Persist a status change (e.g. ACTIVE → DEGRADED)."""
        async with self._session_factory() as session, session.begin():
            row = await session.get(SkillRow, name)
            if row is None:
                return
            data = orjson.loads(row.record_json)
            data["status"] = status.value
            row.record_json = orjson.dumps(data).decode()
            row.updated_at = datetime.now(UTC)

    async def update_shadow(
        self,
        name: str,
        agreement_rate: float,
        total_comparisons: int,
    ) -> None:
        """Persist updated shadow evaluation metrics."""
        async with self._session_factory() as session, session.begin():
            row = await session.get(SkillRow, name)
            if row is None:
                return
            data = orjson.loads(row.record_json)
            data["shadow_agreement_rate"] = round(agreement_rate, 4)
            data["total_shadow_comparisons"] = total_comparisons
            row.record_json = orjson.dumps(data).decode()
            row.updated_at = datetime.now(UTC)

    async def delete(self, name: str) -> None:
        """Remove a persisted skill by name. No-op if not found."""
        from sqlalchemy import delete as sa_delete
        stmt = sa_delete(SkillRow).where(SkillRow.name == name)
        async with self._session_factory() as session, session.begin():
            await session.execute(stmt)
