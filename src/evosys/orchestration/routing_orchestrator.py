"""Routing orchestrator — checks skill registry before LLM fallback."""

from __future__ import annotations

import re

from evosys.core.interfaces import BaseOrchestrator
from evosys.core.types import Action, ActionPlan
from evosys.orchestration.extraction_orchestrator import ExtractionOrchestrator
from evosys.skills.registry import SkillRegistry

_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


class RoutingOrchestrator(BaseOrchestrator):
    """Check the skill registry before delegating to a fallback orchestrator.

    Extracts the URL from the task, looks up ``extract:{domain}`` in the
    registry, and routes to the skill if it is ACTIVE and above the
    confidence threshold.  Otherwise falls back to *fallback*
    (defaults to :class:`ExtractionOrchestrator`).
    """

    def __init__(
        self,
        registry: SkillRegistry,
        fallback: BaseOrchestrator | None = None,
        confidence_threshold: float = 0.7,
    ) -> None:
        self._registry = registry
        self._fallback = fallback or ExtractionOrchestrator()
        self._confidence_threshold = confidence_threshold

    async def plan(self, task: str) -> ActionPlan:
        """Produce an action plan, preferring a skill route when available."""
        url = self._extract_url(task)
        if url is not None:
            domain = self._extract_domain(url)
            if domain is not None:
                skill_name = f"extract:{domain}"
                entry = self._registry.lookup_active(
                    skill_name, min_confidence=self._confidence_threshold
                )
                if entry is not None:
                    return ActionPlan(
                        task_description=task,
                        actions=[
                            Action(
                                name="invoke_skill",
                                params={"skill_name": skill_name, "url": url},
                            )
                        ],
                        reasoning=f"Skill {skill_name!r} matched with confidence "
                        f"{entry.record.confidence_score:.2f}.",
                    )

        return await self._fallback.plan(task)

    @staticmethod
    def _extract_url(task: str) -> str | None:
        """Return the first URL found in *task*, or ``None``."""
        m = _URL_RE.search(task)
        return m.group(0) if m else None

    @staticmethod
    def _extract_domain(url: str) -> str | None:
        """Return the domain from *url* with ``www.`` stripped, or ``None``."""
        # Minimal parser: skip scheme, grab host
        try:
            after_scheme = url.split("://", 1)[1]
            host = after_scheme.split("/", 1)[0].split(":", 1)[0]
            if host.startswith("www."):
                host = host[4:]
            return host or None
        except (IndexError, ValueError):
            return None
