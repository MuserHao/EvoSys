"""Tests for SequenceDetector."""

from __future__ import annotations

import pytest
from ulid import ULID

from evosys.reflection.sequence_detector import (
    SequenceCandidate,
    SequenceDetector,
    _is_strict_subsequence,
)
from evosys.schemas.trajectory import TrajectoryRecord


def _make_record(
    session_id: ULID,
    iteration: int,
    action_name: str,
    latency_ms: float = 10.0,
    token_cost: int = 5,
    params: dict[str, object] | None = None,
    success: bool = True,
) -> TrajectoryRecord:
    return TrajectoryRecord(
        session_id=session_id,
        iteration_index=iteration,
        action_name=action_name,
        context_summary="Test context",
        latency_ms=latency_ms,
        token_cost=token_cost,
        action_params=params or {},
        success=success,
    )


def _make_session_records(
    session_id: ULID,
    actions: list[str],
    latency: float = 10.0,
    token_cost: int = 5,
) -> list[TrajectoryRecord]:
    return [
        _make_record(session_id, i, a, latency, token_cost)
        for i, a in enumerate(actions)
    ]


class TestSequenceDetector:
    def test_no_records(self) -> None:
        detector = SequenceDetector(min_frequency=2)
        assert detector.detect([]) == []

    def test_single_session_below_threshold(self) -> None:
        sid = ULID()
        records = _make_session_records(sid, ["tool:a", "tool:b", "tool:c"])
        detector = SequenceDetector(min_frequency=2)
        assert detector.detect(records) == []

    def test_detects_pair_across_sessions(self) -> None:
        records = []
        for _ in range(3):
            sid = ULID()
            records.extend(_make_session_records(sid, ["tool:web_fetch", "tool:extract"]))

        detector = SequenceDetector(min_frequency=3)
        candidates = detector.detect(records)
        assert len(candidates) >= 1
        # The pair should be detected
        found = False
        for c in candidates:
            if c.tool_sequence == ["tool:web_fetch", "tool:extract"]:
                assert c.frequency == 3
                found = True
        assert found

    def test_detects_longer_sequence(self) -> None:
        records = []
        for _ in range(4):
            sid = ULID()
            records.extend(
                _make_session_records(sid, ["tool:fetch", "tool:parse", "tool:store"])
            )

        detector = SequenceDetector(min_frequency=3, min_seq_length=2, max_seq_length=5)
        candidates = detector.detect(records)
        # Should detect the 3-tool sequence
        three_tool = [c for c in candidates if len(c.tool_sequence) == 3]
        assert len(three_tool) >= 1
        assert three_tool[0].tool_sequence == ["tool:fetch", "tool:parse", "tool:store"]

    def test_filters_non_tool_actions(self) -> None:
        """Only tool:* actions should be considered."""
        records = []
        for _ in range(3):
            sid = ULID()
            records.extend(_make_session_records(
                sid,
                ["llm_extract", "tool:a", "fetch_url", "tool:b"],
            ))

        detector = SequenceDetector(min_frequency=3)
        candidates = detector.detect(records)
        # Should detect tool:a -> tool:b
        found = any(c.tool_sequence == ["tool:a", "tool:b"] for c in candidates)
        assert found

    def test_session_counted_once(self) -> None:
        """Each session counts at most once for frequency."""
        sid = ULID()
        # Same pair appears twice in one session
        records = _make_session_records(
            sid, ["tool:a", "tool:b", "tool:a", "tool:b"]
        )
        detector = SequenceDetector(min_frequency=2)
        candidates = detector.detect(records)
        # Frequency should be 1 (one session), not 2
        for c in candidates:
            if c.tool_sequence == ["tool:a", "tool:b"]:
                assert c.frequency == 1

    def test_respects_min_seq_length(self) -> None:
        records = []
        for _ in range(3):
            sid = ULID()
            records.extend(_make_session_records(sid, ["tool:a", "tool:b"]))

        detector = SequenceDetector(min_frequency=3, min_seq_length=3)
        candidates = detector.detect(records)
        assert candidates == []

    def test_respects_max_seq_length(self) -> None:
        records = []
        for _ in range(3):
            sid = ULID()
            records.extend(
                _make_session_records(sid, ["tool:a", "tool:b", "tool:c", "tool:d"])
            )

        detector = SequenceDetector(min_frequency=3, max_seq_length=2)
        candidates = detector.detect(records)
        # All detected sequences should be length <= 2
        for c in candidates:
            assert len(c.tool_sequence) <= 2

    def test_ranking_by_frequency_times_length(self) -> None:
        records = []
        # 5 sessions with A->B->C
        for _ in range(5):
            sid = ULID()
            records.extend(_make_session_records(sid, ["tool:a", "tool:b", "tool:c"]))
        # 3 sessions with X->Y
        for _ in range(3):
            sid = ULID()
            records.extend(_make_session_records(sid, ["tool:x", "tool:y"]))

        detector = SequenceDetector(min_frequency=3)
        candidates = detector.detect(records)
        # A->B->C (freq=5, len=3, score=15) should rank above X->Y (freq=3, len=2, score=6)
        if len(candidates) >= 2:
            abc = [c for c in candidates if c.tool_sequence == ["tool:a", "tool:b", "tool:c"]]
            xy = [c for c in candidates if c.tool_sequence == ["tool:x", "tool:y"]]
            if abc and xy:
                abc_idx = candidates.index(abc[0])
                xy_idx = candidates.index(xy[0])
                assert abc_idx < xy_idx

    def test_subsequence_deduplication(self) -> None:
        """Shorter subsequences of detected longer ones should be removed."""
        records = []
        for _ in range(5):
            sid = ULID()
            records.extend(
                _make_session_records(sid, ["tool:a", "tool:b", "tool:c"])
            )

        detector = SequenceDetector(min_frequency=3)
        candidates = detector.detect(records)
        # If A->B->C is detected, A->B should not also appear as a separate candidate
        seqs = [tuple(c.tool_sequence) for c in candidates]
        if ("tool:a", "tool:b", "tool:c") in seqs:
            assert ("tool:a", "tool:b") not in seqs
            assert ("tool:b", "tool:c") not in seqs

    def test_canonical_form(self) -> None:
        records = []
        for _ in range(3):
            sid = ULID()
            records.extend(_make_session_records(sid, ["tool:a", "tool:b"]))

        detector = SequenceDetector(min_frequency=3)
        candidates = detector.detect(records)
        ab = [c for c in candidates if c.tool_sequence == ["tool:a", "tool:b"]]
        assert len(ab) == 1
        assert ab[0].canonical_form == "tool:a -> tool:b"

    def test_avg_latency_and_tokens(self) -> None:
        records = []
        for _ in range(3):
            sid = ULID()
            records.extend(
                _make_session_records(sid, ["tool:a", "tool:b"], latency=20.0, token_cost=10)
            )

        detector = SequenceDetector(min_frequency=3)
        candidates = detector.detect(records)
        ab = [c for c in candidates if c.tool_sequence == ["tool:a", "tool:b"]]
        assert len(ab) == 1
        assert ab[0].avg_latency_ms == pytest.approx(20.0, abs=1.0)
        assert ab[0].avg_token_cost >= 0

    def test_parameter_patterns_collected(self) -> None:
        records = []
        for i in range(3):
            sid = ULID()
            records.append(_make_record(sid, 0, "tool:fetch", params={"url": f"http://{i}.com"}))
            records.append(_make_record(sid, 1, "tool:parse", params={"format": "json"}))

        detector = SequenceDetector(min_frequency=3)
        candidates = detector.detect(records)
        fp = [c for c in candidates if c.tool_sequence == ["tool:fetch", "tool:parse"]]
        assert len(fp) == 1
        assert "url" in fp[0].parameter_patterns
        assert "format" in fp[0].parameter_patterns

    def test_sessions_with_different_sequences(self) -> None:
        """Different sessions with different patterns."""
        records = []
        # 3 sessions with A->B
        for _ in range(3):
            sid = ULID()
            records.extend(_make_session_records(sid, ["tool:a", "tool:b"]))
        # 3 sessions with C->D
        for _ in range(3):
            sid = ULID()
            records.extend(_make_session_records(sid, ["tool:c", "tool:d"]))

        detector = SequenceDetector(min_frequency=3)
        candidates = detector.detect(records)
        seqs = {tuple(c.tool_sequence) for c in candidates}
        assert ("tool:a", "tool:b") in seqs
        assert ("tool:c", "tool:d") in seqs

    def test_mixed_tool_and_non_tool_in_session(self) -> None:
        records = []
        for _ in range(3):
            sid = ULID()
            records.extend([
                _make_record(sid, 0, "tool:fetch"),
                _make_record(sid, 1, "llm_extract"),  # not a tool: action
                _make_record(sid, 2, "tool:parse"),
            ])

        detector = SequenceDetector(min_frequency=3)
        candidates = detector.detect(records)
        # Should detect tool:fetch -> tool:parse (contiguous in the tool-only sequence)
        found = any(c.tool_sequence == ["tool:fetch", "tool:parse"] for c in candidates)
        assert found

    def test_empty_sessions_below_min_length(self) -> None:
        records = []
        for _ in range(3):
            sid = ULID()
            records.append(_make_record(sid, 0, "tool:a"))
            # Only 1 tool action per session

        detector = SequenceDetector(min_frequency=3, min_seq_length=2)
        assert detector.detect(records) == []

    def test_failed_records_excluded_from_sequences(self) -> None:
        """Failed records should be dropped before sequence detection."""
        records = []
        for _ in range(3):
            sid = ULID()
            records.extend([
                _make_record(sid, 0, "tool:a", success=True),
                _make_record(sid, 1, "tool:b", success=False),  # failure breaks chain
                _make_record(sid, 2, "tool:c", success=True),
            ])
        # With failures filtered, each session has only tool:a, tool:c
        detector = SequenceDetector(min_frequency=3, min_seq_length=2)
        candidates = detector.detect(records)
        # tool:a -> tool:c should be detected (failures removed)
        found_ac = any(c.tool_sequence == ["tool:a", "tool:c"] for c in candidates)
        assert found_ac
        # tool:a -> tool:b should NOT be found
        found_ab = any(c.tool_sequence == ["tool:a", "tool:b"] for c in candidates)
        assert not found_ab


