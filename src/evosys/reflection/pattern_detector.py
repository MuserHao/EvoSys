"""Frequency-based pattern detector for trajectory data.

Groups LLM-handled extractions by domain and identifies recurring
patterns that could be distilled into skills.  No ML dependencies —
pure counting and grouping.
"""

from __future__ import annotations

from dataclasses import dataclass

from evosys.schemas.trajectory import TrajectoryRecord


@dataclass(frozen=True, slots=True)
class PatternCandidate:
    """A recurring extraction pattern detected in trajectory data."""

    domain: str
    action_name: str
    frequency: int
    trace_ids: list[str]
    sample_params: list[dict[str, object]]
    sample_results: list[dict[str, object]]


class PatternDetector:
    """Detect recurring LLM extraction patterns by domain frequency.

    Scans trajectory records for ``llm_extract`` actions that were *not*
    handled by a skill (i.e., ``skill_used is None``), groups them by
    domain, and returns candidates above a frequency threshold.
    """

    def __init__(self, min_frequency: int = 3) -> None:
        self._min_frequency = min_frequency

    def detect(
        self,
        records_by_domain: dict[str, list[TrajectoryRecord]],
    ) -> list[PatternCandidate]:
        """Detect patterns from pre-grouped domain → records mapping.

        Returns candidates sorted by frequency (highest first).
        """
        candidates: list[PatternCandidate] = []

        for domain, records in records_by_domain.items():
            if len(records) < self._min_frequency:
                continue

            trace_ids = [str(r.trace_id) for r in records]
            sample_params = [
                dict(r.action_params) for r in records[:5]
            ]
            sample_results = [
                dict(r.action_result) for r in records[:5]
            ]

            candidates.append(
                PatternCandidate(
                    domain=domain,
                    action_name="llm_extract",
                    frequency=len(records),
                    trace_ids=trace_ids,
                    sample_params=sample_params,
                    sample_results=sample_results,
                )
            )

        candidates.sort(key=lambda c: c.frequency, reverse=True)
        return candidates
