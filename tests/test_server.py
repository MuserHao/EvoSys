"""Tests for the FastAPI server."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from evosys.server import app


@pytest.fixture()
async def client():
    """Inject an in-memory runtime into the server and return an AsyncClient."""
    from evosys.bootstrap import bootstrap
    from evosys.config import EvoSysConfig

    cfg = EvoSysConfig(db_url="sqlite+aiosqlite:///:memory:")
    runtime = await bootstrap(cfg, load_builtin_skills=True)

    import evosys.server as srv

    srv._runtime = runtime
    srv._evolution_loop = runtime.evolution_loop
    srv._total_evolve_cycles = 0
    srv._total_skills_forged = 0
    srv._last_evolve_result = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await runtime.shutdown()
    srv._runtime = None
    srv._evolution_loop = None


class TestStatusEndpoint:
    async def test_returns_status(self, client):
        resp = await client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "0.1.0"
        assert data["total_skills"] > 0
        assert data["active_skills"] > 0
        assert data["total_evolve_cycles"] == 0


class TestSkillsEndpoint:
    async def test_lists_skills(self, client):
        resp = await client.get("/skills")
        assert resp.status_code == 200
        skills = resp.json()
        assert len(skills) > 0
        names = [s["name"] for s in skills]
        assert any("ycombinator" in n for n in names)

    async def test_skill_fields(self, client):
        resp = await client.get("/skills")
        skill = resp.json()[0]
        assert "name" in skill
        assert "status" in skill
        assert "confidence_score" in skill
        assert "implementation_type" in skill
        assert "invocation_count" in skill


class TestEvolveEndpoint:
    async def test_evolve_empty_db(self, client):
        resp = await client.post("/evolve")
        assert resp.status_code == 200
        data = resp.json()
        assert data["candidates_found"] == 0
        assert data["forge_succeeded"] == 0
        assert data["new_skills"] == []


class TestExtractEndpoint:
    async def test_extract_returns_response_shape(self, client):
        """POST /extract must return the correct response shape.
        We mock the extraction agent so no real HTTP/LLM calls happen."""
        import evosys.server as srv
        from evosys.agents.extraction_agent import ExtractionResult

        fake_result = ExtractionResult(
            data={"title": "Mock Title"},
            url="https://example.com",
            token_cost=10,
            total_latency_ms=50.0,
            session_id="test-session",
            skill_used=None,
        )

        with patch.object(
            srv._runtime.extraction_agent, "extract", new=AsyncMock(return_value=fake_result)
        ):
            resp = await client.post(
                "/extract",
                json={"url": "https://example.com", "schema_description": '{"title": "string"}'},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["data"] == {"title": "Mock Title"}
        assert data["url"] == "https://example.com"
        assert data["token_cost"] == 10
        assert "session_id" in data

    async def test_extract_with_skill_used(self, client):
        import evosys.server as srv
        from evosys.agents.extraction_agent import ExtractionResult

        fake_result = ExtractionResult(
            data={"items": [1, 2, 3]},
            url="https://news.ycombinator.com",
            token_cost=0,
            total_latency_ms=5.0,
            session_id="s2",
            skill_used="extract:news.ycombinator.com",
        )

        with patch.object(
            srv._runtime.extraction_agent, "extract", new=AsyncMock(return_value=fake_result)
        ):
            resp = await client.post(
                "/extract", json={"url": "https://news.ycombinator.com"}
            )

        assert resp.status_code == 200
        assert resp.json()["skill_used"] == "extract:news.ycombinator.com"


class TestAgentRunEndpoint:
    async def test_agent_run_returns_answer(self, client):
        """POST /agent/run must return the correct response shape.
        We mock the general agent so no real LLM calls happen."""
        import evosys.server as srv
        from evosys.agents.agent import AgentResult

        fake_result = AgentResult(
            answer="The answer is 42.",
            total_tokens=20,
            total_latency_ms=100.0,
            session_id="agent-session",
            iterations=1,
        )

        with patch.object(
            srv._runtime.general_agent, "run", new=AsyncMock(return_value=fake_result)
        ):
            resp = await client.post("/agent/run", json={"task": "What is 6 * 7?"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "The answer is 42."
        assert data["iterations"] == 1
        assert data["tool_calls_count"] == 0
        assert "session_id" in data

    async def test_agent_run_with_context(self, client):
        import evosys.server as srv
        from evosys.agents.agent import AgentResult

        fake_result = AgentResult(
            answer="Done.",
            total_tokens=5,
            total_latency_ms=10.0,
            session_id="s3",
            iterations=2,
        )

        with patch.object(
            srv._runtime.general_agent, "run", new=AsyncMock(return_value=fake_result)
        ) as mock_run:
            resp = await client.post(
                "/agent/run",
                json={"task": "Summarise this", "context": {"key": "value"}},
            )

        assert resp.status_code == 200
        # Verify context was passed through
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("context") == {"key": "value"}

