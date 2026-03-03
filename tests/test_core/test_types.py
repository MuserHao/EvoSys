"""Tests for core types (Action, ActionPlan, Observation)."""

from __future__ import annotations

from ulid import ULID

from evosys.core.types import Action, ActionPlan, Observation


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
        import pytest

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
