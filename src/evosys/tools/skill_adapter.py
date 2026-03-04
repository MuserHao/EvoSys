"""Adapter that wraps a SkillEntry as a Tool."""

from __future__ import annotations

from evosys.skills.registry import SkillEntry


class SkillToolAdapter:
    """Wraps a :class:`SkillEntry` so it satisfies the :class:`Tool` protocol."""

    def __init__(self, entry: SkillEntry) -> None:
        self._entry = entry

    @property
    def name(self) -> str:
        return self._entry.record.name

    @property
    def description(self) -> str:
        return self._entry.record.description

    @property
    def parameters_schema(self) -> dict[str, object]:
        return dict(self._entry.record.input_schema)

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        return await self._entry.implementation.invoke(dict(kwargs))

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters_schema,
                },
            },
        }
