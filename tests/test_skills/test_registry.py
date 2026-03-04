"""Tests for SkillRegistry."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from evosys.core.interfaces import BaseSkill
from evosys.schemas._types import ImplementationType, SkillStatus
from evosys.schemas.skill import SkillRecord
from evosys.skills.registry import SkillRegistry


class _StubSkill(BaseSkill):
    """A trivial skill that returns its input unchanged."""

    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        return input_data

    def validate(self) -> bool:
        return True


class _InvalidSkill(BaseSkill):
    """A skill whose validate() always returns False."""

    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        return {}

    def validate(self) -> bool:
        return False


def _make_record(
    name: str = "extract:example.com",
    status: SkillStatus = SkillStatus.ACTIVE,
    confidence: float = 0.9,
) -> SkillRecord:
    return SkillRecord(
        name=name,
        description="Stub skill for testing",
        implementation_type=ImplementationType.DETERMINISTIC,
        implementation_path="skills/stub.py",
        test_suite_path="tests/test_stub.py",
        status=status,
        confidence_score=confidence,
    )


class TestRegister:
    def test_register_and_lookup(self):
        reg = SkillRegistry()
        record = _make_record()
        skill = _StubSkill()
        reg.register(record, skill)

        entry = reg.lookup("extract:example.com")
        assert entry is not None
        assert entry.record.name == "extract:example.com"
        assert entry.implementation is skill

    def test_duplicate_name_rejected(self):
        reg = SkillRegistry()
        reg.register(_make_record(), _StubSkill())
        with pytest.raises(ValueError, match="already registered"):
            reg.register(_make_record(), _StubSkill())

    def test_invalid_skill_rejected(self):
        reg = SkillRegistry()
        with pytest.raises(ValueError, match="failed its validate"):
            reg.register(_make_record(), _InvalidSkill())

    def test_lookup_missing_returns_none(self):
        reg = SkillRegistry()
        assert reg.lookup("nonexistent") is None


class TestUnregister:
    def test_returns_record(self):
        reg = SkillRegistry()
        record = _make_record()
        reg.register(record, _StubSkill())
        returned = reg.unregister("extract:example.com")
        assert returned.name == record.name
        assert reg.lookup("extract:example.com") is None

    def test_missing_raises_key_error(self):
        reg = SkillRegistry()
        with pytest.raises(KeyError):
            reg.unregister("nonexistent")


class TestLookupActive:
    def test_active_above_confidence(self):
        reg = SkillRegistry()
        reg.register(_make_record(confidence=0.9), _StubSkill())
        entry = reg.lookup_active("extract:example.com", min_confidence=0.7)
        assert entry is not None

    def test_below_confidence_returns_none(self):
        reg = SkillRegistry()
        reg.register(_make_record(confidence=0.5), _StubSkill())
        assert reg.lookup_active("extract:example.com", min_confidence=0.7) is None

    def test_degraded_returns_none(self):
        reg = SkillRegistry()
        reg.register(
            _make_record(status=SkillStatus.DEGRADED, confidence=0.9),
            _StubSkill(),
        )
        assert reg.lookup_active("extract:example.com") is None

    def test_deprecated_returns_none(self):
        reg = SkillRegistry()
        reg.register(
            _make_record(status=SkillStatus.DEPRECATED, confidence=0.9),
            _StubSkill(),
        )
        assert reg.lookup_active("extract:example.com") is None

    def test_missing_returns_none(self):
        reg = SkillRegistry()
        assert reg.lookup_active("nonexistent") is None


class TestListMethods:
    def test_list_all(self):
        reg = SkillRegistry()
        reg.register(_make_record("a"), _StubSkill())
        reg.register(
            _make_record("b", status=SkillStatus.DEGRADED, confidence=0.9),
            _StubSkill(),
        )
        assert len(reg.list_all()) == 2

    def test_list_active_filters(self):
        reg = SkillRegistry()
        reg.register(_make_record("a"), _StubSkill())
        reg.register(
            _make_record("b", status=SkillStatus.DEGRADED, confidence=0.9),
            _StubSkill(),
        )
        active = reg.list_active()
        assert len(active) == 1
        assert active[0].record.name == "a"


class TestRecordInvocation:
    def test_increments_count(self):
        reg = SkillRegistry()
        reg.register(_make_record(), _StubSkill())
        reg.record_invocation("extract:example.com")
        entry = reg.lookup("extract:example.com")
        assert entry is not None
        assert entry.invocation_count == 1

    def test_sets_last_invoked(self):
        reg = SkillRegistry()
        reg.register(_make_record(), _StubSkill())
        ts = datetime(2025, 1, 1, tzinfo=UTC)
        reg.record_invocation("extract:example.com", timestamp=ts)
        entry = reg.lookup("extract:example.com")
        assert entry is not None
        assert entry.last_invoked == ts

    def test_increments_multiple_times(self):
        reg = SkillRegistry()
        reg.register(_make_record(), _StubSkill())
        reg.record_invocation("extract:example.com")
        reg.record_invocation("extract:example.com")
        reg.record_invocation("extract:example.com")
        entry = reg.lookup("extract:example.com")
        assert entry is not None
        assert entry.invocation_count == 3

    def test_noop_if_missing(self):
        reg = SkillRegistry()
        reg.record_invocation("nonexistent")  # should not raise

    def test_record_identity_unchanged(self):
        """Invoking the skill must not replace the SkillRecord object.

        Callers that hold a reference to entry.record before the invocation
        should still see a valid record (the object identity is preserved).
        """
        reg = SkillRegistry()
        reg.register(_make_record(), _StubSkill())
        entry = reg.lookup("extract:example.com")
        assert entry is not None
        record_before = entry.record

        reg.record_invocation("extract:example.com")

        # The record object itself must not have been replaced
        assert entry.record is record_before
        # But the counter on the entry is updated
        assert entry.invocation_count == 1


class TestDunderMethods:
    def test_len(self):
        reg = SkillRegistry()
        assert len(reg) == 0
        reg.register(_make_record(), _StubSkill())
        assert len(reg) == 1

    def test_contains(self):
        reg = SkillRegistry()
        reg.register(_make_record(), _StubSkill())
        assert "extract:example.com" in reg
        assert "nonexistent" not in reg
