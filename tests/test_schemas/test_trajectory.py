"""Tests for TrajectoryRecord schema."""

from __future__ import annotations

import pytest
from ulid import ULID

from evosys.schemas import TrajectoryRecord


class TestTrajectoryRecordConstruction:
    def test_minimal_construction(self, sample_session_id: ULID) -> None:
        rec = TrajectoryRecord(
            session_id=sample_session_id,
            iteration_index=0,
            context_summary="Testing trajectory logging",
            action_name="test_action",
        )
        assert isinstance(rec.trace_id, ULID)
        assert rec.session_id == sample_session_id
        assert rec.iteration_index == 0
        assert rec.llm_reasoning == ""
        assert rec.token_cost == 0
        assert rec.latency_ms == 0
        assert rec.skill_used is None
        assert rec.schema_version == 1

    def test_defaults_populated(self, sample_session_id: ULID) -> None:
        rec = TrajectoryRecord(
            session_id=sample_session_id,
            iteration_index=1,
            context_summary="Some context",
            action_name="do_something",
        )
        assert rec.timestamp_utc is not None
        assert rec.action_params == {}
        assert rec.action_result == {}


class TestTrajectoryUlidRoundTrip:
    def test_ulid_str_coercion(self, sample_session_id: ULID) -> None:
        sid_str = str(sample_session_id)
        rec = TrajectoryRecord(
            session_id=sid_str,  # type: ignore[arg-type]
            iteration_index=0,
            context_summary="Testing",
            action_name="act",
        )
        assert rec.session_id == sample_session_id

    def test_ulid_round_trip_via_json(self, sample_session_id: ULID) -> None:
        rec = TrajectoryRecord(
            session_id=sample_session_id,
            iteration_index=0,
            context_summary="Testing",
            action_name="act",
        )
        data = rec.model_dump(mode="json")
        assert isinstance(data["trace_id"], str)
        restored = TrajectoryRecord.model_validate(data)
        assert restored.trace_id == rec.trace_id
        assert restored.session_id == rec.session_id


class TestTrajectoryValidationRejections:
    def test_negative_iteration_index(self, sample_session_id: ULID) -> None:
        with pytest.raises(ValueError, match="greater than or equal to 0"):
            TrajectoryRecord(
                session_id=sample_session_id,
                iteration_index=-1,
                context_summary="Testing",
                action_name="act",
            )

    def test_empty_context_summary(self, sample_session_id: ULID) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            TrajectoryRecord(
                session_id=sample_session_id,
                iteration_index=0,
                context_summary="",
                action_name="act",
            )

    def test_future_schema_version(self, sample_session_id: ULID) -> None:
        with pytest.raises(ValueError, match="newer EvoSys release"):
            TrajectoryRecord(
                session_id=sample_session_id,
                iteration_index=0,
                context_summary="Testing",
                action_name="act",
                schema_version=999,
            )


class TestTrajectoryOrjsonRoundTrip:
    def test_orjson_serialization(self, sample_session_id: ULID) -> None:
        rec = TrajectoryRecord(
            session_id=sample_session_id,
            iteration_index=5,
            context_summary="Round-trip test",
            action_name="fetch_data",
            action_params={"url": "https://example.com"},
            action_result={"status": 200},
            token_cost=150,
            latency_ms=342.5,
        )
        raw = rec.model_dump_orjson()
        assert isinstance(raw, bytes)
        restored = TrajectoryRecord.model_validate_orjson(raw)
        assert restored.trace_id == rec.trace_id
        assert restored.action_params == {"url": "https://example.com"}
        assert restored.token_cost == 150
