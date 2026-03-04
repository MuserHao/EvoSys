"""Shared test fixtures."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from ulid import ULID

from evosys.storage.models import Base
from evosys.storage.trajectory_store import TrajectoryStore
from evosys.trajectory.logger import TrajectoryLogger


@pytest.fixture()
def sample_ulid() -> ULID:
    return ULID()


@pytest.fixture()
def sample_session_id() -> ULID:
    return ULID()


@pytest.fixture()
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
def session_factory(async_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest.fixture()
def trajectory_store(session_factory) -> TrajectoryStore:
    return TrajectoryStore(session_factory)


@pytest.fixture()
def trajectory_logger(trajectory_store) -> TrajectoryLogger:
    return TrajectoryLogger(trajectory_store)
