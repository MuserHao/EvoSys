"""Cross-session key-value memory store backed by SQLite."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from evosys.storage.models import MemoryRow


class MemoryStore:
    """Persistent key-value store for agent memory across sessions.

    Keys are scoped by *namespace* (default ``"default"``) so that
    different users or contexts don't collide.  Values are stored as
    plain strings; callers are responsible for serialisation if they
    need structured data.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def set(self, key: str, value: str, *, namespace: str = "default") -> None:
        """Store *value* under *key* in *namespace*, overwriting if present."""
        now = datetime.now(UTC)
        stmt = (
            sqlite_insert(MemoryRow)
            .values(namespace=namespace, key=key, value=value, updated_at=now)
            .on_conflict_do_update(
                index_elements=["namespace", "key"],
                set_={"value": value, "updated_at": now},
            )
        )
        async with self._session_factory() as session, session.begin():
            await session.execute(stmt)

    async def get(self, key: str, *, namespace: str = "default") -> str | None:
        """Return the stored value for *key*, or ``None`` if not found."""
        async with self._session_factory() as session:
            row = await session.get(MemoryRow, (namespace, key))
            return row.value if row else None

    async def delete(self, key: str, *, namespace: str = "default") -> None:
        """Remove *key* from *namespace*. No-op if not found."""
        stmt = delete(MemoryRow).where(
            MemoryRow.namespace == namespace,
            MemoryRow.key == key,
        )
        async with self._session_factory() as session, session.begin():
            await session.execute(stmt)

    async def list_keys(self, *, namespace: str = "default") -> list[str]:
        """Return all keys in *namespace*, ordered alphabetically."""
        async with self._session_factory() as session:
            stmt = (
                select(MemoryRow.key)
                .where(MemoryRow.namespace == namespace)
                .order_by(MemoryRow.key)
            )
            result = await session.execute(stmt)
            return [row for (row,) in result.all()]
