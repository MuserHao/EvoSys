"""Tests for TrajectoryStore CRUD operations."""


from ulid import ULID

from evosys.schemas.trajectory import TrajectoryRecord
from evosys.storage.trajectory_store import TrajectoryStore


def _make_record(
    session_id: ULID | None = None,
    iteration_index: int = 0,
    **kwargs: object,
) -> TrajectoryRecord:
    defaults: dict[str, object] = {
        "session_id": session_id or ULID(),
        "iteration_index": iteration_index,
        "context_summary": "test context",
        "action_name": "test_action",
    }
    defaults.update(kwargs)
    return TrajectoryRecord(**defaults)  # type: ignore[arg-type]


class TestSaveAndRetrieve:
    async def test_round_trip_by_trace_id(self, trajectory_store: TrajectoryStore):
        rec = _make_record()
        await trajectory_store.save(rec)
        loaded = await trajectory_store.get_by_trace_id(str(rec.trace_id))
        assert loaded is not None
        assert loaded.trace_id == rec.trace_id
        assert loaded.action_name == rec.action_name

    async def test_round_trip_by_session_id(self, trajectory_store: TrajectoryStore):
        sid = ULID()
        r0 = _make_record(session_id=sid, iteration_index=0)
        r1 = _make_record(session_id=sid, iteration_index=1)
        await trajectory_store.save(r0)
        await trajectory_store.save(r1)
        loaded = await trajectory_store.get_by_session_id(str(sid))
        assert len(loaded) == 2
        assert loaded[0].iteration_index == 0
        assert loaded[1].iteration_index == 1

    async def test_nonexistent_returns_none(self, trajectory_store: TrajectoryStore):
        result = await trajectory_store.get_by_trace_id(str(ULID()))
        assert result is None


class TestSaveMany:
    async def test_save_many_round_trip(self, trajectory_store: TrajectoryStore):
        sid = ULID()
        records = [_make_record(session_id=sid, iteration_index=i) for i in range(3)]
        await trajectory_store.save_many(records)
        loaded = await trajectory_store.get_by_session_id(str(sid))
        assert len(loaded) == 3


class TestJsonDictRoundTrip:
    async def test_dict_serialization(self, trajectory_store: TrajectoryStore):
        params = {"url": "https://example.com", "count": 42}
        result = {"data": [1, 2, 3], "nested": {"key": "value"}}
        rec = _make_record(action_params=params, action_result=result)
        await trajectory_store.save(rec)
        loaded = await trajectory_store.get_by_trace_id(str(rec.trace_id))
        assert loaded is not None
        assert loaded.action_params == params
        assert loaded.action_result == result


class TestUlidStringRoundTrip:
    async def test_ulid_preserved(self, trajectory_store: TrajectoryStore):
        rec = _make_record()
        original_trace = rec.trace_id
        original_session = rec.session_id
        await trajectory_store.save(rec)
        loaded = await trajectory_store.get_by_trace_id(str(original_trace))
        assert loaded is not None
        assert loaded.trace_id == original_trace
        assert loaded.session_id == original_session


class TestNullableFields:
    async def test_parent_task_id_nullable(self, trajectory_store: TrajectoryStore):
        rec = _make_record(parent_task_id=None)
        await trajectory_store.save(rec)
        loaded = await trajectory_store.get_by_trace_id(str(rec.trace_id))
        assert loaded is not None
        assert loaded.parent_task_id is None

    async def test_parent_task_id_set(self, trajectory_store: TrajectoryStore):
        parent = ULID()
        rec = _make_record(parent_task_id=parent)
        await trajectory_store.save(rec)
        loaded = await trajectory_store.get_by_trace_id(str(rec.trace_id))
        assert loaded is not None
        assert loaded.parent_task_id == parent

    async def test_skill_used_nullable(self, trajectory_store: TrajectoryStore):
        rec = _make_record(skill_used=None)
        await trajectory_store.save(rec)
        loaded = await trajectory_store.get_by_trace_id(str(rec.trace_id))
        assert loaded is not None
        assert loaded.skill_used is None

    async def test_skill_used_set(self, trajectory_store: TrajectoryStore):
        rec = _make_record(skill_used="my_skill")
        await trajectory_store.save(rec)
        loaded = await trajectory_store.get_by_trace_id(str(rec.trace_id))
        assert loaded is not None
        assert loaded.skill_used == "my_skill"
