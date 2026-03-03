"""Tests for SkillRecord schema."""

from __future__ import annotations

import pytest
from ulid import ULID

from evosys.schemas import ImplementationType, SkillRecord, SkillStatus


class TestSkillRecordConstruction:
    def test_minimal_construction(self) -> None:
        rec = SkillRecord(
            name="extract_entities",
            description="Extract named entities from HTML",
            implementation_type=ImplementationType.PYTHON_FN,
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
            implementation_type=ImplementationType.PROMPT_CACHE,
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
            implementation_type=ImplementationType.PYTHON_FN,
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
                implementation_type=ImplementationType.PYTHON_FN,
                implementation_path="p",
                test_suite_path="t",
                version="not_a_version",
            )

    def test_semver_with_build_metadata(self) -> None:
        rec = SkillRecord(
            name="test",
            description="test",
            implementation_type=ImplementationType.PYTHON_FN,
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
            implementation_type="python_fn",  # type: ignore[arg-type]
            implementation_path="p",
            test_suite_path="t",
        )
        assert rec.implementation_type == ImplementationType.PYTHON_FN

    def test_status_from_string(self) -> None:
        rec = SkillRecord(
            name="test",
            description="test",
            implementation_type=ImplementationType.PYTHON_FN,
            implementation_path="p",
            test_suite_path="t",
            status="degraded",  # type: ignore[arg-type]
            pass_rate=0.3,
        )
        assert rec.status == SkillStatus.DEGRADED


class TestCrossFieldValidation:
    def test_active_with_low_pass_rate_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"pass_rate >= 0\.5"):
            SkillRecord(
                name="test",
                description="test",
                implementation_type=ImplementationType.PYTHON_FN,
                implementation_path="p",
                test_suite_path="t",
                status=SkillStatus.ACTIVE,
                pass_rate=0.3,
            )

    def test_degraded_with_low_pass_rate_allowed(self) -> None:
        rec = SkillRecord(
            name="test",
            description="test",
            implementation_type=ImplementationType.PYTHON_FN,
            implementation_path="p",
            test_suite_path="t",
            status=SkillStatus.DEGRADED,
            pass_rate=0.2,
        )
        assert rec.pass_rate == 0.2


class TestSkillOrjsonRoundTrip:
    def test_orjson_round_trip(self) -> None:
        rec = SkillRecord(
            name="extract",
            description="Extract stuff",
            implementation_type=ImplementationType.TINY_MODEL,
            implementation_path="models/extract.gguf",
            test_suite_path="tests/test_extract.py",
            pass_rate=0.92,
            confidence_score=0.85,
        )
        raw = rec.model_dump_orjson()
        restored = SkillRecord.model_validate_orjson(raw)
        assert restored.skill_id == rec.skill_id
        assert restored.implementation_type == ImplementationType.TINY_MODEL
        assert restored.pass_rate == 0.92
