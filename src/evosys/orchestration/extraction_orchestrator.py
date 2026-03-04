"""Extraction orchestrator — static 2-step plan for URL-to-JSON."""

from __future__ import annotations

from evosys.core.interfaces import BaseOrchestrator
from evosys.core.types import Action, ActionPlan


class ExtractionOrchestrator(BaseOrchestrator):
    """Always produces a 2-action plan: ``fetch_url`` then ``llm_extract``."""

    async def plan(self, task: str) -> ActionPlan:
        """Return a static extraction plan for *task*."""
        fetch = Action(name="fetch_url")
        extract = Action(name="llm_extract", depends_on=[fetch.action_id])
        return ActionPlan(
            task_description=task,
            actions=[fetch, extract],
            reasoning="Fetch HTML from URL, then extract structured data via LLM.",
        )
