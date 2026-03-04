"""Tool protocol — structural typing for all EvoSys tools.

Uses ``Protocol`` instead of ABC so that MCP tools, skill adapters,
and plain functions can satisfy the contract without inheritance.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Tool(Protocol):
    """Structural protocol that any EvoSys tool must satisfy."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def parameters_schema(self) -> dict[str, object]: ...

    async def __call__(self, **kwargs: object) -> dict[str, object]: ...

    def to_openai_tool(self) -> dict[str, object]: ...
