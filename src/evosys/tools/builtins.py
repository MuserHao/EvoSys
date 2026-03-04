"""Built-in tools for the general agent.

These wrap existing EvoSys components (HttpExecutor, ExtractionAgent) so
the agent loop can call them as standard tools.
"""

from __future__ import annotations

from typing import Any

from evosys.core.types import Action
from evosys.executors.http_executor import HttpExecutor
from evosys.schemas._types import new_ulid


class WebFetchTool:
    """Fetches a URL and returns HTML content. Wraps HttpExecutor."""

    def __init__(self, http_executor: HttpExecutor) -> None:
        self._http = http_executor

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch a web page and return its HTML content. "
            "Use this when you need to read the contents of a URL."
        )

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {
            "url": {
                "type": "string",
                "description": "The URL to fetch",
            },
        }

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        url = str(kwargs.get("url", ""))
        action = Action(
            action_id=new_ulid(),
            name="fetch_url",
            params={"url": url},
        )
        obs = await self._http.execute(action)
        if obs.success:
            return {
                "html": str(obs.result.get("html", "")),
                "status_code": obs.result.get("status_code", 0),
                "url": str(obs.result.get("url", url)),
            }
        return {"error": obs.error or "Unknown error"}

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters_schema,
                    "required": ["url"],
                },
            },
        }


class ExtractStructuredTool:
    """Extracts structured data from HTML using LLM or skills.

    Wraps the existing ExtractionAgent, preserving full backward
    compatibility with skill routing and trajectory logging.
    """

    def __init__(self, extraction_agent: Any) -> None:
        self._agent = extraction_agent

    @property
    def name(self) -> str:
        return "extract_structured"

    @property
    def description(self) -> str:
        return (
            "Extract structured JSON data from a URL. Returns key-value pairs "
            "based on the page content. Provide the URL and optionally a schema "
            "description of the fields you want."
        )

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {
            "url": {
                "type": "string",
                "description": "The URL to extract data from",
            },
            "schema_description": {
                "type": "string",
                "description": "Description of the target JSON schema",
            },
        }

    async def __call__(self, **kwargs: object) -> dict[str, object]:
        url = str(kwargs.get("url", ""))
        schema_desc = str(kwargs.get("schema_description", "{}"))
        try:
            result = await self._agent.extract(
                url=url,
                target_schema=schema_desc,
            )
            return dict(result.data)
        except Exception as exc:
            return {"error": str(exc)}

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters_schema,
                    "required": ["url"],
                },
            },
        }
