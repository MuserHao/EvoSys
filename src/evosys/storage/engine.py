"""Async SQLAlchemy engine lifecycle helpers."""

from __future__ import annotations

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
