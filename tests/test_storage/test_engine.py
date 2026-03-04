"""Tests for storage engine lifecycle."""

from sqlalchemy.ext.asyncio import create_async_engine

from evosys.storage.engine import dispose_engine, init_engine, make_session_factory
from evosys.storage.models import Base, TrajectoryRow


class TestInitEngine:
    async def test_creates_tables(self):
        engine = await init_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            tables = await conn.run_sync(
                lambda sync_conn: list(Base.metadata.tables.keys())
            )
        assert "trajectory_records" in tables
        await dispose_engine(engine)

    async def test_dispose_works(self):
        engine = await init_engine("sqlite+aiosqlite:///:memory:")
        await dispose_engine(engine)
        # No error raised means success.


class TestMakeSessionFactory:
    async def test_session_factory_callable(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = make_session_factory(engine)
        async with factory() as session:
            # Can execute a simple query without error.
            result = await session.execute(
                TrajectoryRow.__table__.select()  # type: ignore[union-attr]
            )
            rows = result.all()
            assert rows == []
        await engine.dispose()
