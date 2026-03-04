"""Tests for SkillExecutor."""

from __future__ import annotations

from unittest.mock import AsyncMock

from evosys.core.interfaces import BaseSkill
from evosys.core.types import Action
from evosys.executors.skill_executor import SkillExecutor
from evosys.schemas._types import ImplementationType
from evosys.schemas.skill import SkillRecord
from evosys.skills.registry import SkillRegistry


class _StubSkill(BaseSkill):
    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        return {"extracted": True, "url": input_data.get("url", "")}

    def validate(self) -> bool:
        return True


class _ExplodingSkill(BaseSkill):
    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("skill exploded")

    def validate(self) -> bool:
        return True


def _make_record(name: str = "extract:example.com") -> SkillRecord:
    return SkillRecord(
        name=name,
        description="Stub skill",
        implementation_type=ImplementationType.DETERMINISTIC,
        implementation_path="skills/stub.py",
        test_suite_path="tests/test_stub.py",
    )


def _make_action(
    skill_name: str = "extract:example.com", **extra: object
) -> Action:
    params: dict[str, object] = {"skill_name": skill_name, **extra}
    return Action(name="invoke_skill", params=params)


class TestSuccessfulInvocation:
    async def test_returns_successful_observation(self):
        reg = SkillRegistry()
        reg.register(_make_record(), _StubSkill())
        executor = SkillExecutor(reg)
        obs = await executor.execute(_make_action(url="https://example.com"))
        assert obs.success is True
        assert obs.result["extracted"] is True

    async def test_latency_measured(self):
        reg = SkillRegistry()
        reg.register(_make_record(), _StubSkill())
        executor = SkillExecutor(reg)
        obs = await executor.execute(_make_action())
        assert obs.latency_ms >= 0

    async def test_invocation_count_incremented(self):
        reg = SkillRegistry()
        reg.register(_make_record(), _StubSkill())
        executor = SkillExecutor(reg)
        await executor.execute(_make_action())
        entry = reg.lookup("extract:example.com")
        assert entry is not None
        assert entry.invocation_count == 1

    async def test_token_cost_is_zero(self):
        reg = SkillRegistry()
        reg.register(_make_record(), _StubSkill())
        executor = SkillExecutor(reg)
        obs = await executor.execute(_make_action())
        assert obs.token_cost == 0

    async def test_skill_name_excluded_from_input_data(self):
        reg = SkillRegistry()
        spy = AsyncMock(spec=BaseSkill)
        spy.validate.return_value = True
        spy.invoke = AsyncMock(return_value={"ok": True})
        reg.register(_make_record(), spy)
        executor = SkillExecutor(reg)
        await executor.execute(_make_action(url="https://example.com"))
        spy.invoke.assert_awaited_once_with({"url": "https://example.com"})


class TestErrorHandling:
    async def test_missing_skill_name_param(self):
        reg = SkillRegistry()
        executor = SkillExecutor(reg)
        action = Action(name="invoke_skill", params={})
        obs = await executor.execute(action)
        assert obs.success is False
        assert "Missing" in str(obs.error)

    async def test_skill_not_found(self):
        reg = SkillRegistry()
        executor = SkillExecutor(reg)
        obs = await executor.execute(_make_action("nonexistent"))
        assert obs.success is False
        assert "not found" in str(obs.error)

    async def test_skill_raises_exception(self):
        reg = SkillRegistry()
        reg.register(_make_record(), _ExplodingSkill())
        executor = SkillExecutor(reg)
        obs = await executor.execute(_make_action())
        assert obs.success is False
        assert "exploded" in str(obs.error)
        assert obs.latency_ms >= 0
