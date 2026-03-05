"""Tests for HttpApiTool and SendEmailTool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from evosys.core.tool import Tool
from evosys.tools.builtins import HttpApiTool, SendEmailTool


class TestHttpApiTool:
    def test_protocol_compliance(self) -> None:
        assert isinstance(HttpApiTool(), Tool)

    def test_name(self) -> None:
        assert HttpApiTool().name == "http_api"

    def test_to_openai_tool_format(self) -> None:
        fmt = HttpApiTool().to_openai_tool()
        assert fmt["type"] == "function"
        fn = fmt["function"]
        assert fn["name"] == "http_api"
        assert "method" in fn["parameters"]["required"]
        assert "url" in fn["parameters"]["required"]

    async def test_post_success(self) -> None:
        tool = HttpApiTool()
        # Patch httpx.AsyncClient to use mock transport
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.is_success = True
            mock_resp.text = '{"id": 42, "created": true}'
            mock_resp.url = "https://api.example.com/items"
            mock_client.request = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await tool(
                method="POST",
                url="https://api.example.com/items",
                body={"name": "widget"},
            )

        assert result["status_code"] == 201
        assert result["ok"] is True
        assert result["body"]["id"] == 42

    async def test_empty_url_returns_error(self) -> None:
        tool = HttpApiTool()
        result = await tool(method="POST", url="")
        assert "error" in result

    async def test_invalid_method_returns_error(self) -> None:
        tool = HttpApiTool()
        result = await tool(method="BREW", url="https://example.com")
        assert "error" in result

    async def test_delete_request(self) -> None:
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_resp = MagicMock()
            mock_resp.status_code = 204
            mock_resp.is_success = True
            mock_resp.text = ""
            mock_resp.url = "https://api.example.com/items/1"
            mock_client.request = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            tool = HttpApiTool()
            result = await tool(method="DELETE", url="https://api.example.com/items/1")

        assert result["status_code"] == 204
        assert result["ok"] is True


class TestSendEmailTool:
    def test_protocol_compliance(self) -> None:
        assert isinstance(SendEmailTool(), Tool)

    def test_name(self) -> None:
        assert SendEmailTool().name == "send_email"

    def test_to_openai_tool_format(self) -> None:
        fmt = SendEmailTool().to_openai_tool()
        assert fmt["type"] == "function"
        fn = fmt["function"]
        assert fn["name"] == "send_email"
        assert "to" in fn["parameters"]["required"]
        assert "subject" in fn["parameters"]["required"]
        assert "body" in fn["parameters"]["required"]

    async def test_not_configured_returns_error(self) -> None:
        """Without SMTP env vars, tool returns a clear configuration error."""
        import os
        env_backup = {k: os.environ.pop(k, None) for k in [
            "EVOSYS_SMTP_HOST", "EVOSYS_SMTP_USER", "EVOSYS_SMTP_PASSWORD"
        ]}
        try:
            tool = SendEmailTool()
            result = await tool(to="user@example.com", subject="Hi", body="Hello")
            assert "error" in result
            assert "SMTP" in result["error"]
        finally:
            for k, v in env_backup.items():
                if v is not None:
                    os.environ[k] = v

    async def test_empty_to_returns_error(self) -> None:
        import os
        os.environ["EVOSYS_SMTP_HOST"] = "smtp.example.com"
        os.environ["EVOSYS_SMTP_USER"] = "user"
        os.environ["EVOSYS_SMTP_PASSWORD"] = "pass"
        try:
            tool = SendEmailTool()
            result = await tool(to="", subject="Hi", body="Hello")
            assert "error" in result
        finally:
            for k in ["EVOSYS_SMTP_HOST", "EVOSYS_SMTP_USER", "EVOSYS_SMTP_PASSWORD"]:
                os.environ.pop(k, None)

    async def test_send_success_with_mock_smtp(self) -> None:
        """Email sends successfully when SMTP is mocked."""
        import os
        os.environ["EVOSYS_SMTP_HOST"] = "smtp.example.com"
        os.environ["EVOSYS_SMTP_USER"] = "sender@example.com"
        os.environ["EVOSYS_SMTP_PASSWORD"] = "secret"
        os.environ["EVOSYS_SMTP_FROM"] = "sender@example.com"
        try:
            tool = SendEmailTool()
            with patch("smtplib.SMTP") as mock_smtp_cls:
                mock_smtp = MagicMock()
                mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
                mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
                result = await tool(
                    to="recv@example.com",
                    subject="Test",
                    body="Hello world",
                )
            assert result["sent"] is True
            assert result["to"] == "recv@example.com"
        finally:
            for k in [
                "EVOSYS_SMTP_HOST", "EVOSYS_SMTP_USER",
                "EVOSYS_SMTP_PASSWORD", "EVOSYS_SMTP_FROM"
            ]:
                os.environ.pop(k, None)
