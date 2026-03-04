"""Reflection daemon — mines trajectories for recurring skill candidates."""

from __future__ import annotations

from ulid import ULID

from evosys.core.interfaces import BaseReflectionDaemon
from evosys.reflection.pattern_detector import PatternDetector
from evosys.schemas._types import ForgeStatus, new_ulid
from evosys.schemas.slice import SliceCandidate
from evosys.storage.trajectory_store import TrajectoryStore


class ReflectionDaemon(BaseReflectionDaemon):
    """Analyse trajectory data and emit skill candidates.

    Runs a single reflection cycle:
    1. Query trajectory store for LLM extractions grouped by domain.
    2. Detect recurring patterns using :class:`PatternDetector`.
    3. Convert patterns into :class:`SliceCandidate` objects.
    """

    def __init__(
        self,
        store: TrajectoryStore,
        detector: PatternDetector | None = None,
        min_frequency: int = 3,
    ) -> None:
        self._store = store
        self._detector = detector or PatternDetector(min_frequency=min_frequency)

    async def run_cycle(self) -> list[SliceCandidate]:
        """Analyse recent trajectories and return discovered candidates."""
        records_by_domain = await self._store.get_llm_extractions_by_domain()

        if not records_by_domain:
            return []

        patterns = self._detector.detect(records_by_domain)

        candidates: list[SliceCandidate] = []
        for pattern in patterns:
            trace_ulids = [ULID.from_str(tid) for tid in pattern.trace_ids]

            candidate = SliceCandidate(
                candidate_id=new_ulid(),
                action_sequence=[pattern.action_name],
                frequency=pattern.frequency,
                occurrence_trace_ids=trace_ulids,
                input_schema_inferred=_infer_schema(pattern.sample_params),
                output_schema_inferred=_infer_schema(pattern.sample_results),
                boundary_confidence=min(1.0, pattern.frequency / 10.0),
                forge_status=ForgeStatus.PENDING,
            )
            candidates.append(candidate)

        return candidates


def _infer_schema(samples: list[dict[str, object]]) -> dict[str, object]:
    """Infer a minimal schema from sample dicts.

    Returns a dict mapping field names to observed Python type names.
    """
    if not samples:
        return {}

    schema: dict[str, object] = {}
    for sample in samples:
        for key, value in sample.items():
            if key not in schema:
                schema[key] = type(value).__name__
    return schema
