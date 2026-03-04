"""Tests for the FastAPI server."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from evosys.server import app


@pytest.fixture()
async def client():
    """Create a test client with mocked bootstrap."""
    from evosys.config import EvoSysConfig

    # We need to mock the lifespan to avoid real DB/LLM connections.
    # Instead, we test the endpoints with a properly bootstrapped in-memory runtime.
    cfg = EvoSysConfig(db_url="sqlite+aiosqlite:///:memory:")

    from evosys.bootstrap import bootstrap

    runtime = await bootstrap(cfg, load_builtin_skills=True)

    # Inject runtime into server module globals
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

    # Clean up globals
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
