"""Tests for core interface ABCs."""

from __future__ import annotations

import pytest

from evosys.core.interfaces import (
    BaseExecutor,
    BaseForge,
    BaseLearnabilityEstimator,
    BaseOrchestrator,
    BaseReflectionDaemon,
    BaseShadowEvaluator,
    BaseSkill,
)
from evosys.core.types import (
    Action,
    ActionPlan,
    IOPair,
    LearnabilityAssessment,
    Observation,
    ShadowComparison,
)
from evosys.schemas import ImplementationType
from evosys.schemas.skill import SkillRecord
from evosys.schemas.slice import SliceCandidate


class TestCannotInstantiateABCs:
    def test_orchestrator(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            BaseOrchestrator()  # type: ignore[abstract]

    def test_skill(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            BaseSkill()  # type: ignore[abstract]

    def test_executor(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            BaseExecutor()  # type: ignore[abstract]

    def test_reflection_daemon(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            BaseReflectionDaemon()  # type: ignore[abstract]

    def test_forge(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            BaseForge()  # type: ignore[abstract]

    def test_shadow_evaluator(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            BaseShadowEvaluator()  # type: ignore[abstract]

    def test_learnability_estimator(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            BaseLearnabilityEstimator()  # type: ignore[abstract]


class TestPartialImplFails:
    def test_partial_skill_missing_validate(self) -> None:
        class PartialSkill(BaseSkill):
            async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
                return {}

        with pytest.raises(TypeError, match="abstract"):
            PartialSkill()  # type: ignore[abstract]


class TestConcreteSubclass:
    @pytest.mark.anyio()
    async def test_concrete_orchestrator(self) -> None:
        class MyOrchestrator(BaseOrchestrator):
            async def plan(self, task: str) -> ActionPlan:
                return ActionPlan(
                    task_description=task,
                    actions=[Action(name="do_it")],
                )

        orch = MyOrchestrator()
        plan = await orch.plan("test task")
        assert plan.task_description == "test task"
        assert len(plan.actions) == 1

    @pytest.mark.anyio()
    async def test_concrete_skill(self) -> None:
        class MySkill(BaseSkill):
            async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
                return {"result": "ok"}

            def validate(self) -> bool:
                return True

        skill = MySkill()
        result = await skill.invoke({})
        assert result == {"result": "ok"}
        assert skill.validate() is True

    @pytest.mark.anyio()
    async def test_concrete_executor(self) -> None:
        class MyExecutor(BaseExecutor):
            async def execute(self, action: Action) -> Observation:
                return Observation(action_id=action.action_id, success=True)

        executor = MyExecutor()
        action = Action(name="test")
        obs = await executor.execute(action)
        assert obs.success is True

    @pytest.mark.anyio()
    async def test_concrete_reflection_daemon(self) -> None:
        class MyDaemon(BaseReflectionDaemon):
            async def run_cycle(self) -> list[SliceCandidate]:
                return []

        daemon = MyDaemon()
        result = await daemon.run_cycle()
        assert result == []

    @pytest.mark.anyio()
    async def test_concrete_forge(self) -> None:
        class MyForge(BaseForge):
            async def forge(self, candidate: SliceCandidate) -> SkillRecord | None:
                return None

        from ulid import ULID

        forge = MyForge()
        candidate = SliceCandidate(
            action_sequence=["a"],
            frequency=1,
            occurrence_trace_ids=[ULID()],
            boundary_confidence=0.9,
        )
        result = await forge.forge(candidate)
        assert result is None

    @pytest.mark.anyio()
    async def test_concrete_shadow_evaluator(self) -> None:
        class MyShadowEval(BaseShadowEvaluator):
            async def compare(
                self,
                skill_output: dict[str, object],
                llm_output: dict[str, object],
                output_schema: dict[str, object],
            ) -> ShadowComparison:
                return ShadowComparison(
                    skill_output=skill_output,
                    llm_output=llm_output,
                    agreement=skill_output == llm_output,
                    similarity_score=1.0 if skill_output == llm_output else 0.5,
                )

        evaluator = MyShadowEval()
        result = await evaluator.compare({"x": 1}, {"x": 1}, {})
        assert result.agreement is True
        assert result.similarity_score == 1.0

        result2 = await evaluator.compare({"x": 1}, {"x": 2}, {})
        assert result2.agreement is False

    @pytest.mark.anyio()
    async def test_concrete_learnability_estimator(self) -> None:
        class MyEstimator(BaseLearnabilityEstimator):
            async def estimate(
                self,
                candidate: SliceCandidate,
                examples: list[IOPair],
            ) -> LearnabilityAssessment:
                return LearnabilityAssessment(
                    determinism_ratio=0.9,
                    schema_consistency=0.85,
                    avg_output_tokens=100,
                    recommended_tier=ImplementationType.ALGORITHMIC,
                    learnability_score=0.8,
                    reasoning="Looks deterministic enough for code synthesis",
                )

        from ulid import ULID

        estimator = MyEstimator()
        candidate = SliceCandidate(
            action_sequence=["fetch", "parse"],
            frequency=2,
            occurrence_trace_ids=[ULID(), ULID()],
            boundary_confidence=0.85,
        )
        examples = [
            IOPair(input_data={"url": "a"}, output_data={"text": "b"}),
            IOPair(input_data={"url": "c"}, output_data={"text": "d"}),
        ]
        result = await estimator.estimate(candidate, examples)
        assert result.recommended_tier == ImplementationType.ALGORITHMIC
        assert result.learnability_score == 0.8
