"""Tests for SkillRecord schema."""

from __future__ import annotations

import pytest
from ulid import ULID

from evosys.schemas import (
    ImplementationType,
    MaturationStage,
    SkillRecord,
    SkillStatus,
)


class TestSkillRecordConstruction:
    def test_minimal_construction(self) -> None:
        rec = SkillRecord(
            name="extract_entities",
            description="Extract named entities from HTML",
            implementation_type=ImplementationType.ALGORITHMIC,
            implementation_path="skills/extract_entities.py",
            test_suite_path="tests/skills/test_extract_entities.py",
        )
        assert isinstance(rec.skill_id, ULID)
        assert rec.version == "0.1.0"
        assert rec.pass_rate == 1.0
        assert rec.invocation_count == 0
        assert rec.status == SkillStatus.ACTIVE
        assert rec.parent_skill_id is None
        assert rec.last_invoked is None

    def test_full_construction(self, sample_ulid: ULID) -> None:
        rec = SkillRecord(
            name="parse_date",
            description="Parse dates from natural language",
            implementation_type=ImplementationType.CACHED_PROMPT,
            implementation_path="skills/parse_date.py",
            test_suite_path="tests/skills/test_parse_date.py",
            parent_skill_id=sample_ulid,
            version="1.2.3",
            pass_rate=0.95,
            confidence_score=0.88,
            invocation_count=42,
            created_from_traces=[sample_ulid],
        )
        assert rec.parent_skill_id == sample_ulid
        assert rec.version == "1.2.3"


class TestSemverValidation:
    def test_valid_semver(self) -> None:
        rec = SkillRecord(
            name="test",
            description="test",
            implementation_type=ImplementationType.DETERMINISTIC,
            implementation_path="p",
            test_suite_path="t",
            version="2.0.0-alpha.1",
        )
        assert rec.version == "2.0.0-alpha.1"

    def test_invalid_semver_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid semver"):
            SkillRecord(
                name="test",
                description="test",
                implementation_type=ImplementationType.DETERMINISTIC,
                implementation_path="p",
                test_suite_path="t",
                version="not_a_version",
            )

    def test_semver_with_build_metadata(self) -> None:
        rec = SkillRecord(
            name="test",
            description="test",
            implementation_type=ImplementationType.DETERMINISTIC,
            implementation_path="p",
            test_suite_path="t",
            version="1.0.0+build.123",
        )
        assert rec.version == "1.0.0+build.123"


class TestEnumCoercion:
    def test_implementation_type_from_string(self) -> None:
        rec = SkillRecord(
            name="test",
            description="test",
            implementation_type="deterministic",  # type: ignore[arg-type]
            implementation_path="p",
            test_suite_path="t",
        )
        assert rec.implementation_type == ImplementationType.DETERMINISTIC

    def test_status_from_string(self) -> None:
        rec = SkillRecord(
            name="test",
            description="test",
            implementation_type=ImplementationType.DETERMINISTIC,
            implementation_path="p",
            test_suite_path="t",
            status="degraded",  # type: ignore[arg-type]
            pass_rate=0.3,
        )
        assert rec.status == SkillStatus.DEGRADED

    def test_maturation_stage_from_string(self) -> None:
        rec = SkillRecord(
            name="test",
            description="test",
            implementation_type=ImplementationType.CACHED_PROMPT,
            implementation_path="p",
            test_suite_path="t",
            maturation_stage="prompted",  # type: ignore[arg-type]
        )
        assert rec.maturation_stage == MaturationStage.PROMPTED


class TestCrossFieldValidation:
    def test_active_with_low_pass_rate_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"pass_rate >= 0\.5"):
            SkillRecord(
                name="test",
                description="test",
                implementation_type=ImplementationType.DETERMINISTIC,
                implementation_path="p",
                test_suite_path="t",
                status=SkillStatus.ACTIVE,
                pass_rate=0.3,
            )

    def test_degraded_with_low_pass_rate_allowed(self) -> None:
        rec = SkillRecord(
            name="test",
            description="test",
            implementation_type=ImplementationType.DETERMINISTIC,
            implementation_path="p",
            test_suite_path="t",
            status=SkillStatus.DEGRADED,
            pass_rate=0.2,
        )
        assert rec.pass_rate == 0.2


