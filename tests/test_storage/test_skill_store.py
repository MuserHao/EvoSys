"""Tests for SkillStore — forged skill persistence."""

from __future__ import annotations

import pytest

from evosys.schemas._types import ImplementationType, MaturationStage, SkillStatus, new_ulid
from evosys.schemas.skill import SkillRecord
from evosys.storage.skill_store import PersistedSkill, SkillStore


@pytest.fixture()
async def skill_store(session_factory) -> SkillStore:
    return SkillStore(session_factory)


def _make_record(name: str = "extract:test.com", **overrides: object) -> SkillRecord:
    return SkillRecord(
        skill_id=new_ulid(),
        name=name,
        description="Auto-forged extraction skill for test.com",
        implementation_type=ImplementationType.ALGORITHMIC,
        implementation_path="forge:synthesized:test.com",
        test_suite_path="auto-generated",
        pass_rate=0.9,
        confidence_score=0.8,
        maturation_stage=MaturationStage.SYNTHESIZED,
        **overrides,  # type: ignore[arg-type]
    )


_SAMPLE_CODE = (
    "import re\n"
    "async def extract(input_data):\n"
    "    m = re.search(r'<h1>(.*?)</h1>', input_data.get('html', ''))\n"
    "    return {'title': m.group(1) if m else ''}\n"
)


class TestSkillStoreSaveAndLoad:
    async def test_save_and_load_all(self, skill_store: SkillStore) -> None:
        record = _make_record()
        await skill_store.save(record, _SAMPLE_CODE)
        loaded = await skill_store.load_all()
        assert len(loaded) == 1
        assert isinstance(loaded[0], PersistedSkill)
        assert loaded[0].record.name == "extract:test.com"
        assert loaded[0].source_code == _SAMPLE_CODE

    async def test_load_restores_full_record(self, skill_store: SkillStore) -> None:
        record = _make_record()
        await skill_store.save(record, _SAMPLE_CODE)
        loaded = await skill_store.load_all()
        r = loaded[0].record
        assert r.skill_id == record.skill_id
        assert r.pass_rate == 0.9
        assert r.confidence_score == 0.8
        assert r.maturation_stage == MaturationStage.SYNTHESIZED

    async def test_upsert_overwrites_existing(self, skill_store: SkillStore) -> None:
        record = _make_record()
        await skill_store.save(record, "# v1\nasync def extract(d): return {}")
        new_code = "# v2\nasync def extract(d): return {'updated': True}"
        await skill_store.save(record, new_code)
        loaded = await skill_store.load_all()
        assert len(loaded) == 1
        assert "v2" in loaded[0].source_code

    async def test_load_all_empty(self, skill_store: SkillStore) -> None:
        assert await skill_store.load_all() == []

    async def test_multiple_skills_ordered_by_created_at(
        self, skill_store: SkillStore
    ) -> None:
        for domain in ("alpha.com", "beta.com", "gamma.com"):
            await skill_store.save(_make_record(f"extract:{domain}"), _SAMPLE_CODE)
        loaded = await skill_store.load_all()
        names = [ps.record.name for ps in loaded]
        assert names == ["extract:alpha.com", "extract:beta.com", "extract:gamma.com"]


class TestSkillStoreUpdateStatus:
    async def test_update_status_to_degraded(self, skill_store: SkillStore) -> None:
        await skill_store.save(_make_record(), _SAMPLE_CODE)
        await skill_store.update_status("extract:test.com", SkillStatus.DEGRADED)
        loaded = await skill_store.load_all()
        assert loaded[0].record.status == SkillStatus.DEGRADED

    async def test_update_status_noop_if_missing(self, skill_store: SkillStore) -> None:
        await skill_store.update_status("extract:nonexistent.com", SkillStatus.DEGRADED)
        # must not raise

    async def test_update_status_preserves_other_fields(
        self, skill_store: SkillStore
    ) -> None:
        await skill_store.save(_make_record(), _SAMPLE_CODE)
        await skill_store.update_status("extract:test.com", SkillStatus.DEGRADED)
        loaded = await skill_store.load_all()
        r = loaded[0].record
        assert r.pass_rate == 0.9  # unchanged
        assert r.confidence_score == 0.8  # unchanged


class TestSkillStoreUpdateShadow:
    async def test_update_shadow_metrics(self, skill_store: SkillStore) -> None:
        await skill_store.save(_make_record(), _SAMPLE_CODE)
        await skill_store.update_shadow("extract:test.com", 0.95, 20)
        loaded = await skill_store.load_all()
        r = loaded[0].record
        assert r.shadow_agreement_rate == 0.95
        assert r.total_shadow_comparisons == 20

    async def test_update_shadow_noop_if_missing(self, skill_store: SkillStore) -> None:
        await skill_store.update_shadow("extract:nonexistent.com", 0.5, 5)
        # must not raise


class TestSkillStoreDelete:
    async def test_delete_removes_skill(self, skill_store: SkillStore) -> None:
        await skill_store.save(_make_record(), _SAMPLE_CODE)
        await skill_store.delete("extract:test.com")
        assert await skill_store.load_all() == []

    async def test_delete_noop_if_missing(self, skill_store: SkillStore) -> None:
        await skill_store.delete("extract:nonexistent.com")  # must not raise


class TestSkillStoreRecompile:
    """Tests that the stored source code can be recompiled into a working function."""

    async def test_loaded_code_compiles_and_runs(
        self, skill_store: SkillStore
    ) -> None:
        """End-to-end: save a skill, load it, recompile, invoke it."""
        from evosys.forge.forge import _compile_extract, _SynthesizedSkill

        code = (
            "import re\n"
            "async def extract(input_data):\n"
            "    m = re.search(r'<title>(.*?)</title>', input_data.get('html', ''))\n"
            "    return {'title': m.group(1) if m else ''}\n"
        )
        await skill_store.save(_make_record("extract:example.com"), code)
        loaded = await skill_store.load_all()
        assert len(loaded) == 1

        extract_fn = _compile_extract(loaded[0].source_code)
        assert extract_fn is not None

        skill = _SynthesizedSkill(extract_fn)
        result = await skill.invoke({"html": "<title>Hello World</title>", "url": ""})
        assert result["title"] == "Hello World"
