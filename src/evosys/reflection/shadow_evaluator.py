"""Shadow evaluator — compares skill output against LLM ground truth."""

from __future__ import annotations

from evosys.core.interfaces import BaseShadowEvaluator
from evosys.core.types import ShadowComparison


class ShadowEvaluator(BaseShadowEvaluator):
    """Compare a skill's output against the cloud LLM ground truth.

    Uses field-level exact match for agreement, and computes a
    similarity score based on the fraction of matching top-level keys.
    """

    async def compare(
        self,
        skill_output: dict[str, object],
        llm_output: dict[str, object],
        output_schema: dict[str, object],
    ) -> ShadowComparison:
        """Compare *skill_output* against *llm_output*."""
        if not llm_output:
            return ShadowComparison(
                skill_output=skill_output,
                llm_output=llm_output,
                agreement=True,
                similarity_score=1.0,
                notes="No LLM output to compare against.",
            )

        # Compute field-level agreement
        all_keys = set(skill_output.keys()) | set(llm_output.keys())
        if not all_keys:
            return ShadowComparison(
                skill_output=skill_output,
                llm_output=llm_output,
                agreement=True,
                similarity_score=1.0,
                notes="Both outputs empty.",
            )

        matching = 0
        mismatches: list[str] = []
        for key in all_keys:
            s_val = skill_output.get(key)
            l_val = llm_output.get(key)
            if _values_match(s_val, l_val):
                matching += 1
            else:
                mismatches.append(key)

        similarity = matching / len(all_keys)
        agreement = similarity >= 0.8

        notes = ""
        if mismatches:
            notes = f"Mismatched fields: {', '.join(sorted(mismatches))}"

        return ShadowComparison(
            skill_output=skill_output,
            llm_output=llm_output,
            agreement=agreement,
            similarity_score=round(similarity, 4),
            notes=notes,
        )


def _values_match(a: object, b: object) -> bool:
    """Check if two values match, with tolerance for type differences."""
    if a == b:
        return True
    # Compare string representations for numeric/string mismatches
    return str(a).strip().lower() == str(b).strip().lower()
