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
