"""Tests for core interface ABCs."""

from __future__ import annotations

import pytest

from evosys.core.interfaces import BaseSkill


class TestPartialImplFails:
    def test_partial_skill_missing_validate(self) -> None:
        class PartialSkill(BaseSkill):
            async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
                return {}

        with pytest.raises(TypeError, match="abstract"):
            PartialSkill()  # type: ignore[abstract]