class TestImplementationTierCoverage:
    """Verify all six tiers + composite can be used."""

    @pytest.mark.parametrize(
        "tier",
        [
            ImplementationType.DETERMINISTIC,
            ImplementationType.ALGORITHMIC,
            ImplementationType.CACHED_PROMPT,
            ImplementationType.FINE_TUNED_MODEL,
            ImplementationType.CLOUD_LLM,
            ImplementationType.AGENT_DELEGATION,
            ImplementationType.COMPOSITE,
        ],
    )
    def test_all_tiers_accepted(self, tier: ImplementationType) -> None:
        rec = SkillRecord(
            name="test",
            description="test",
            implementation_type=tier,
            implementation_path="p",
            test_suite_path="t",
        )
        assert rec.implementation_type == tier


class TestMaturationAndShadow:
    def test_maturation_defaults(self) -> None:
        rec = SkillRecord(
            name="test",
            description="test",
            implementation_type=ImplementationType.DETERMINISTIC,
            implementation_path="p",
            test_suite_path="t",
        )
        assert rec.maturation_stage == MaturationStage.OBSERVED
        assert rec.shadow_sample_rate == 1.0
        assert rec.shadow_agreement_rate is None
        assert rec.total_shadow_comparisons == 0
        assert rec.tier_demotion_attempts == 0
        assert rec.current_tier is None

    def test_maturation_with_shadow_tracking(self) -> None:
        rec = SkillRecord(
            name="entity_extractor",
            description="Extracts entities",
            implementation_type=ImplementationType.CACHED_PROMPT,
            implementation_path="skills/extract.py",
            test_suite_path="tests/test_extract.py",
            maturation_stage=MaturationStage.SYNTHESIZED,
            shadow_sample_rate=0.2,
            shadow_agreement_rate=0.94,
            total_shadow_comparisons=150,
            tier_demotion_attempts=1,
            current_tier=ImplementationType.ALGORITHMIC,
        )
        assert rec.maturation_stage == MaturationStage.SYNTHESIZED
        assert rec.shadow_sample_rate == 0.2
        assert rec.shadow_agreement_rate == 0.94
        assert rec.total_shadow_comparisons == 150
        assert rec.current_tier == ImplementationType.ALGORITHMIC

    def test_stable_skill_low_shadow_rate(self) -> None:
        rec = SkillRecord(
            name="date_parser",
            description="Parses dates",
            implementation_type=ImplementationType.DETERMINISTIC,
            implementation_path="skills/dates.py",
            test_suite_path="tests/test_dates.py",
            maturation_stage=MaturationStage.STABLE,
            shadow_sample_rate=0.01,
            shadow_agreement_rate=0.99,
            total_shadow_comparisons=5000,
        )
        assert rec.maturation_stage == MaturationStage.STABLE
        assert rec.shadow_sample_rate == 0.01

    @pytest.mark.parametrize(
        "stage",
        list(MaturationStage),
    )
    def test_all_maturation_stages(self, stage: MaturationStage) -> None:
        rec = SkillRecord(
            name="test",
            description="test",
            implementation_type=ImplementationType.DETERMINISTIC,
            implementation_path="p",
            test_suite_path="t",
            maturation_stage=stage,
        )
        assert rec.maturation_stage == stage


class TestSkillOrjsonRoundTrip:
    def test_orjson_round_trip(self) -> None:
        rec = SkillRecord(
            name="extract",
            description="Extract stuff",
            implementation_type=ImplementationType.FINE_TUNED_MODEL,
            implementation_path="models/extract.gguf",
            test_suite_path="tests/test_extract.py",
            pass_rate=0.92,
            confidence_score=0.85,
            maturation_stage=MaturationStage.SYNTHESIZED,
            shadow_sample_rate=0.15,
            shadow_agreement_rate=0.91,
            total_shadow_comparisons=200,
        )
        raw = rec.model_dump_orjson()
        restored = SkillRecord.model_validate_orjson(raw)
        assert restored.skill_id == rec.skill_id
        assert restored.implementation_type == ImplementationType.FINE_TUNED_MODEL
        assert restored.pass_rate == 0.92
        assert restored.maturation_stage == MaturationStage.SYNTHESIZED
        assert restored.shadow_agreement_rate == 0.91
