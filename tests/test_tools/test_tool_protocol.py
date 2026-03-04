"""Tests for Tool protocol."""

from evosys.core.tool import Tool


class _FakeTool:
    """Satisfies the Tool protocol via structural typing."""

    @property
    def name(self) -> str:
        return "fake"

    @property
    def description(self) -> str:
        return "A fake tool"

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {"url": {"type": "string"}}

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        return {"ok": True}

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": self.parameters_schema},
            },
        }


class TestToolProtocol:
    def test_isinstance_check(self) -> None:
        tool = _FakeTool()
        assert isinstance(tool, Tool)

    def test_openai_format(self) -> None:
        tool = _FakeTool()
        fmt = tool.to_openai_tool()
        assert fmt["type"] == "function"
        fn = fmt["function"]
        assert fn["name"] == "fake"
        assert fn["description"] == "A fake tool"

    async def test_call(self) -> None:
        tool = _FakeTool()
        result = await tool(url="http://example.com")
        assert result == {"ok": True}
