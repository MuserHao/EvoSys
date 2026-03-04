"""Tests for RoutingOrchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock

from evosys.core.interfaces import BaseOrchestrator, BaseSkill
from evosys.core.types import Action, ActionPlan
from evosys.orchestration.routing_orchestrator import RoutingOrchestrator
from evosys.schemas._types import ImplementationType, SkillStatus
from evosys.schemas.skill import SkillRecord
from evosys.skills.registry import SkillRegistry


class _StubSkill(BaseSkill):
    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        return input_data

    def validate(self) -> bool:
        return True


def _make_record(
    name: str = "extract:example.com",
    status: SkillStatus = SkillStatus.ACTIVE,
    confidence: float = 0.9,
) -> SkillRecord:
    return SkillRecord(
        name=name,
        description="Stub",
        implementation_type=ImplementationType.DETERMINISTIC,
        implementation_path="skills/stub.py",
        test_suite_path="tests/test_stub.py",
        status=status,
        confidence_score=confidence,
    )


def _make_fallback_plan(task: str = "fallback") -> ActionPlan:
    return ActionPlan(
        task_description=task,
        actions=[Action(name="fetch_url"), Action(name="llm_extract")],
        reasoning="Fallback plan.",
    )


class TestSkillRouting:
    async def test_routes_to_matching_skill(self):
        reg = SkillRegistry()
        reg.register(_make_record(), _StubSkill())
        orch = RoutingOrchestrator(reg)
        plan = await orch.plan("Extract from https://example.com/page")
        assert len(plan.actions) == 1
        assert plan.actions[0].name == "invoke_skill"
        assert plan.actions[0].params["skill_name"] == "extract:example.com"
        assert plan.actions[0].params["url"] == "https://example.com/page"

    async def test_strips_www_prefix(self):
        reg = SkillRegistry()
        reg.register(_make_record("extract:example.com"), _StubSkill())
        orch = RoutingOrchestrator(reg)
        plan = await orch.plan("Extract from https://www.example.com/page")
        assert plan.actions[0].name == "invoke_skill"
        assert plan.actions[0].params["skill_name"] == "extract:example.com"

    async def test_reasoning_mentions_skill_name(self):
        reg = SkillRegistry()
        reg.register(_make_record(), _StubSkill())
        orch = RoutingOrchestrator(reg)
        plan = await orch.plan("Extract from https://example.com/page")
        assert "extract:example.com" in plan.reasoning


class TestFallback:
    async def test_falls_back_when_no_skill(self):
        reg = SkillRegistry()
        fallback = AsyncMock(spec=BaseOrchestrator)
        fallback.plan = AsyncMock(return_value=_make_fallback_plan())
        orch = RoutingOrchestrator(reg, fallback=fallback)
        plan = await orch.plan("Extract from https://unknown.com/page")
        assert plan.actions[0].name == "fetch_url"
        fallback.plan.assert_awaited_once()

    async def test_falls_back_below_confidence(self):
        reg = SkillRegistry()
        reg.register(_make_record(confidence=0.5), _StubSkill())
        fallback = AsyncMock(spec=BaseOrchestrator)
        fallback.plan = AsyncMock(return_value=_make_fallback_plan())
        orch = RoutingOrchestrator(reg, fallback=fallback, confidence_threshold=0.7)
        plan = await orch.plan("Extract from https://example.com/page")
        assert plan.actions[0].name == "fetch_url"

    async def test_falls_back_when_degraded(self):
        reg = SkillRegistry()
        reg.register(
            _make_record(status=SkillStatus.DEGRADED, confidence=0.9),
            _StubSkill(),
        )
        fallback = AsyncMock(spec=BaseOrchestrator)
        fallback.plan = AsyncMock(return_value=_make_fallback_plan())
        orch = RoutingOrchestrator(reg, fallback=fallback)
        plan = await orch.plan("Extract from https://example.com/page")
        assert plan.actions[0].name == "fetch_url"

    async def test_falls_back_when_no_url(self):
        reg = SkillRegistry()
        reg.register(_make_record(), _StubSkill())
        fallback = AsyncMock(spec=BaseOrchestrator)
        fallback.plan = AsyncMock(return_value=_make_fallback_plan())
        orch = RoutingOrchestrator(reg, fallback=fallback)
        await orch.plan("Extract data from the database")
        fallback.plan.assert_awaited_once()

    async def test_custom_threshold(self):
        reg = SkillRegistry()
        reg.register(_make_record(confidence=0.6), _StubSkill())
        orch = RoutingOrchestrator(reg, confidence_threshold=0.5)
        plan = await orch.plan("Extract from https://example.com/page")
        assert plan.actions[0].name == "invoke_skill"


class TestUrlExtraction:
    def test_extract_url_basic(self):
        assert (
            RoutingOrchestrator._extract_url("Get https://foo.com/bar")
            == "https://foo.com/bar"
        )

    def test_extract_url_none(self):
        assert RoutingOrchestrator._extract_url("no url here") is None

    def test_extract_url_http(self):
        url = RoutingOrchestrator._extract_url("Fetch http://example.com")
        assert url == "http://example.com"


class TestDomainExtraction:
    def test_basic_domain(self):
        assert RoutingOrchestrator._extract_domain("https://example.com/page") == "example.com"

    def test_strips_www(self):
        assert RoutingOrchestrator._extract_domain("https://www.example.com/page") == "example.com"

    def test_with_port(self):
        assert RoutingOrchestrator._extract_domain("https://example.com:8080/page") == "example.com"

    def test_invalid_url(self):
        assert RoutingOrchestrator._extract_domain("not-a-url") is None

    # New tests enabled by urllib.parse
    def test_ip_address(self):
        assert RoutingOrchestrator._extract_domain("http://192.168.1.1/data") == "192.168.1.1"

    def test_localhost(self):
        assert RoutingOrchestrator._extract_domain("http://localhost:8000/api") == "localhost"

    def test_subdomain_preserved(self):
        result = RoutingOrchestrator._extract_domain("https://api.example.com/v1")
        assert result == "api.example.com"

    def test_no_path(self):
        assert RoutingOrchestrator._extract_domain("https://example.com") == "example.com"
