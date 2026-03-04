"""Tests for SliceCandidate schema."""

from __future__ import annotations

import pytest
from ulid import ULID

from evosys.schemas import ForgeStatus, ImplementationType, SliceCandidate


def _minimal(sample_ulid: ULID, **overrides: object) -> SliceCandidate:
    return SliceCandidate(
        action_sequence=["fetch_html", "parse_table"],
        frequency=1,
        occurrence_trace_ids=[sample_ulid],
        boundary_confidence=0.85,
        **overrides,  # type: ignore[arg-type]
    )


class TestSliceCandidateDefaults:
    def test_minimal_construction(self, sample_ulid: ULID) -> None:
        sc = _minimal(sample_ulid)
        assert isinstance(sc.candidate_id, ULID)
        assert sc.forge_status == ForgeStatus.PENDING
        assert sc.input_schema_inferred == {}
        assert sc.output_schema_inferred == {}


class TestSliceCrossFieldValidation:
    """These validators are EvoSys-authored — worth testing."""

    def test_frequency_trace_ids_mismatch_rejected(self, sample_ulid: ULID) -> None:
        with pytest.raises(ValueError, match=r"frequency.*must equal.*len"):
            SliceCandidate(
                action_sequence=["a"],
                frequency=5,
                occurrence_trace_ids=[sample_ulid],
                boundary_confidence=0.5,
            )

    def test_empty_action_sequence_rejected(self, sample_ulid: ULID) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            SliceCandidate(
                action_sequence=[],
                frequency=1,
                occurrence_trace_ids=[sample_ulid],
                boundary_confidence=0.5,
            )


class TestSliceOrjsonRoundTrip:
    def test_full_round_trip(self) -> None:
        ids = [ULID(), ULID()]
        sc = SliceCandidate(
            action_sequence=["step1", "step2"],
            frequency=2,
            occurrence_trace_ids=ids,
            boundary_confidence=0.77,
            determinism_ratio=0.85,
            schema_consistency=0.90,
            avg_output_tokens=200,
            recommended_tier=ImplementationType.CACHED_PROMPT,
            learnability_score=0.72,
        )
        raw = sc.model_dump_orjson()
        restored = SliceCandidate.model_validate_orjson(raw)
        assert restored.candidate_id == sc.candidate_id
        assert restored.action_sequence == ["step1", "step2"]
        assert restored.occurrence_trace_ids == ids
        assert restored.determinism_ratio == 0.85
        assert restored.recommended_tier == ImplementationType.CACHED_PROMPT
