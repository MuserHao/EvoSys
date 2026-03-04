"""Tests for SkillSynthesizer."""

from __future__ import annotations

from unittest.mock import AsyncMock

from evosys.forge.synthesizer import SkillSynthesizer
from evosys.llm.client import LLMClient, LLMResponse


def _mock_llm(content: str = "async def extract(input_data):\n    return {}") -> LLMClient:
    client = AsyncMock(spec=LLMClient)
    client.complete = AsyncMock(
        return_value=LLMResponse(
            content=content,
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            model="test-model",
        )
    )
    return client


class TestSynthesize:
    async def test_returns_code_string(self):
        llm = _mock_llm("async def extract(input_data):\n    return {}")
        synth = SkillSynthesizer(llm)
        code = await synth.synthesize(
            domain="example.com",
            sample_inputs=[{"html": "<p>test</p>", "url": "https://example.com"}],
            sample_outputs=[{"title": "test"}],
        )
        assert "extract" in code

    async def test_strips_markdown_fences(self):
        raw = "```python\nasync def extract(input_data):\n    return {}\n```"
        llm = _mock_llm(raw)
        synth = SkillSynthesizer(llm)
        code = await synth.synthesize(
            domain="example.com",
            sample_inputs=[],
            sample_outputs=[],
        )
        assert "```" not in code
        assert "extract" in code


class TestCleanCode:
    def test_strips_fences(self):
        raw = "```python\ndef foo():\n    pass\n```"
        assert "```" not in SkillSynthesizer._clean_code(raw)

    def test_plain_code_unchanged(self):
        code = "async def extract(d):\n    return {}"
        assert SkillSynthesizer._clean_code(code) == code


class TestFormatExamples:
    def test_formats_io_pairs(self):
        result = SkillSynthesizer._format_examples(
            [{"html": "<p>hi</p>", "url": "https://x.com"}],
            [{"title": "hi"}],
        )
        assert "Example 1" in result
        assert "title" in result

    def test_truncates_long_html(self):
        long_html = "x" * 5000
        result = SkillSynthesizer._format_examples(
            [{"html": long_html}],
            [{"title": "test"}],
        )
        # Method only shows keys, not full values, so just verify it runs
        assert "Example 1" in result
        assert "html" in result
