"""Tests for SliceCandidate schema."""

from __future__ import annotations

import pytest
from ulid import ULID

from evosys.schemas import ForgeStatus, SliceCandidate


class TestSliceCandidateConstruction:
    def test_minimal_construction(self, sample_ulid: ULID) -> None:
        sc = SliceCandidate(
            action_sequence=["fetch_html", "parse_table"],
            frequency=1,
            occurrence_trace_ids=[sample_ulid],
            boundary_confidence=0.85,
        )
        assert isinstance(sc.candidate_id, ULID)
        assert sc.forge_status == ForgeStatus.PENDING
        assert sc.input_schema_inferred == {}
        assert sc.output_schema_inferred == {}

    def test_full_construction(self) -> None:
        ids = [ULID(), ULID(), ULID()]
        sc = SliceCandidate(
            action_sequence=["a", "b", "c"],
            frequency=3,
            occurrence_trace_ids=ids,
            boundary_confidence=0.92,
            input_schema_inferred={"type": "object"},
            output_schema_inferred={"type": "array"},
            forge_status=ForgeStatus.FORGING,
        )
        assert sc.frequency == 3
        assert len(sc.occurrence_trace_ids) == 3


class TestSliceValidation:
    def test_frequency_trace_ids_mismatch(self, sample_ulid: ULID) -> None:
        with pytest.raises(ValueError, match=r"frequency.*must equal.*len"):
            SliceCandidate(
                action_sequence=["a"],
                frequency=5,
                occurrence_trace_ids=[sample_ulid],
                boundary_confidence=0.5,
            )

    def test_empty_action_sequence(self, sample_ulid: ULID) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            SliceCandidate(
                action_sequence=[],
                frequency=1,
                occurrence_trace_ids=[sample_ulid],
                boundary_confidence=0.5,
            )

    def test_empty_occurrence_trace_ids(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            SliceCandidate(
                action_sequence=["a"],
                frequency=0,
                occurrence_trace_ids=[],
                boundary_confidence=0.5,
            )


class TestSliceOrjsonRoundTrip:
    def test_orjson_round_trip(self) -> None:
        ids = [ULID(), ULID()]
        sc = SliceCandidate(
            action_sequence=["step1", "step2"],
            frequency=2,
            occurrence_trace_ids=ids,
            boundary_confidence=0.77,
        )
        raw = sc.model_dump_orjson()
        restored = SliceCandidate.model_validate_orjson(raw)
        assert restored.candidate_id == sc.candidate_id
        assert restored.action_sequence == ["step1", "step2"]
        assert restored.occurrence_trace_ids == ids
