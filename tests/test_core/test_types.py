"""Tests for core types."""

from __future__ import annotations

import pytest
from ulid import ULID

from evosys.core.types import (
    Action,
    ActionPlan,
    IOPair,
    LearnabilityAssessment,
    Observation,
    ShadowComparison,
)
from evosys.schemas import ImplementationType


class TestAction:
    def test_construction(self) -> None:
        action = Action(name="fetch_url", params={"url": "https://example.com"})
        assert isinstance(action.action_id, ULID)
        assert action.name == "fetch_url"
        assert action.depends_on == []

    def test_with_dependencies(self, sample_ulid: ULID) -> None:
        action = Action(
            name="parse_html",
            params={},
            depends_on=[sample_ulid],
        )
        assert action.depends_on == [sample_ulid]

    def test_serialization(self) -> None:
        action = Action(name="test", params={"key": "value"})
        data = action.model_dump(mode="json")
        assert isinstance(data["action_id"], str)
        restored = Action.model_validate(data)
        assert restored.action_id == action.action_id


class TestActionPlan:
    def test_construction(self) -> None:
        actions = [Action(name="step1"), Action(name="step2")]
        plan = ActionPlan(
            task_description="Do the thing",
            actions=actions,
            reasoning="Because reasons",
        )
        assert isinstance(plan.plan_id, ULID)
        assert len(plan.actions) == 2
        assert plan.reasoning == "Because reasons"

    def test_empty_actions_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            ActionPlan(task_description="Do nothing", actions=[])

    def test_orjson_round_trip(self) -> None:
        plan = ActionPlan(
            task_description="Test plan",
            actions=[Action(name="a", params={"x": 1})],
        )
        raw = plan.model_dump_orjson()
        restored = ActionPlan.model_validate_orjson(raw)
        assert restored.plan_id == plan.plan_id
        assert restored.actions[0].name == "a"


class TestObservation:
    def test_success(self, sample_ulid: ULID) -> None:
        obs = Observation(
            action_id=sample_ulid,
            success=True,
            result={"data": [1, 2, 3]},
            latency_ms=50.3,
            token_cost=100,
        )
        assert obs.success is True
        assert obs.error is None

    def test_failure(self, sample_ulid: ULID) -> None:
        obs = Observation(
            action_id=sample_ulid,
            success=False,
            error="Connection timeout",
        )
        assert obs.success is False
        assert obs.error == "Connection timeout"

    def test_serialization(self, sample_ulid: ULID) -> None:
        obs = Observation(action_id=sample_ulid, success=True, result={"ok": True})
        raw = obs.model_dump_orjson()
        restored = Observation.model_validate_orjson(raw)
        assert restored.action_id == sample_ulid


class TestIOPair:
    def test_construction(self) -> None:
        pair = IOPair(
            input_data={"html": "<p>Hello</p>"},
            output_data={"text": "Hello"},
        )
        assert pair.input_data == {"html": "<p>Hello</p>"}
        assert pair.output_data == {"text": "Hello"}
        assert pair.trace_id is None

    def test_with_trace_id(self, sample_ulid: ULID) -> None:
        pair = IOPair(
            input_data={"x": 1},
            output_data={"y": 2},
            trace_id=sample_ulid,
        )
        assert pair.trace_id == sample_ulid

    def test_orjson_round_trip(self) -> None:
        pair = IOPair(
            input_data={"query": "test"},
            output_data={"result": [1, 2, 3]},
        )
        raw = pair.model_dump_orjson()
        restored = IOPair.model_validate_orjson(raw)
        assert restored.input_data == pair.input_data
        assert restored.output_data == pair.output_data


class TestShadowComparison:
    def test_agreement(self) -> None:
        comp = ShadowComparison(
            skill_output={"entities": ["Alice"]},
            llm_output={"entities": ["Alice"]},
            agreement=True,
            similarity_score=1.0,
        )
        assert comp.agreement is True
        assert comp.similarity_score == 1.0

    def test_disagreement(self) -> None:
        comp = ShadowComparison(
            skill_output={"entities": ["Alice"]},
            llm_output={"entities": ["Alice", "Bob"]},
            agreement=False,
            similarity_score=0.6,
            notes="Skill missed entity 'Bob'",
        )
        assert comp.agreement is False
        assert comp.notes == "Skill missed entity 'Bob'"

    def test_orjson_round_trip(self) -> None:
        comp = ShadowComparison(
            skill_output={"x": 1},
            llm_output={"x": 1},
            agreement=True,
            similarity_score=0.99,
        )
        raw = comp.model_dump_orjson()
        restored = ShadowComparison.model_validate_orjson(raw)
        assert restored.agreement is True
        assert restored.similarity_score == 0.99


class TestLearnabilityAssessment:
    def test_construction(self) -> None:
        assessment = LearnabilityAssessment(
            determinism_ratio=0.95,
            schema_consistency=0.92,
            avg_output_tokens=50,
            recommended_tier=ImplementationType.DETERMINISTIC,
            learnability_score=0.93,
            reasoning="High determinism, consistent schema, low output size",
        )
        assert assessment.recommended_tier == ImplementationType.DETERMINISTIC
        assert assessment.learnability_score == 0.93

    def test_hard_task_assessment(self) -> None:
        assessment = LearnabilityAssessment(
            determinism_ratio=0.3,
            schema_consistency=0.5,
            avg_output_tokens=2000,
            recommended_tier=ImplementationType.CLOUD_LLM,
            learnability_score=0.15,
            reasoning="Low determinism, inconsistent schema, requires reasoning",
        )
        assert assessment.recommended_tier == ImplementationType.CLOUD_LLM
        assert assessment.learnability_score == 0.15

    def test_orjson_round_trip(self) -> None:
        assessment = LearnabilityAssessment(
            determinism_ratio=0.8,
            schema_consistency=0.85,
            avg_output_tokens=100,
            recommended_tier=ImplementationType.CACHED_PROMPT,
            learnability_score=0.65,
        )
        raw = assessment.model_dump_orjson()
        restored = LearnabilityAssessment.model_validate_orjson(raw)
        assert restored.recommended_tier == ImplementationType.CACHED_PROMPT
        assert restored.learnability_score == 0.65
