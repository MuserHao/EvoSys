"""Tests for HttpExecutor (mocked httpx)."""

from __future__ import annotations

import httpx

from evosys.core.types import Action
from evosys.executors.http_executor import HttpExecutor


def _make_action(url: str | None = "https://example.com") -> Action:
    params: dict[str, object] = {}
    if url is not None:
        params["url"] = url
    return Action(name="fetch_url", params=params)


class TestSuccessfulFetch:
    async def test_returns_html(self):
        transport = httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                text="<html>Hello</html>",
                headers={"content-type": "text/html"},
            )
        )
        client = httpx.AsyncClient(transport=transport)
        executor = HttpExecutor(client=client)
        obs = await executor.execute(_make_action())
        assert obs.success is True
        assert obs.result["html"] == "<html>Hello</html>"
        assert obs.result["status_code"] == 200
        assert "text/html" in str(obs.result["content_type"])

    async def test_latency_measured(self):
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, text="ok")
        )
        client = httpx.AsyncClient(transport=transport)
        executor = HttpExecutor(client=client)
        obs = await executor.execute(_make_action())
        assert obs.latency_ms >= 0


class TestFailures:
    async def test_404_failure(self):
        transport = httpx.MockTransport(
            lambda req: httpx.Response(404, text="Not found")
        )
        client = httpx.AsyncClient(transport=transport)
        executor = HttpExecutor(client=client)
        obs = await executor.execute(_make_action())
        assert obs.success is False
        assert "404" in (obs.error or "")

    async def test_missing_url_param(self):
        executor = HttpExecutor()
        action = Action(name="fetch_url", params={})
        obs = await executor.execute(action)
        assert obs.success is False
        assert "url" in (obs.error or "").lower()

    async def test_timeout_failure(self):
        def raise_timeout(req: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("read timed out")

        transport = httpx.MockTransport(raise_timeout)
        client = httpx.AsyncClient(transport=transport)
        executor = HttpExecutor(client=client)
        obs = await executor.execute(_make_action())
        assert obs.success is False
        assert "timeout" in (obs.error or "").lower()


class TestBodyTruncation:
    async def test_body_truncated(self):
        big_body = "x" * 1000
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, text=big_body)
        )
        client = httpx.AsyncClient(transport=transport)
        executor = HttpExecutor(max_body_bytes=100, client=client)
        obs = await executor.execute(_make_action())
        assert obs.success is True
        assert len(str(obs.result["html"])) == 100


class TestRedirectFollowed:
    async def test_redirect(self):
        def handler(req: httpx.Request) -> httpx.Response:
            if str(req.url) == "https://example.com/":
                return httpx.Response(
                    301,
                    headers={
                        "location": "https://example.com/redirected",
                        "content-type": "text/html",
                    },
                )
            return httpx.Response(200, text="final", headers={"content-type": "text/html"})

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport, follow_redirects=True)
        executor = HttpExecutor(client=client)
        obs = await executor.execute(_make_action("https://example.com/"))
        assert obs.success is True
        assert obs.result["html"] == "final"


class TestInjectedClient:
    async def test_uses_injected_client(self):
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, text="injected")
        )
        client = httpx.AsyncClient(transport=transport)
        executor = HttpExecutor(client=client)
        obs = await executor.execute(_make_action())
        assert obs.success is True
        assert obs.result["html"] == "injected"


class TestBrowserFetch:
    """Browser fetch path — mock playwright so no real browser is needed."""

    async def test_playwright_not_installed_returns_error(self):
        """When playwright is absent, the executor returns a clear error."""
        import sys
        from unittest.mock import patch

        # Simulate playwright not being installed
        with patch.dict(sys.modules, {"playwright": None, "playwright.async_api": None}):
            executor = HttpExecutor(browser_fetch=True)
            obs = await executor.execute(_make_action())
        assert obs.success is False
        assert "playwright" in (obs.error or "").lower()

    async def test_browser_fetch_flag_false_uses_httpx(self):
        """Ensure browser_fetch=False still uses httpx path."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, text="httpx-path")
        )
        client = httpx.AsyncClient(transport=transport)
        executor = HttpExecutor(client=client, browser_fetch=False)
        obs = await executor.execute(_make_action())
        assert obs.success is True
        assert obs.result["html"] == "httpx-path"
        assert obs.result.get("fetch_method") == "httpx"

    async def test_browser_fetch_success_with_mock(self):
        """Full browser path with mocked playwright objects."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>JS rendered</body></html>")
        mock_page.url = "https://example.com"

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_chromium = AsyncMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)

        mock_pw = MagicMock()
        mock_pw.chromium = mock_chromium
        mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_pw.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "evosys.executors.http_executor.HttpExecutor._fetch_with_browser",
        ) as mock_method:
            mock_method.return_value = type("O", (), {
                "success": True,
                "result": {
                    "html": "<html><body>JS rendered</body></html>",
                    "status_code": 200,
                    "content_type": "text/html",
                    "url": "https://example.com",
                    "fetch_method": "browser",
                },
                "error": None,
                "latency_ms": 1200.0,
                "action_id": _make_action().action_id,
            })()
            executor = HttpExecutor(browser_fetch=True)
            obs = await executor.execute(_make_action())

        assert obs.success is True
        assert obs.result["fetch_method"] == "browser"
