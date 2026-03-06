"""Tests for TrajectoryLogger."""

from ulid import ULID

from evosys.schemas.trajectory import TrajectoryRecord
from evosys.trajectory.logger import TrajectoryLogger


class TestLogCreatesRecord:
    async def test_returns_trajectory_record(self, trajectory_logger: TrajectoryLogger):
        rec = await trajectory_logger.log(
            action_name="test_action",
            context_summary="testing",
        )
        assert isinstance(rec, TrajectoryRecord)
        assert rec.action_name == "test_action"
        assert rec.context_summary == "testing"


class TestIterationAutoIncrement:
    async def test_increments(self, trajectory_logger: TrajectoryLogger):
        r0 = await trajectory_logger.log(action_name="a", context_summary="s")
        r1 = await trajectory_logger.log(action_name="b", context_summary="s")
        r2 = await trajectory_logger.log(action_name="c", context_summary="s")
        assert r0.iteration_index == 0
        assert r1.iteration_index == 1
        assert r2.iteration_index == 2


class TestSanitization:
    async def test_params_sanitized(self, trajectory_logger: TrajectoryLogger):
        rec = await trajectory_logger.log(
            action_name="test",
            context_summary="s",
            action_params={"api_key": "secret123", "url": "https://example.com"},
        )
        assert rec.action_params["api_key"] == "[REDACTED]"
        assert rec.action_params["url"] == "https://example.com"

    async def test_result_sanitized(self, trajectory_logger: TrajectoryLogger):
        rec = await trajectory_logger.log(
            action_name="test",
            context_summary="s",
            action_result={"password": "hunter2", "data": "ok"},
        )
        assert rec.action_result["password"] == "[REDACTED]"
        assert rec.action_result["data"] == "ok"

    async def test_none_params_become_empty_dict(self, trajectory_logger: TrajectoryLogger):
        rec = await trajectory_logger.log(
            action_name="test",
            context_summary="s",
        )
        assert rec.action_params == {}
        assert rec.action_result == {}


class TestSessionIdConsistent:
    async def test_same_session_id(self, trajectory_logger: TrajectoryLogger):
        r0 = await trajectory_logger.log(action_name="a", context_summary="s")
        r1 = await trajectory_logger.log(action_name="b", context_summary="s")
        assert r0.session_id == r1.session_id
        assert r0.session_id == trajectory_logger.session_id

    async def test_custom_session_id(self, trajectory_store):
        custom_sid = ULID()
        logger = TrajectoryLogger(trajectory_store, session_id=custom_sid)
        rec = await logger.log(action_name="a", context_summary="s")
        assert rec.session_id == custom_sid


class TestSuccessField:
    async def test_default_success_is_true(self, trajectory_logger: TrajectoryLogger):
        rec = await trajectory_logger.log(action_name="a", context_summary="s")
        assert rec.success is True

    async def test_explicit_success_false(self, trajectory_logger: TrajectoryLogger):
        rec = await trajectory_logger.log(
            action_name="a", context_summary="s", success=False
        )
        assert rec.success is False

    async def test_success_roundtrips_through_store(
        self, trajectory_store, trajectory_logger: TrajectoryLogger
    ):
        rec = await trajectory_logger.log(
            action_name="fail_action", context_summary="s", success=False
        )
        loaded = await trajectory_store.get_by_trace_id(str(rec.trace_id))
        assert loaded is not None
        assert loaded.success is False

    async def test_success_true_roundtrips(
        self, trajectory_store, trajectory_logger: TrajectoryLogger
    ):
        rec = await trajectory_logger.log(
            action_name="ok_action", context_summary="s", success=True
        )
        loaded = await trajectory_store.get_by_trace_id(str(rec.trace_id))
        assert loaded is not None
        assert loaded.success is True
