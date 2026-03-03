"""Tests for SliceCandidate schema."""

from __future__ import annotations

import pytest
from ulid import ULID

from evosys.schemas import ForgeStatus, ImplementationType, SliceCandidate


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


class TestLearnabilityFields:
    def test_defaults_are_none(self, sample_ulid: ULID) -> None:
        sc = SliceCandidate(
            action_sequence=["a"],
            frequency=1,
            occurrence_trace_ids=[sample_ulid],
            boundary_confidence=0.5,
        )
        assert sc.determinism_ratio is None
        assert sc.schema_consistency is None
        assert sc.avg_output_tokens is None
        assert sc.recommended_tier is None
        assert sc.learnability_score is None

    def test_with_learnability_signals(self, sample_ulid: ULID) -> None:
        sc = SliceCandidate(
            action_sequence=["fetch", "parse", "extract"],
            frequency=1,
            occurrence_trace_ids=[sample_ulid],
            boundary_confidence=0.88,
            determinism_ratio=0.95,
            schema_consistency=0.92,
            avg_output_tokens=150,
            recommended_tier=ImplementationType.ALGORITHMIC,
            learnability_score=0.87,
        )
        assert sc.determinism_ratio == 0.95
        assert sc.schema_consistency == 0.92
        assert sc.avg_output_tokens == 150
        assert sc.recommended_tier == ImplementationType.ALGORITHMIC
        assert sc.learnability_score == 0.87

    def test_learnability_score_bounds(self, sample_ulid: ULID) -> None:
        with pytest.raises(ValueError, match="greater than or equal to 0"):
            SliceCandidate(
                action_sequence=["a"],
                frequency=1,
                occurrence_trace_ids=[sample_ulid],
                boundary_confidence=0.5,
                learnability_score=-0.1,
            )

    def test_recommended_tier_all_values(self, sample_ulid: ULID) -> None:
        for tier in ImplementationType:
            sc = SliceCandidate(
                action_sequence=["a"],
                frequency=1,
                occurrence_trace_ids=[sample_ulid],
                boundary_confidence=0.5,
                recommended_tier=tier,
            )
            assert sc.recommended_tier == tier


class TestSliceOrjsonRoundTrip:
    def test_orjson_round_trip(self) -> None:
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
        assert restored.learnability_score == 0.72
