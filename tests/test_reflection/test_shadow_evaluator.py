"""Tests for ShadowEvaluator."""

from __future__ import annotations

from evosys.reflection.shadow_evaluator import ShadowEvaluator


class TestAgreement:
    async def test_identical_outputs(self):
        evaluator = ShadowEvaluator()
        result = await evaluator.compare(
            skill_output={"title": "Hello", "score": 42},
            llm_output={"title": "Hello", "score": 42},
            output_schema={},
        )
        assert result.agreement is True
        assert result.similarity_score == 1.0

    async def test_partial_match_above_threshold(self):
        evaluator = ShadowEvaluator()
        result = await evaluator.compare(
            skill_output={"a": 1, "b": 2, "c": 3, "d": 4, "e": 5},
            llm_output={"a": 1, "b": 2, "c": 3, "d": 4, "e": 99},
            output_schema={},
        )
        assert result.agreement is True
        assert result.similarity_score == 0.8

    async def test_disagreement_below_threshold(self):
        evaluator = ShadowEvaluator()
        result = await evaluator.compare(
            skill_output={"a": 1, "b": 2},
            llm_output={"a": 1, "b": 99},
            output_schema={},
        )
        assert result.agreement is False
        assert result.similarity_score == 0.5

    async def test_empty_llm_output(self):
        evaluator = ShadowEvaluator()
        result = await evaluator.compare(
            skill_output={"a": 1},
            llm_output={},
            output_schema={},
        )
        assert result.agreement is True
        assert result.similarity_score == 1.0


class TestMismatchNotes:
    async def test_lists_mismatched_fields(self):
        evaluator = ShadowEvaluator()
        result = await evaluator.compare(
            skill_output={"title": "A", "score": 1},
            llm_output={"title": "A", "score": 999},
            output_schema={},
        )
        assert "score" in result.notes

    async def test_no_notes_on_match(self):
        evaluator = ShadowEvaluator()
        result = await evaluator.compare(
            skill_output={"x": 1},
            llm_output={"x": 1},
            output_schema={},
        )
        assert result.notes == ""


class TestTypeTolerance:
    async def test_string_vs_int_match(self):
        evaluator = ShadowEvaluator()
        result = await evaluator.compare(
            skill_output={"count": "42"},
            llm_output={"count": 42},
            output_schema={},
        )
        assert result.agreement is True

    async def test_case_insensitive_string_match(self):
        evaluator = ShadowEvaluator()
        result = await evaluator.compare(
            skill_output={"status": "Active"},
            llm_output={"status": "active"},
            output_schema={},
        )
        assert result.agreement is True
