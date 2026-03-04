"""Skill synthesizer — generates Python extraction code from I/O examples."""

from __future__ import annotations

import re
import textwrap

from evosys.llm.client import LLMClient

_SYNTH_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a code synthesis assistant. Given input/output examples from a
    web extraction task, generate a Python async function that performs the
    same extraction using only the standard library (re, html.parser) and
    no external dependencies.

    The function MUST:
    - Be named `extract`
    - Accept a single argument `input_data: dict[str, object]` where
      input_data["html"] is the HTML string and input_data["url"] is the URL
    - Return a `dict[str, object]` matching the output examples
    - Use regex and string parsing, NOT BeautifulSoup or lxml
    - Be a standalone async function (no class)
    - Handle edge cases (missing data returns empty strings, 0, or [])

    Return ONLY the Python code, no markdown fences, no explanation.
""")


class SkillSynthesizer:
    """Generate Python extraction code from I/O examples using an LLM."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def synthesize(
        self,
        *,
        domain: str,
        sample_inputs: list[dict[str, object]],
        sample_outputs: list[dict[str, object]],
    ) -> str:
        """Generate Python code for extracting data from *domain*.

        Returns the raw Python source code as a string.
        """
        examples = self._format_examples(sample_inputs, sample_outputs)

        user_content = (
            f"Domain: {domain}\n\n"
            f"I/O Examples:\n{examples}\n\n"
            "Generate the `extract` function."
        )

        resp = await self._llm.complete(
            messages=[
                {"role": "system", "content": _SYNTH_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )

        return self._clean_code(resp.content)

    @staticmethod
    def _format_examples(
        inputs: list[dict[str, object]],
        outputs: list[dict[str, object]],
    ) -> str:
        """Format I/O pairs as a readable string for the LLM."""
        lines: list[str] = []
        for i, (inp, out) in enumerate(zip(inputs, outputs, strict=False)):
            lines.append(f"Example {i + 1}:")
            # Truncate HTML to keep prompt manageable
            inp_display = dict(inp)
            if "html" in inp_display and isinstance(inp_display["html"], str):
                html = str(inp_display["html"])
                if len(html) > 2000:
                    inp_display["html"] = html[:2000] + "... [truncated]"
            lines.append(f"  Input keys: {list(inp_display.keys())}")
            lines.append(f"  Output: {out}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _clean_code(raw: str) -> str:
        """Strip markdown fences and leading/trailing whitespace."""
        code = raw.strip()
        # Remove ```python ... ``` fences
        code = re.sub(r"^```(?:python)?\s*\n", "", code)
        code = re.sub(r"\n```\s*$", "", code)
        return code.strip()
