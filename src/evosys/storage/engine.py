"""Async SQLAlchemy engine lifecycle helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from evosys.storage.models import Base


async def init_engine(db_url: str) -> AsyncEngine:
    """Create an async engine and run ``CREATE TABLE`` for all models."""
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory bound to *engine*."""
    return async_sessionmaker(engine, expire_on_commit=False)


async def dispose_engine(engine: AsyncEngine) -> None:
    """Dispose of the engine, closing all connections."""
    await engine.dispose()


def upsert_stmt(
    table: Any,
    values: dict[str, Any],
    index_elements: list[str],
    update_set: dict[str, Any],
) -> Any:
    """Build a dialect-aware upsert (INSERT ... ON CONFLICT DO UPDATE).

    Works with SQLite and PostgreSQL. For other dialects, falls back
    to SQLite-style insert (works with most SQLAlchemy-supported DBs).
    """
    try:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        # Try PostgreSQL first (will be used if the engine is pg)
        stmt = (
            pg_insert(table)
            .values(**values)
            .on_conflict_do_update(
                index_elements=index_elements,
                set_=update_set,
            )
        )
        return stmt
    except Exception:
        pass

    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    return (
        sqlite_insert(table)
        .values(**values)
        .on_conflict_do_update(
            index_elements=index_elements,
            set_=update_set,
        )
    )
