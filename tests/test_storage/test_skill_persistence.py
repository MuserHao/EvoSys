"""Integration test: forged skill survives a simulated restart.

Tests the full persistence loop:
  forge → save to DB → reload from DB → recompile → re-register → route
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from evosys.bootstrap import _reload_forged_skills
from evosys.forge.forge import SkillForge
from evosys.forge.synthesizer import SkillSynthesizer
from evosys.schemas._types import ImplementationType, new_ulid
from evosys.schemas.slice import SliceCandidate
from evosys.skills.registry import SkillRegistry
from evosys.storage.skill_store import SkillStore


@pytest.fixture()
async def skill_store(session_factory) -> SkillStore:
    return SkillStore(session_factory)


def _make_candidate(domain: str = "example.com") -> SliceCandidate:
    tid = new_ulid()
    return SliceCandidate(
        action_sequence=["llm_extract"],
        frequency=5,
        occurrence_trace_ids=[tid] * 5,
        boundary_confidence=0.8,
    )


def _mock_synthesizer(code: str) -> SkillSynthesizer:
    synth = AsyncMock(spec=SkillSynthesizer)
    synth.synthesize = AsyncMock(return_value=code)
    return synth


_WORKING_CODE = (
    "import re\n"
    "async def extract(input_data):\n"
    "    m = re.search(r'<h1>(.*?)</h1>', input_data.get('html', ''))\n"
    "    return {'title': m.group(1).lower() if m else ''}\n"
)


class TestForgePersistsSkill:
    async def test_forge_saves_to_db(self, skill_store: SkillStore) -> None:
        """After a successful forge, the skill appears in the DB."""
        registry = SkillRegistry()
        forge = SkillForge(
            _mock_synthesizer(_WORKING_CODE), registry, skill_store=skill_store
        )
        record = await forge.forge(_make_candidate(), domain="example.com")

        assert record is not None
        saved = await skill_store.load_all()
        assert len(saved) == 1
        assert saved[0].record.name == "extract:example.com"
        assert saved[0].source_code == _WORKING_CODE

    async def test_forge_without_store_still_registers(self) -> None:
        """skill_store=None is backward-compatible — skill registers in memory only."""
        registry = SkillRegistry()
        forge = SkillForge(
            _mock_synthesizer(_WORKING_CODE), registry, skill_store=None
        )
        record = await forge.forge(_make_candidate(), domain="example.com")
        assert record is not None
        assert "extract:example.com" in registry


class TestReloadForgedSkills:
    async def test_reload_restores_skill_in_registry(
        self, skill_store: SkillStore
    ) -> None:
        """Skills saved to DB are reloaded into a fresh registry."""
        # Step 1: forge and persist
        registry1 = SkillRegistry()
        forge = SkillForge(
            _mock_synthesizer(_WORKING_CODE), registry1, skill_store=skill_store
        )
        await forge.forge(_make_candidate("reload.com"), domain="reload.com")
        assert "extract:reload.com" in registry1

        # Step 2: simulate restart — fresh registry, reload from DB
        registry2 = SkillRegistry()
        reloaded = await _reload_forged_skills(skill_store, registry2)

        assert reloaded == 1
        assert "extract:reload.com" in registry2

    async def test_reloaded_skill_actually_works(
        self, skill_store: SkillStore
    ) -> None:
        """Reloaded skill can be invoked and returns correct output."""
        registry1 = SkillRegistry()
        forge = SkillForge(
            _mock_synthesizer(_WORKING_CODE), registry1, skill_store=skill_store
        )
        await forge.forge(_make_candidate("works.com"), domain="works.com")

        registry2 = SkillRegistry()
        await _reload_forged_skills(skill_store, registry2)

        entry = registry2.lookup("extract:works.com")
        assert entry is not None

        result = await entry.implementation.invoke(
            {"html": "<h1>Hello World</h1>", "url": "https://works.com"}
        )
        assert result["title"] == "hello world"

    async def test_builtin_takes_precedence_over_db(
        self, skill_store: SkillStore
    ) -> None:
        """If a builtin skill name collides with a DB entry, the builtin wins."""
        from evosys.core.interfaces import BaseSkill
        from evosys.schemas.skill import SkillRecord

        class BuiltinSkill(BaseSkill):
            async def invoke(self, d: dict[str, object]) -> dict[str, object]:
                return {"source": "builtin"}

            def validate(self) -> bool:
                return True

        # Save a forged skill with same name as a builtin
        from evosys.schemas._types import MaturationStage
        rec = SkillRecord(
            name="extract:example.com",
            description="Forged version",
            implementation_type=ImplementationType.ALGORITHMIC,
            implementation_path="forge:synthesized:example.com",
            test_suite_path="auto-generated",
            pass_rate=0.9,
            maturation_stage=MaturationStage.SYNTHESIZED,
        )
        await skill_store.save(rec, _WORKING_CODE)

        # Builtin registered first
        registry = SkillRegistry()
        registry.register(
            SkillRecord(
                name="extract:example.com",
                description="Builtin version",
                implementation_type=ImplementationType.DETERMINISTIC,
                implementation_path="builtins",
                test_suite_path="tests",
            ),
            BuiltinSkill(),
        )

        reloaded = await _reload_forged_skills(skill_store, registry)
        assert reloaded == 0  # skipped — builtin already registered

        # Builtin still in control
        entry = registry.lookup("extract:example.com")
        assert entry is not None
        result = await entry.implementation.invoke({})
        assert result["source"] == "builtin"

    async def test_reload_skips_corrupted_code(
        self, skill_store: SkillStore
    ) -> None:
        """Rows with code that fails to compile are skipped gracefully."""
        from evosys.schemas._types import MaturationStage
        from evosys.schemas.skill import SkillRecord

        rec = SkillRecord(
            name="extract:broken.com",
            description="Broken skill",
            implementation_type=ImplementationType.ALGORITHMIC,
            implementation_path="forge:synthesized:broken.com",
            test_suite_path="auto-generated",
            pass_rate=0.9,
            maturation_stage=MaturationStage.SYNTHESIZED,
        )
        await skill_store.save(rec, "def broken(: syntax error")

        registry = SkillRegistry()
        reloaded = await _reload_forged_skills(skill_store, registry)
        assert reloaded == 0
        assert "extract:broken.com" not in registry
