"""Outbound webhook channel — fires HTTP POSTs on system events.

Notifies external services when tasks complete, skills are forged,
or other significant events occur.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

log = structlog.get_logger()


class WebhookNotifier:
    """Send outbound webhook notifications for system events.

    Parameters
    ----------
    webhook_urls:
        List of URLs to POST events to.
    timeout_s:
        HTTP timeout for webhook delivery.
    """

    def __init__(
        self,
        webhook_urls: list[str] | None = None,
        *,
        timeout_s: float = 10.0,
    ) -> None:
        self._urls = webhook_urls or []
        self._timeout_s = timeout_s

    @property
    def is_configured(self) -> bool:
        return bool(self._urls)

    async def notify(
        self,
        event_type: str,
        data: dict[str, Any],
    ) -> int:
        """Send an event to all configured webhook URLs.

        Returns the number of successful deliveries.
        """
        if not self._urls:
            return 0

        import httpx

        payload = {
            "event": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": data,
        }

        successes = 0
        async with httpx.AsyncClient() as client:
            for url in self._urls:
                try:
                    resp = await client.post(
                        url,
                        json=payload,
                        timeout=self._timeout_s,
                        headers={"Content-Type": "application/json"},
                    )
                    if resp.is_success:
                        successes += 1
                    else:
                        log.warning(
                            "webhook.delivery_failed",
                            url=url,
                            status=resp.status_code,
                        )
                except Exception:
                    log.exception("webhook.delivery_error", url=url)

        return successes

    async def task_complete(
        self,
        task: str,
        answer: str,
        session_id: str,
        tokens: int,
    ) -> int:
        """Notify that an agent task completed."""
        return await self.notify("task_complete", {
            "task": task[:200],
            "answer": answer[:500],
            "session_id": session_id,
            "total_tokens": tokens,
        })

    async def skill_forged(
        self,
        skill_name: str,
        confidence: float,
        domain: str,
    ) -> int:
        """Notify that a new skill was forged."""
        return await self.notify("skill_forged", {
            "skill_name": skill_name,
            "confidence": confidence,
            "domain": domain,
        })

    async def evolution_cycle(
        self,
        cycle: int,
        candidates: int,
        forged: int,
    ) -> int:
        """Notify that an evolution cycle completed."""
        return await self.notify("evolution_cycle", {
            "cycle": cycle,
            "candidates_found": candidates,
            "skills_forged": forged,
        })
