"""Tests for StrategyExtractor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from evosys.llm.client import LLMResponse
from evosys.reflection.strategy_extractor import StrategyExtractor
from evosys.schemas._types import new_ulid
from evosys.schemas.trajectory import TrajectoryRecord
from evosys.skills.registry import SkillRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_records(
    n: int = 6,
    *,
    action_name: str = "tool:claude_code:Bash",
) -> list[TrajectoryRecord]:
    sid = new_ulid()
    return [
        TrajectoryRecord(
            session_id=sid,
            iteration_index=i,
            action_name=action_name,
            context_summary=f"Step {i}",
            action_result={"cost_usd": 0.005},
        )
        for i in range(n)
    ]


def _mock_llm(content: str = "") -> MagicMock:
    llm = MagicMock()
    resp = LLMResponse(
        content=content,
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        model="test",
    )
    llm.complete = AsyncMock(return_value=resp)
    return llm


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStrategyExtractor:
    async def test_extracts_from_complex_session(self):
        """Extracts a strategy from a session with enough steps/cost."""
        llm = _mock_llm(
            '{"name": "git_bisect", "description": "Use git bisect for debugging", '
            '"prompt_template": "When debugging, use git bisect to find the bad commit"}'
        )
        registry = SkillRegistry()
        extractor = StrategyExtractor(
            llm, registry, min_steps=3, min_cost_usd=0.01
        )

        records = _make_records(6)
        record = await extractor.extract_from_session(records, 0.05)

        assert record is not None
        assert record.name == "strategy:git_bisect"
        assert "strategy:git_bisect" in registry

    async def test_skips_cheap_session(self):
        """Sessions below min_cost_usd are skipped."""
        llm = _mock_llm()
        registry = SkillRegistry()
        extractor = StrategyExtractor(
            llm, registry, min_steps=3, min_cost_usd=1.0
        )

        records = _make_records(10)
        result = await extractor.extract_from_session(records, 0.001)

        assert result is None
        llm.complete.assert_not_called()

    async def test_skips_short_session(self):
        """Sessions below min_steps are skipped."""
        llm = _mock_llm()
        registry = SkillRegistry()
        extractor = StrategyExtractor(
            llm, registry, min_steps=5, min_cost_usd=0.0
        )

        records = _make_records(3)
        result = await extractor.extract_from_session(records, 1.0)

        assert result is None
        llm.complete.assert_not_called()

    async def test_duplicate_prevention(self):
        """Won't extract the same strategy twice."""
        llm = _mock_llm(
            '{"name": "same_strategy", "description": "Test", '
            '"prompt_template": "Do the thing"}'
        )
        registry = SkillRegistry()
        extractor = StrategyExtractor(
            llm, registry, min_steps=3, min_cost_usd=0.0
        )

        records = _make_records(6)
        r1 = await extractor.extract_from_session(records, 0.1)
        assert r1 is not None

        r2 = await extractor.extract_from_session(records, 0.1)
        assert r2 is None

    async def test_llm_failure_handling(self):
        """Gracefully handles LLM errors."""
        llm = _mock_llm()
        llm.complete = AsyncMock(side_effect=RuntimeError("LLM down"))
        registry = SkillRegistry()
        extractor = StrategyExtractor(
            llm, registry, min_steps=3, min_cost_usd=0.0
        )

        records = _make_records(6)
        result = await extractor.extract_from_session(records, 0.1)
        assert result is None
