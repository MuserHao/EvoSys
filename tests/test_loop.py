"""Tests for EvolutionLoop."""

from __future__ import annotations

from unittest.mock import AsyncMock

from ulid import ULID

from evosys.forge.forge import SkillForge
from evosys.loop import EvolutionLoop, EvolveCycleResult
from evosys.schemas._types import ImplementationType, new_ulid
from evosys.schemas.skill import SkillRecord
from evosys.schemas.trajectory import TrajectoryRecord
from evosys.skills.registry import SkillRegistry
from evosys.storage.trajectory_store import TrajectoryStore


def _make_trajectory(domain: str, trace_id: str | None = None) -> TrajectoryRecord:
    """Create a minimal TrajectoryRecord for testing."""
    return TrajectoryRecord(
        trace_id=ULID.from_str(trace_id) if trace_id else ULID(),
        session_id=ULID(),
        iteration_index=0,
        context_summary=f"Extract data from {domain}",
        action_name="llm_extract",
        action_params={"url": f"https://{domain}/page", "html": "<p>test</p>"},
        action_result={"title": "Test"},
        latency_ms=100.0,
        token_cost=500,
    )


def _mock_store(domains: dict[str, int]) -> TrajectoryStore:
    """Create a mock store that returns records grouped by domain."""
    store = AsyncMock(spec=TrajectoryStore)
    records_by_domain: dict[str, list[TrajectoryRecord]] = {}
    for domain, count in domains.items():
        records_by_domain[domain] = [_make_trajectory(domain) for _ in range(count)]
    store.get_llm_extractions_by_domain = AsyncMock(return_value=records_by_domain)
    return store


def _mock_forge(succeed: bool = True) -> SkillForge:
    """Create a mock forge that either succeeds or fails."""
    forge = AsyncMock(spec=SkillForge)
    if succeed:
        forge.forge = AsyncMock(
            side_effect=lambda candidate, domain="": SkillRecord(
                skill_id=new_ulid(),
                name=f"extract:{domain}",
                description=f"Forged for {domain}",
                implementation_type=ImplementationType.ALGORITHMIC,
                implementation_path=f"forge:synthesized:{domain}",
                test_suite_path="auto-generated",
                pass_rate=1.0,
                confidence_score=0.8,
            )
        )
    else:
        forge.forge = AsyncMock(return_value=None)
    return forge


class TestEvolveCycleResult:
    def test_fields(self):
        result = EvolveCycleResult(
            candidates_found=5,
            already_covered=2,
            forge_attempted=3,
            forge_succeeded=1,
        )
        assert result.candidates_found == 5
        assert result.new_skills == []

    def test_with_new_skills(self):
        skill = SkillRecord(
            name="extract:test.com",
            description="test",
            implementation_type=ImplementationType.ALGORITHMIC,
            implementation_path="x",
            test_suite_path="x",
        )
        result = EvolveCycleResult(
            candidates_found=1,
            already_covered=0,
            forge_attempted=1,
            forge_succeeded=1,
            new_skills=[skill],
        )
        assert len(result.new_skills) == 1


