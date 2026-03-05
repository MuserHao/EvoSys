"""Local model probe — detect Ollama and list available models.

Checks if a local Ollama instance is running and what models are
available.  Used by the tier strategy to route simple tasks locally.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class LocalModel:
    """A locally available LLM model."""

    name: str
    size_bytes: int = 0
    parameter_count: str = ""  # e.g. "7B", "13B"
    family: str = ""


class LocalModelProbe:
    """Detect and list models available via Ollama.

    Parameters
    ----------
    base_url:
        Ollama API base URL (default: http://localhost:11434).
    """

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self._base_url = base_url.rstrip("/")

    async def is_available(self) -> bool:
        """Return True if Ollama is reachable."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self._base_url}/api/version", timeout=3.0)
                return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[LocalModel]:
        """List models available on the local Ollama instance."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._base_url}/api/tags", timeout=5.0
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            log.debug("local_probe.list_failed")
            return []

        models: list[LocalModel] = []
        for m in data.get("models", []):
            name = m.get("name", "")
            size = m.get("size", 0)
            details = m.get("details", {})
            param_count = details.get("parameter_size", "")
            family = details.get("family", "")
            models.append(
                LocalModel(
                    name=name,
                    size_bytes=size,
                    parameter_count=param_count,
                    family=family,
                )
            )

        return models

    async def get_best_model(self) -> str | None:
        """Return the best available local model for general tasks.

        Prefers larger models.  Returns None if Ollama is not available
        or has no models.
        """
        if not await self.is_available():
            return None

        models = await self.list_models()
        if not models:
            return None

        # Sort by size (prefer larger models)
        models.sort(key=lambda m: m.size_bytes, reverse=True)
        return f"ollama/{models[0].name}"
