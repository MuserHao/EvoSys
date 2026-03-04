"""Sequence detector — finds recurring tool-call patterns in trajectory data.

Analyses agent trajectories to identify tool-call sequences that are
invoked frequently across sessions. These candidates can be forged into
composite skills to reduce future LLM calls and latency.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from evosys.schemas.trajectory import TrajectoryRecord


@dataclass(frozen=True, slots=True)
class SequenceCandidate:
    """A recurring tool-call sequence detected across sessions."""

    tool_sequence: list[str]
    frequency: int
    session_ids: list[str]
    avg_latency_ms: float
    avg_token_cost: int
    parameter_patterns: dict[str, list[object]] = field(default_factory=dict)
    canonical_form: str = ""


class SequenceDetector:
    """Detect recurring tool-call sequences in agent trajectory data.

    Algorithm:
    1. Group trajectory records by ``session_id``
    2. Extract ordered ``action_name`` sequences per session
       (filtered to ``tool:*`` actions, sorted by ``iteration_index``)
    3. Extract all contiguous subsequences of length 2..max_seq_length
    4. Count frequency across sessions (each session counts at most once)
    5. Filter by ``min_frequency`` threshold
    6. Rank by ``frequency * len(sequence)``
    """

    def __init__(
        self,
        *,
        min_frequency: int = 3,
        min_seq_length: int = 2,
        max_seq_length: int = 10,
    ) -> None:
        self._min_frequency = min_frequency
        self._min_seq_length = min_seq_length
        self._max_seq_length = max_seq_length

    def detect(
        self,
        records: list[TrajectoryRecord],
    ) -> list[SequenceCandidate]:
        """Find recurring tool-call sequences in *records*."""
        # 1. Group by session
        sessions: dict[str, list[TrajectoryRecord]] = {}
        for rec in records:
            sid = str(rec.session_id)
            sessions.setdefault(sid, []).append(rec)

        # 2. Extract ordered tool sequences per session
        session_sequences: dict[str, list[str]] = {}
        for sid, recs in sessions.items():
            sorted_recs = sorted(recs, key=lambda r: r.iteration_index)
            tool_actions = [
                r.action_name for r in sorted_recs if r.action_name.startswith("tool:")
            ]
            if len(tool_actions) >= self._min_seq_length:
                session_sequences[sid] = tool_actions

        if not session_sequences:
            return []

        # 3. Extract contiguous subsequences and count per-session frequency
        # Key: canonical tuple, Value: set of session IDs
        subseq_sessions: dict[tuple[str, ...], set[str]] = {}
        for sid, actions in session_sequences.items():
            seen_in_session: set[tuple[str, ...]] = set()
            for seq_len in range(self._min_seq_length, self._max_seq_length + 1):
                for start in range(len(actions) - seq_len + 1):
                    subseq = tuple(actions[start : start + seq_len])
                    if subseq not in seen_in_session:
                        seen_in_session.add(subseq)
                        subseq_sessions.setdefault(subseq, set()).add(sid)

        # 4. Filter by min_frequency
        candidates: list[SequenceCandidate] = []
        for subseq, sids in subseq_sessions.items():
            freq = len(sids)
            if freq < self._min_frequency:
                continue

            # Compute average latency and token cost across sessions
            total_latency = 0.0
            total_tokens = 0
            match_count = 0
            param_patterns: dict[str, list[object]] = {}

            for sid in sids:
                recs = sessions.get(sid, [])
                tool_recs = [
                    r for r in sorted(recs, key=lambda r: r.iteration_index)
                    if r.action_name.startswith("tool:")
                ]
                # Find the matching subsequence in this session's records
                for start in range(len(tool_recs) - len(subseq) + 1):
                    window = tool_recs[start : start + len(subseq)]
                    if tuple(r.action_name for r in window) == subseq:
                        for rec in window:
                            total_latency += rec.latency_ms
                            total_tokens += rec.token_cost
                            match_count += 1
                            # Collect parameter patterns
                            for key, val in rec.action_params.items():
                                param_patterns.setdefault(key, []).append(val)
                        break

            avg_latency = total_latency / match_count if match_count > 0 else 0
            avg_tokens = total_tokens // max(match_count, 1)

            canonical = " -> ".join(subseq)
            candidates.append(
                SequenceCandidate(
                    tool_sequence=list(subseq),
                    frequency=freq,
                    session_ids=sorted(sids),
                    avg_latency_ms=avg_latency,
                    avg_token_cost=avg_tokens,
                    parameter_patterns=param_patterns,
                    canonical_form=canonical,
                )
            )

        # 5. Rank by frequency * sequence_length (higher is better)
        candidates.sort(key=lambda c: c.frequency * len(c.tool_sequence), reverse=True)

        # 6. Remove subsequences that are subsets of longer detected sequences
        #    (prefer the longest pattern)
        filtered: list[SequenceCandidate] = []
        for c in candidates:
            # Check if this is a strict subsequence of any already-accepted candidate
            is_subseq = False
            for accepted in filtered:
                if _is_strict_subsequence(c.tool_sequence, accepted.tool_sequence):
                    is_subseq = True
                    break
            if not is_subseq:
                filtered.append(c)

        return filtered


def _is_strict_subsequence(short: list[str], long: list[str]) -> bool:
    """Check if *short* is a contiguous subsequence of *long*."""
    if len(short) >= len(long):
        return False
    short_t = tuple(short)
    for start in range(len(long) - len(short) + 1):
        if tuple(long[start : start + len(short)]) == short_t:
            return True
    return False
