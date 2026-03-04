"""Tests for ToolRegistry."""


from evosys.core.interfaces import BaseSkill
from evosys.schemas._types import ImplementationType, SkillStatus
from evosys.schemas.skill import SkillRecord
from evosys.skills.registry import SkillRegistry
from evosys.tools.registry import ToolRegistry


class _StubSkill(BaseSkill):
    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        return {"out": True}

    def validate(self) -> bool:
        return True


class _FakeExternalTool:
    """Satisfies the Tool protocol."""

    def __init__(self, name: str = "external_tool", desc: str = "ext") -> None:
        self._name = name
        self._desc = desc

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._desc

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {"input": {"type": "string"}}

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        return {"external": True}

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": self._desc,
                "parameters": {"type": "object", "properties": self.parameters_schema},
            },
        }


def _register_skill(
    registry: SkillRegistry,
    name: str = "extract:example.com",
    confidence: float = 1.0,
    status: SkillStatus = SkillStatus.ACTIVE,
) -> None:
    record = SkillRecord(
        name=name,
        description=f"Skill for {name}",
        implementation_type=ImplementationType.DETERMINISTIC,
        implementation_path="test",
        test_suite_path="test",
        confidence_score=confidence,
        status=status,
    )
    registry.register(record, _StubSkill())


class TestToolRegistry:
    def test_empty_registry(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        assert tr.list_tools() == []
        assert tr.get_openai_tools() == []

    def test_skill_registry_property(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        assert tr.skill_registry is sr

    def test_skills_exposed_as_tools(self) -> None:
        sr = SkillRegistry()
        _register_skill(sr, "extract:a.com")
        _register_skill(sr, "extract:b.com")
        tr = ToolRegistry(sr)
        tools = tr.list_tools()
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert names == {"extract:a.com", "extract:b.com"}

    def test_inactive_skills_not_exposed(self) -> None:
        sr = SkillRegistry()
        _register_skill(sr, "extract:a.com", status=SkillStatus.DEPRECATED)
        tr = ToolRegistry(sr)
        assert tr.list_tools() == []

    def test_low_confidence_skills_filtered(self) -> None:
        sr = SkillRegistry()
        _register_skill(sr, "extract:a.com", confidence=0.3)
        tr = ToolRegistry(sr, min_confidence=0.5)
        assert tr.list_tools() == []

    def test_register_external_tool(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        ext = _FakeExternalTool("my_tool")
        tr.register_external(ext)
        tools = tr.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "my_tool"

    def test_unregister_external_tool(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        ext = _FakeExternalTool("my_tool")
        tr.register_external(ext)
        tr.unregister_external("my_tool")
        assert tr.list_tools() == []

    def test_unregister_nonexistent_tool(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        tr.unregister_external("nope")  # should not raise

    def test_get_tool_external(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        ext = _FakeExternalTool("ext")
        tr.register_external(ext)
        tool = tr.get_tool("ext")
        assert tool is not None
        assert tool.name == "ext"

    def test_get_tool_skill(self) -> None:
        sr = SkillRegistry()
        _register_skill(sr, "extract:x.com")
        tr = ToolRegistry(sr)
        tool = tr.get_tool("extract:x.com")
        assert tool is not None
        assert tool.name == "extract:x.com"

    def test_get_tool_not_found(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        assert tr.get_tool("nope") is None

    def test_external_takes_priority(self) -> None:
        sr = SkillRegistry()
        _register_skill(sr, "overlap")
        tr = ToolRegistry(sr)
        ext = _FakeExternalTool("overlap", desc="external version")
        tr.register_external(ext)
        tool = tr.get_tool("overlap")
        assert tool is not None
        assert tool.description == "external version"

    def test_get_openai_tools_format(self) -> None:
        sr = SkillRegistry()
        _register_skill(sr, "extract:a.com")
        tr = ToolRegistry(sr)
        ext = _FakeExternalTool("ext")
        tr.register_external(ext)
        openai_tools = tr.get_openai_tools()
        assert len(openai_tools) == 2
        for t in openai_tools:
            assert t["type"] == "function"
            assert "function" in t

    def test_mixed_tools_list(self) -> None:
        sr = SkillRegistry()
        _register_skill(sr, "extract:a.com")
        tr = ToolRegistry(sr)
        ext = _FakeExternalTool("web_search")
        tr.register_external(ext)
        tools = tr.list_tools()
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert names == {"extract:a.com", "web_search"}

    async def test_external_tool_callable(self) -> None:
        sr = SkillRegistry()
        tr = ToolRegistry(sr)
        ext = _FakeExternalTool("ext")
        tr.register_external(ext)
        tool = tr.get_tool("ext")
        assert tool is not None
        result = await tool(input="test")
        assert result == {"external": True}

    async def test_skill_tool_callable(self) -> None:
        sr = SkillRegistry()
        _register_skill(sr, "extract:a.com")
        tr = ToolRegistry(sr)
        tool = tr.get_tool("extract:a.com")
        assert tool is not None
        result = await tool(html="<p>hi</p>")
        assert result == {"out": True}
