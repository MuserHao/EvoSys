"""Unified tool registry — composes SkillRegistry with external tools."""

from __future__ import annotations

from evosys.core.tool import Tool
from evosys.skills.registry import SkillRegistry
from evosys.tools.skill_adapter import SkillToolAdapter


class ToolRegistry:
    """Combines skills (via adapter) and external tools under one interface.

    Does **not** replace :class:`SkillRegistry` — it wraps it.
    Active skills with sufficient confidence are automatically exposed.
    """

    def __init__(
        self,
        skill_registry: SkillRegistry,
        *,
        min_confidence: float = 0.0,
    ) -> None:
        self._skill_registry = skill_registry
        self._min_confidence = min_confidence
        self._external: dict[str, Tool] = {}

    @property
    def skill_registry(self) -> SkillRegistry:
        return self._skill_registry

    def register_external(self, tool: Tool) -> None:
        """Register an external tool (e.g. from MCP or custom code)."""
        self._external[tool.name] = tool

    def unregister_external(self, name: str) -> None:
        """Remove an external tool by name."""
        self._external.pop(name, None)

    def get_tool(self, name: str) -> Tool | None:
        """Look up a tool by name (external first, then skills)."""
        if name in self._external:
            return self._external[name]
        entry = self._skill_registry.lookup_active(
            name, min_confidence=self._min_confidence
        )
        if entry is not None:
            return SkillToolAdapter(entry)
        return None

    def list_tools(self) -> list[Tool]:
        """Return all available tools (external + adapted skills)."""
        tools: list[Tool] = list(self._external.values())
        for entry in self._skill_registry.list_active():
            if entry.record.confidence_score >= self._min_confidence:
                tools.append(SkillToolAdapter(entry))
        return tools

    def get_openai_tools(self) -> list[dict[str, object]]:
        """Return all tools in OpenAI function-calling format."""
        return [t.to_openai_tool() for t in self.list_tools()]
