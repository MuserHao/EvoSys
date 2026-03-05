"""Tests for skill re-forger."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from evosys.forge.reforger import SkillReforger
from evosys.schemas._types import SkillStatus


class TestSkillReforger:
    def _make_degraded_entry(self, name: str = "extract:example.com"):
        """Create a mock degraded skill registry entry."""
        record = MagicMock()
        record.name = name
        record.status = SkillStatus.DEGRADED
        record.description = "test skill"
        record.confidence_score = 0.5
        record.input_schema = {}
        record.output_schema = {}

        entry = MagicMock()
        entry.record = record
        entry.implementation = MagicMock()
        return entry

    async def test_no_degraded_skills(self) -> None:
        store = AsyncMock()
        forge = AsyncMock()
        registry = MagicMock()
        registry.list_all.return_value = []

        reforger = SkillReforger(store, forge, registry)
        count = await reforger.reforge_degraded()
        assert count == 0

    async def test_insufficient_samples(self) -> None:
        store = AsyncMock()
        store.get_llm_extractions_by_domain.return_value = {"example.com": []}

        forge = AsyncMock()
        registry = MagicMock()
        entry = self._make_degraded_entry()
        registry.list_all.return_value = [entry]

        reforger = SkillReforger(store, forge, registry, min_samples=5)
        count = await reforger.reforge_degraded()
        assert count == 0

    async def test_handles_exception_gracefully(self) -> None:
        store = AsyncMock()
        store.get_llm_extractions_by_domain.side_effect = RuntimeError("db error")

        forge = AsyncMock()
        registry = MagicMock()
        entry = self._make_degraded_entry()
        registry.list_all.return_value = [entry]

        reforger = SkillReforger(store, forge, registry)
        # Should not raise
        count = await reforger.reforge_degraded()
        assert count == 0
