"""Tests for SkillForge."""

from __future__ import annotations

from unittest.mock import AsyncMock

from evosys.forge.forge import SkillForge, _is_safe_code
from evosys.forge.synthesizer import SkillSynthesizer
from evosys.schemas._types import new_ulid
from evosys.schemas.slice import SliceCandidate
from evosys.skills.registry import SkillRegistry


def _make_candidate() -> SliceCandidate:
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


class TestIsSafeCode:
    def test_safe_code(self):
        code = "import re\nasync def extract(d):\n    return {}"
        assert _is_safe_code(code) is True

    def test_rejects_os_import(self):
        assert _is_safe_code("import os") is False

    def test_rejects_subprocess(self):
        assert _is_safe_code("import subprocess") is False

    def test_rejects_eval_call(self):
        assert _is_safe_code("eval('1+1')") is False

    def test_rejects_open_call(self):
        assert _is_safe_code("open('file.txt')") is False

    def test_rejects_syntax_error(self):
        assert _is_safe_code("def (broken") is False

    def test_allows_html_parser(self):
        code = "from html.parser import HTMLParser"
        assert _is_safe_code(code) is True

    def test_allows_re(self):
        assert _is_safe_code("import re\nimport json") is True


class TestForge:
    async def test_no_domain_returns_none(self):
        synth = _mock_synthesizer("")
        reg = SkillRegistry()
        forge = SkillForge(synth, reg)
        result = await forge.forge(_make_candidate(), domain="")
        assert result is None

    async def test_already_registered_returns_none(self):
        from evosys.core.interfaces import BaseSkill
        from evosys.schemas._types import ImplementationType
        from evosys.schemas.skill import SkillRecord

        class Stub(BaseSkill):
            async def invoke(self, d: dict[str, object]) -> dict[str, object]:
                return {}

            def validate(self) -> bool:
                return True

        reg = SkillRegistry()
        rec = SkillRecord(
            name="extract:example.com",
            description="x",
            implementation_type=ImplementationType.DETERMINISTIC,
            implementation_path="x",
            test_suite_path="x",
        )
        reg.register(rec, Stub())

        synth = _mock_synthesizer("")
        forge = SkillForge(synth, reg)
        result = await forge.forge(_make_candidate(), domain="example.com")
        assert result is None

    async def test_unsafe_code_returns_none(self):
        synth = _mock_synthesizer("import os\nos.system('rm -rf /')")
        reg = SkillRegistry()
        forge = SkillForge(synth, reg)
        result = await forge.forge(_make_candidate(), domain="example.com")
        assert result is None

    async def test_successful_forge_no_io_pairs(self):
        code = "import re\nasync def extract(input_data):\n    return {'title': 'test'}"
        synth = _mock_synthesizer(code)
        reg = SkillRegistry()
        forge = SkillForge(synth, reg)
        result = await forge.forge(_make_candidate(), domain="example.com")
        assert result is not None
        assert result.name == "extract:example.com"
        assert "extract:example.com" in reg
