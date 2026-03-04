"""HTTP executor — fetches a URL and returns an Observation."""

from __future__ import annotations

import time

import httpx

from evosys.core.interfaces import BaseExecutor
from evosys.core.types import Action, Observation


class HttpExecutor(BaseExecutor):
    """Fetch a URL and return the response body as an :class:`Observation`.

    Never raises — errors are always captured in the Observation.
    """

    def __init__(
        self,
        timeout_s: float = 30.0,
        max_body_bytes: int = 5_000_000,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._timeout_s = timeout_s
        self._max_body_bytes = max_body_bytes
        self._client = client

    async def execute(self, action: Action) -> Observation:
        """Execute an HTTP fetch and return an :class:`Observation`."""
        url = action.params.get("url")
        if not url or not isinstance(url, str):
            return Observation(
                action_id=action.action_id,
                success=False,
                error="Missing or invalid 'url' param",
            )

        t0 = time.monotonic()
        try:
            if self._client is not None:
                resp = await self._client.get(
                    url, timeout=self._timeout_s, follow_redirects=True
                )
            else:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    resp = await client.get(url, timeout=self._timeout_s)

            elapsed_ms = (time.monotonic() - t0) * 1000
            resp.raise_for_status()

            body = resp.text[: self._max_body_bytes]
            return Observation(
                action_id=action.action_id,
                success=True,
                result={
                    "html": body,
                    "status_code": resp.status_code,
                    "content_type": resp.headers.get("content-type", ""),
                    "url": str(resp.url),
                },
                latency_ms=elapsed_ms,
            )
        except httpx.TimeoutException:
            elapsed_ms = (time.monotonic() - t0) * 1000
            return Observation(
                action_id=action.action_id,
                success=False,
                error=f"Timeout after {self._timeout_s}s fetching {url}",
                latency_ms=elapsed_ms,
            )
        except httpx.HTTPStatusError as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            return Observation(
                action_id=action.action_id,
                success=False,
                error=f"HTTP {exc.response.status_code} for {url}",
                latency_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            return Observation(
                action_id=action.action_id,
                success=False,
                error=str(exc),
                latency_ms=elapsed_ms,
            )
