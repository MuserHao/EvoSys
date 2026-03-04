"""Tests for SkillToolAdapter."""


from evosys.core.interfaces import BaseSkill
from evosys.core.tool import Tool
from evosys.schemas._types import ImplementationType
from evosys.schemas.skill import SkillRecord
from evosys.skills.registry import SkillEntry
from evosys.tools.skill_adapter import SkillToolAdapter


class _StubSkill(BaseSkill):
    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        return {"title": "stub", **input_data}

    def validate(self) -> bool:
        return True


def _make_entry(
    name: str = "extract:example.com",
    description: str = "Test skill",
    input_schema: dict[str, object] | None = None,
) -> SkillEntry:
    record = SkillRecord(
        name=name,
        description=description,
        implementation_type=ImplementationType.DETERMINISTIC,
        implementation_path="test",
        test_suite_path="test",
        input_schema=input_schema or {"html": "str"},
        output_schema={"title": "str"},
    )
    return SkillEntry(record=record, implementation=_StubSkill())


class TestSkillToolAdapter:
    def test_satisfies_protocol(self) -> None:
        adapter = SkillToolAdapter(_make_entry())
        assert isinstance(adapter, Tool)

    def test_name(self) -> None:
        adapter = SkillToolAdapter(_make_entry(name="extract:test.com"))
        assert adapter.name == "extract:test.com"

    def test_description(self) -> None:
        adapter = SkillToolAdapter(_make_entry(description="My skill"))
        assert adapter.description == "My skill"

    def test_parameters_schema(self) -> None:
        adapter = SkillToolAdapter(
            _make_entry(input_schema={"url": "str", "html": "str"})
        )
        assert adapter.parameters_schema == {"url": "str", "html": "str"}

    async def test_call_delegates_to_skill(self) -> None:
        adapter = SkillToolAdapter(_make_entry())
        result = await adapter(html="<h1>Hi</h1>")
        assert result["title"] == "stub"
        assert result["html"] == "<h1>Hi</h1>"

    def test_to_openai_tool_format(self) -> None:
        adapter = SkillToolAdapter(_make_entry(name="extract:x.com", description="desc"))
        fmt = adapter.to_openai_tool()
        assert fmt["type"] == "function"
        fn = fmt["function"]
        assert fn["name"] == "extract:x.com"
        assert fn["description"] == "desc"
        assert "properties" in fn["parameters"]

    def test_parameters_schema_is_copy(self) -> None:
        entry = _make_entry(input_schema={"a": "str"})
        adapter = SkillToolAdapter(entry)
        schema = adapter.parameters_schema
        schema["b"] = "int"
        assert "b" not in adapter.parameters_schema
