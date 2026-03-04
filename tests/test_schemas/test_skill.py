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


def _minimal(**overrides: object) -> SkillRecord:
    return SkillRecord(
        name=overrides.pop("name", "extract_entities"),  # type: ignore[arg-type]
        description="test",
        implementation_type=ImplementationType.ALGORITHMIC,
        implementation_path="p",
        test_suite_path="t",
        **overrides,  # type: ignore[arg-type]
    )


class TestSkillRecordDefaults:
    def test_minimal_construction(self) -> None:
        rec = _minimal()
        assert isinstance(rec.skill_id, ULID)
        assert rec.version == "0.1.0"
        assert rec.pass_rate == 1.0
        assert rec.invocation_count == 0
        assert rec.status == SkillStatus.ACTIVE
        assert rec.parent_skill_id is None
        assert rec.last_invoked is None
        assert rec.maturation_stage == MaturationStage.OBSERVED
        assert rec.shadow_agreement_rate is None
        assert rec.total_shadow_comparisons == 0


class TestSemverValidation:
    def test_valid_prerelease(self) -> None:
        assert _minimal(version="2.0.0-alpha.1").version == "2.0.0-alpha.1"

    def test_invalid_semver_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid semver"):
            _minimal(version="not_a_version")


class TestCrossFieldValidation:
    def test_active_with_low_pass_rate_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"pass_rate >= 0\.5"):
            _minimal(status=SkillStatus.ACTIVE, pass_rate=0.3)

    def test_degraded_with_low_pass_rate_allowed(self) -> None:
        rec = _minimal(status=SkillStatus.DEGRADED, pass_rate=0.2)
        assert rec.pass_rate == 0.2


class TestSkillOrjsonRoundTrip:
    def test_full_round_trip(self) -> None:
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
