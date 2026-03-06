"""Tests for continuous shadow evaluation in SkillExecutor."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from evosys.core.interfaces import BaseSkill
from evosys.core.types import Action
from evosys.executors.skill_executor import SkillExecutor
from evosys.reflection.shadow_evaluator import ShadowEvaluator
from evosys.schemas._types import (
    ImplementationType,
    MaturationStage,
    SkillStatus,
    new_ulid,
)
from evosys.schemas.skill import SkillRecord
from evosys.skills.registry import SkillRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeSkill(BaseSkill):
    def __init__(self, result: dict[str, object] | None = None):
        self._result = result or {"title": "Test"}

    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        return self._result

    def validate(self) -> bool:
        return True


def _make_record(
    name: str = "extract:test.com",
    shadow_sample_rate: float = 1.0,
) -> SkillRecord:
    return SkillRecord(
        skill_id=new_ulid(),
        name=name,
        description="Test skill",
        implementation_type=ImplementationType.ALGORITHMIC,
        implementation_path="test",
        test_suite_path="test",
        maturation_stage=MaturationStage.SYNTHESIZED,
        shadow_sample_rate=shadow_sample_rate,
    )


def _make_action(skill_name: str = "extract:test.com") -> Action:
    return Action(
        action_id=new_ulid(),
        name="invoke_skill",
        params={"skill_name": skill_name, "url": "http://test.com"},
    )


def _make_mock_llm(content: str = '{"title": "Test"}') -> MagicMock:
    mock_llm = MagicMock()
    resp = MagicMock()
    resp.content = content
    mock_llm.extract_json = AsyncMock(return_value=resp)
    return mock_llm


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestContinuousShadow:
    async def test_shadow_triggered_at_rate_1(self):
        """Shadow evaluation fires for every invocation at rate 1.0."""
        registry = SkillRegistry()
        record = _make_record(shadow_sample_rate=1.0)
        skill = _FakeSkill()
        registry.register(record, skill)

        shadow = ShadowEvaluator()
        mock_llm = _make_mock_llm()

        executor = SkillExecutor(
            registry, shadow_evaluator=shadow, llm=mock_llm
        )
        action = _make_action()
        obs = await executor.execute(action)
        assert obs.success

        # Give background task time to complete
        await asyncio.sleep(0.1)

        # LLM should have been called for shadow comparison
        assert mock_llm.extract_json.call_count == 1

    async def test_shadow_skipped_at_rate_0(self):
        """Shadow evaluation never fires at rate 0.0."""
        registry = SkillRegistry()
        record = _make_record(shadow_sample_rate=0.0)
        skill = _FakeSkill()
        registry.register(record, skill)

        shadow = ShadowEvaluator()
        mock_llm = _make_mock_llm()

        executor = SkillExecutor(
            registry, shadow_evaluator=shadow, llm=mock_llm
        )
        action = _make_action()
        obs = await executor.execute(action)
        assert obs.success

        await asyncio.sleep(0.05)
        assert mock_llm.extract_json.call_count == 0

    async def test_bayesian_increase_on_agreement(self):
        """Shadow agreement rate increases when comparison agrees."""
        registry = SkillRegistry()
        record = _make_record(shadow_sample_rate=1.0)
        record.shadow_agreement_rate = 0.5
        record.total_shadow_comparisons = 3
        record.confidence_score = 0.3  # starts below routing threshold
        skill = _FakeSkill({"title": "Test"})
        registry.register(record, skill)

        shadow = ShadowEvaluator()
        mock_llm = _make_mock_llm('{"title": "Test"}')

        executor = SkillExecutor(
            registry, shadow_evaluator=shadow, llm=mock_llm
        )

        # Execute and wait for shadow task
        await executor.execute(_make_action())
        await asyncio.sleep(0.1)

        # Rate should have increased from 0.5
        assert record.shadow_agreement_rate is not None
        assert record.shadow_agreement_rate > 0.5
        assert record.total_shadow_comparisons == 4

    async def test_bayesian_decrease_on_disagreement(self):
        """Shadow agreement rate decreases when comparison disagrees."""
        registry = SkillRegistry()
        record = _make_record(shadow_sample_rate=1.0)
        record.shadow_agreement_rate = 0.8
        record.total_shadow_comparisons = 3
        skill = _FakeSkill({"title": "SkillResult"})
        registry.register(record, skill)

        shadow = ShadowEvaluator()
        # LLM returns completely different output
        mock_llm = _make_mock_llm('{"title": "DifferentResult", "extra": "x"}')

        executor = SkillExecutor(
            registry, shadow_evaluator=shadow, llm=mock_llm
        )

        await executor.execute(_make_action())
        await asyncio.sleep(0.1)

        # Rate should have decreased from 0.8
        assert record.shadow_agreement_rate is not None
        assert record.shadow_agreement_rate < 0.8
        assert record.total_shadow_comparisons == 4

    async def test_degradation_threshold(self):
        """Skill marked DEGRADED after 5+ comparisons with rate < 0.5."""
        registry = SkillRegistry()
        record = _make_record(shadow_sample_rate=1.0)
        record.shadow_agreement_rate = 0.3
        record.total_shadow_comparisons = 4  # Will become 5 after next
        skill = _FakeSkill({"title": "Wrong"})
        registry.register(record, skill)

        shadow = ShadowEvaluator()
        # LLM returns completely different output → disagreement
        mock_llm = _make_mock_llm('{"title": "Correct", "extra": "v"}')

        executor = SkillExecutor(
            registry, shadow_evaluator=shadow, llm=mock_llm
        )

        await executor.execute(_make_action())
        await asyncio.sleep(0.1)

        assert record.total_shadow_comparisons == 5
        assert record.shadow_agreement_rate < 0.5
        assert record.status == SkillStatus.DEGRADED

    async def test_confidence_promoted_on_sustained_agreement(self):
        """confidence_score increases after sustained shadow agreement."""
        registry = SkillRegistry()
        record = _make_record(shadow_sample_rate=1.0)
        record.shadow_agreement_rate = 0.9
        record.total_shadow_comparisons = 5
        record.confidence_score = 0.3  # below routing threshold 0.7
        skill = _FakeSkill({"title": "Test"})
        registry.register(record, skill)

        shadow = ShadowEvaluator()
        mock_llm = _make_mock_llm('{"title": "Test"}')

        executor = SkillExecutor(
            registry, shadow_evaluator=shadow, llm=mock_llm
        )

        # Run several shadow evaluations with agreement
        for _ in range(5):
            await executor.execute(_make_action())
            await asyncio.sleep(0.1)

        # Confidence should have been promoted above starting 0.3
        assert record.confidence_score > 0.3
        assert record.total_shadow_comparisons == 10

    async def test_no_latency_impact(self):
        """Shadow evaluation runs in background and doesn't block execute()."""
        registry = SkillRegistry()
        record = _make_record(shadow_sample_rate=1.0)
        skill = _FakeSkill()
        registry.register(record, skill)

        # Make LLM slow
        slow_llm = MagicMock()
        resp = MagicMock()
        resp.content = '{"title": "Test"}'

        async def _slow_extract(**kwargs):
            await asyncio.sleep(0.5)
            return resp

        slow_llm.extract_json = _slow_extract

        shadow = ShadowEvaluator()
        executor = SkillExecutor(
            registry, shadow_evaluator=shadow, llm=slow_llm
        )

        import time
        t0 = time.monotonic()
        obs = await executor.execute(_make_action())
        elapsed = time.monotonic() - t0

        assert obs.success
        # Execute should return quickly, not waiting for the 0.5s LLM call
        assert elapsed < 0.3