class TestEvolutionLoop:
    async def test_no_data_returns_empty(self):
        store = _mock_store({})
        forge = _mock_forge()
        registry = SkillRegistry()
        loop = EvolutionLoop(store, forge, registry)

        result = await loop.run_cycle()

        assert result.candidates_found == 0
        assert result.forge_attempted == 0

    async def test_below_min_frequency_returns_empty(self):
        store = _mock_store({"example.com": 2})  # Below default min_frequency=3
        forge = _mock_forge()
        registry = SkillRegistry()
        loop = EvolutionLoop(store, forge, registry)

        result = await loop.run_cycle()

        assert result.candidates_found == 0

    async def test_forge_succeeds(self):
        store = _mock_store({"example.com": 5})
        forge = _mock_forge(succeed=True)
        registry = SkillRegistry()
        loop = EvolutionLoop(store, forge, registry)

        result = await loop.run_cycle()

        assert result.candidates_found == 1
        assert result.forge_attempted == 1
        assert result.forge_succeeded == 1
        assert len(result.new_skills) == 1
        assert result.new_skills[0].name == "extract:example.com"

    async def test_forge_fails(self):
        store = _mock_store({"example.com": 5})
        forge = _mock_forge(succeed=False)
        registry = SkillRegistry()
        loop = EvolutionLoop(store, forge, registry)

        result = await loop.run_cycle()

        assert result.candidates_found == 1
        assert result.forge_attempted == 1
        assert result.forge_succeeded == 0
        assert len(result.new_skills) == 0

    async def test_already_covered_skipped(self):
        from evosys.core.interfaces import BaseSkill

        class Stub(BaseSkill):
            async def invoke(self, d: dict[str, object]) -> dict[str, object]:
                return {}

            def validate(self) -> bool:
                return True

        store = _mock_store({"example.com": 5})
        forge = _mock_forge()
        registry = SkillRegistry()

        # Pre-register the skill
        rec = SkillRecord(
            name="extract:example.com",
            description="existing",
            implementation_type=ImplementationType.DETERMINISTIC,
            implementation_path="x",
            test_suite_path="x",
        )
        registry.register(rec, Stub())

        loop = EvolutionLoop(store, forge, registry)
        result = await loop.run_cycle()

        assert result.candidates_found == 1
        assert result.already_covered == 1
        assert result.forge_attempted == 0

    async def test_multiple_domains(self):
        store = _mock_store({"a.com": 5, "b.com": 3, "c.com": 1})
        forge = _mock_forge(succeed=True)
        registry = SkillRegistry()
        loop = EvolutionLoop(store, forge, registry)

        result = await loop.run_cycle()

        # c.com has only 1 occurrence, below min_frequency=3
        assert result.candidates_found == 2
        assert result.forge_attempted == 2
        assert result.forge_succeeded == 2
        assert len(result.new_skills) == 2

    async def test_custom_min_frequency(self):
        store = _mock_store({"example.com": 2})
        forge = _mock_forge(succeed=True)
        registry = SkillRegistry()
        loop = EvolutionLoop(store, forge, registry, min_frequency=2)

        result = await loop.run_cycle()

        assert result.candidates_found == 1
        assert result.forge_succeeded == 1

    async def test_mixed_covered_and_uncovered(self):
        from evosys.core.interfaces import BaseSkill

        class Stub(BaseSkill):
            async def invoke(self, d: dict[str, object]) -> dict[str, object]:
                return {}

            def validate(self) -> bool:
                return True

        store = _mock_store({"covered.com": 5, "new.com": 4})
        forge = _mock_forge(succeed=True)
        registry = SkillRegistry()

        rec = SkillRecord(
            name="extract:covered.com",
            description="existing",
            implementation_type=ImplementationType.DETERMINISTIC,
            implementation_path="x",
            test_suite_path="x",
        )
        registry.register(rec, Stub())

        loop = EvolutionLoop(store, forge, registry)
        result = await loop.run_cycle()

        assert result.candidates_found == 2
        assert result.already_covered == 1
        assert result.forge_attempted == 1
        assert result.forge_succeeded == 1


class TestShadowEvaluation:
    async def test_shadow_evaluates_forged_skill(self):
        """When a forge succeeds and the skill is in the registry,
        shadow evaluation should run and update shadow metrics."""
        from evosys.core.interfaces import BaseSkill

        class EchoSkill(BaseSkill):
            async def invoke(self, d: dict[str, object]) -> dict[str, object]:
                return {"title": "Test"}

            def validate(self) -> bool:
                return True

        store = _mock_store({"example.com": 5})
        registry = SkillRegistry()

        # Create a forge mock that actually registers the skill
        forge = AsyncMock(spec=SkillForge)

        async def _forge_and_register(candidate, domain=""):
            rec = SkillRecord(
                skill_id=new_ulid(),
                name=f"extract:{domain}",
                description=f"Forged for {domain}",
                implementation_type=ImplementationType.ALGORITHMIC,
                implementation_path=f"forge:synthesized:{domain}",
                test_suite_path="auto-generated",
                pass_rate=1.0,
                confidence_score=0.8,
            )
            registry.register(rec, EchoSkill())
            return rec

        forge.forge = AsyncMock(side_effect=_forge_and_register)

        loop = EvolutionLoop(store, forge, registry)
        result = await loop.run_cycle()

        assert result.forge_succeeded == 1
        skill = result.new_skills[0]
        # Shadow eval should have run (sample_results from _mock_store
        # contain {"title": "Test"} which matches EchoSkill output)
        assert skill.shadow_agreement_rate is not None
        assert skill.total_shadow_comparisons > 0