class TestIsStrictSubsequence:
    def test_is_subsequence(self) -> None:
        assert _is_strict_subsequence(["a", "b"], ["a", "b", "c"])
        assert _is_strict_subsequence(["b", "c"], ["a", "b", "c"])

    def test_not_subsequence(self) -> None:
        assert not _is_strict_subsequence(["a", "c"], ["a", "b", "c"])
        assert not _is_strict_subsequence(["d"], ["a", "b", "c"])

    def test_same_length(self) -> None:
        assert not _is_strict_subsequence(["a", "b"], ["a", "b"])

    def test_longer_than_candidate(self) -> None:
        assert not _is_strict_subsequence(["a", "b", "c"], ["a", "b"])


class TestSequenceCandidate:
    def test_creation(self) -> None:
        c = SequenceCandidate(
            tool_sequence=["tool:a", "tool:b"],
            frequency=5,
            session_ids=["s1", "s2", "s3", "s4", "s5"],
            avg_latency_ms=15.0,
            avg_token_cost=10,
            canonical_form="tool:a -> tool:b",
        )
        assert c.frequency == 5
        assert len(c.tool_sequence) == 2
        assert c.canonical_form == "tool:a -> tool:b"

    def test_defaults(self) -> None:
        c = SequenceCandidate(
            tool_sequence=["tool:a"],
            frequency=1,
            session_ids=["s1"],
            avg_latency_ms=0,
            avg_token_cost=0,
        )
        assert c.parameter_patterns == {}
        assert c.canonical_form == ""
