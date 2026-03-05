"""HTTP executor — fetches a URL and returns an Observation.

Two fetch strategies:
- Plain httpx (default): fast, low overhead, works for static HTML.
- Browser (Playwright): renders JavaScript, required for SPAs and most
  modern consumer sites.  Enabled via ``browser_fetch=True``.
  Requires: uv sync --group browser && playwright install chromium
"""

from __future__ import annotations

import time

import httpx

from evosys.core.interfaces import BaseExecutor
from evosys.core.types import Action, Observation


class HttpExecutor(BaseExecutor):
    """Fetch a URL and return the response body as an :class:`Observation`.

    Never raises — errors are always captured in the Observation.

    When *browser_fetch* is ``True`` the executor uses Playwright to
    launch a headless Chromium browser, navigate to the URL, wait for
    the network to settle, and return the fully-rendered HTML.  This
    adds ~1-2 s of latency but makes JavaScript-rendered pages work.
    """

    def __init__(
        self,
        timeout_s: float = 30.0,
        max_body_bytes: int = 5_000_000,
        client: httpx.AsyncClient | None = None,
        *,
        browser_fetch: bool = False,
    ) -> None:
        self._timeout_s = timeout_s
        self._max_body_bytes = max_body_bytes
        self._client = client
        self._browser_fetch = browser_fetch

    async def execute(self, action: Action) -> Observation:
        """Execute an HTTP fetch and return an :class:`Observation`."""
        url = action.params.get("url")
        if not url or not isinstance(url, str):
            return Observation(
                action_id=action.action_id,
                success=False,
                error="Missing or invalid 'url' param",
            )

        if self._browser_fetch:
            return await self._fetch_with_browser(action, url)
        return await self._fetch_with_httpx(action, url)

    async def _fetch_with_httpx(self, action: Action, url: str) -> Observation:
        """Fetch using plain httpx (static HTML only)."""
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
                    "fetch_method": "httpx",
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

    async def _fetch_with_browser(self, action: Action, url: str) -> Observation:
        """Fetch using Playwright headless Chromium (JavaScript-rendered HTML)."""
        t0 = time.monotonic()
        try:
            from playwright.async_api import async_playwright  # type: ignore[import-untyped]
        except ImportError:
            return Observation(
                action_id=action.action_id,
                success=False,
                error=(
                    "Playwright is not installed. "
                    "Run: uv sync --group browser && playwright install chromium"
                ),
            )

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        user_agent=(
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        )
                    )
                    page = await context.new_page()
                    await page.goto(
                        url,
                        timeout=self._timeout_s * 1000,  # playwright uses ms
                        wait_until="networkidle",
                    )
                    html = await page.content()
                    final_url = page.url
                finally:
                    await browser.close()

            elapsed_ms = (time.monotonic() - t0) * 1000
            body = html[: self._max_body_bytes]
            return Observation(
                action_id=action.action_id,
                success=True,
                result={
                    "html": body,
                    "status_code": 200,
                    "content_type": "text/html",
                    "url": final_url,
                    "fetch_method": "browser",
                },
                latency_ms=elapsed_ms,
            )
        except TimeoutError:
            elapsed_ms = (time.monotonic() - t0) * 1000
            return Observation(
                action_id=action.action_id,
                success=False,
                error=f"Browser timeout after {self._timeout_s}s fetching {url}",
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
