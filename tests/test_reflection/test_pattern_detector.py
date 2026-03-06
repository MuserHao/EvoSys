"""Tests for PatternDetector."""

from __future__ import annotations

from evosys.reflection.pattern_detector import PatternDetector
from evosys.schemas._types import new_ulid
from evosys.schemas.trajectory import TrajectoryRecord


def _make_record(
    domain: str = "example.com",
    result: dict[str, object] | None = None,
    success: bool = True,
) -> TrajectoryRecord:
    return TrajectoryRecord(
        session_id=new_ulid(),
        iteration_index=0,
        context_summary=f"LLM extraction from https://{domain}/page",
        action_name="llm_extract",
        action_params={"target_schema": "{}"},
        action_result=result or {"title": "Test"},
        success=success,
    )


class TestDetect:
    def test_finds_pattern_above_threshold(self):
        records = {
            "example.com": [_make_record() for _ in range(5)],
        }
        detector = PatternDetector(min_frequency=3)
        candidates = detector.detect(records)
        assert len(candidates) == 1
        assert candidates[0].domain == "example.com"
        assert candidates[0].frequency == 5

    def test_skips_below_threshold(self):
        records = {
            "rare.com": [_make_record("rare.com") for _ in range(2)],
        }
        detector = PatternDetector(min_frequency=3)
        candidates = detector.detect(records)
        assert len(candidates) == 0

    def test_sorted_by_frequency(self):
        records = {
            "a.com": [_make_record("a.com") for _ in range(3)],
            "b.com": [_make_record("b.com") for _ in range(10)],
            "c.com": [_make_record("c.com") for _ in range(5)],
        }
        detector = PatternDetector(min_frequency=3)
        candidates = detector.detect(records)
        assert len(candidates) == 3
        assert candidates[0].domain == "b.com"
        assert candidates[1].domain == "c.com"
        assert candidates[2].domain == "a.com"

    def test_captures_trace_ids(self):
        records = [_make_record() for _ in range(4)]
        grouped = {"example.com": records}
        detector = PatternDetector(min_frequency=3)
        candidates = detector.detect(grouped)
        assert len(candidates[0].trace_ids) == 4

    def test_captures_sample_results(self):
        records = [
            _make_record(result={"title": f"Page {i}"}) for i in range(6)
        ]
        grouped = {"example.com": records}
        detector = PatternDetector(min_frequency=3)
        candidates = detector.detect(grouped)
        # Samples capped at 5
        assert len(candidates[0].sample_results) == 5

    def test_empty_input(self):
        detector = PatternDetector(min_frequency=3)
        assert detector.detect({}) == []

    def test_failed_records_excluded(self):
        """Failed records should be filtered out before counting frequency."""
        records = {
            "example.com": [
                _make_record(success=True),
                _make_record(success=True),
                _make_record(success=True),
                _make_record(success=False),
                _make_record(success=False),
            ],
        }
        detector = PatternDetector(min_frequency=3)
        candidates = detector.detect(records)
        assert len(candidates) == 1
        # Only 3 successful records should be counted
        assert candidates[0].frequency == 3

    def test_all_failed_records_excluded(self):
        """Domain with only failed records should not produce candidates."""
        records = {
            "fail.com": [_make_record("fail.com", success=False) for _ in range(5)],
        }
        detector = PatternDetector(min_frequency=3)
        candidates = detector.detect(records)
        assert len(candidates) == 0
