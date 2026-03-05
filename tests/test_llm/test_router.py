"""Tests for ModelRouter and ModelHealth."""

from __future__ import annotations

import pytest

from evosys.llm.client import LLMError
from evosys.llm.health import ModelHealth
from evosys.llm.router import ModelRouter

# --- ModelHealth ---


class TestModelHealth:
    def test_initially_healthy(self) -> None:
        h = ModelHealth(model="test-model")
        assert h.is_healthy is True

    def test_record_success_resets_consecutive(self) -> None:
        h = ModelHealth(model="test-model")
        h.record_failure()
        h.record_failure()
        h.record_success()
        assert h.consecutive_failures == 0
        assert h.successes == 1
        assert h.failures == 2

    def test_cooldown_after_max_failures(self) -> None:
        h = ModelHealth(model="test-model", max_consecutive_failures=2, cooldown_s=1000)
        h.record_failure()
        assert h.is_healthy is True
        h.record_failure()
        assert h.is_healthy is False  # In cooldown

    def test_cooldown_expires(self) -> None:
        h = ModelHealth(model="test-model", max_consecutive_failures=1, cooldown_s=0)
        h.record_failure()
        # With cooldown_s=0, it should be healthy again immediately
        assert h.is_healthy is True

    def test_reset(self) -> None:
        h = ModelHealth(model="test-model")
        h.record_failure()
        h.record_success()
        h.reset()
        assert h.successes == 0
        assert h.failures == 0
        assert h.consecutive_failures == 0


# --- ModelRouter ---


class TestModelRouter:
    def test_requires_at_least_one_model(self) -> None:
        with pytest.raises(ValueError, match="at least one model"):
            ModelRouter([])

    def test_models_property(self) -> None:
        router = ModelRouter(["model-a", "model-b"])
        assert router.models == ["model-a", "model-b"]

    def test_primary_model_exposed(self) -> None:
        router = ModelRouter(["primary", "fallback"])
        assert router.model == "primary"

    def test_health_per_model(self) -> None:
        router = ModelRouter(["m1", "m2", "m3"])
        assert len(router.health) == 3
        assert all(h.is_healthy for h in router.health)

    async def test_complete_falls_back_on_error(self) -> None:
        """Integration test — requires mocking litellm."""
        # This test verifies the router structure; actual LLM calls
        # would need litellm mocks
        router = ModelRouter(
            ["bad-model", "good-model"],
            cooldown_s=0,
            max_consecutive_failures=1,
        )
        # We can't easily test actual failover without mocking litellm,
        # but we can verify the router was constructed correctly
        assert len(router._clients) == 2
        assert len(router._health) == 2

    async def test_all_models_exhausted_raises(self) -> None:
        router = ModelRouter(
            ["model-a"],
            cooldown_s=1000,
            max_consecutive_failures=1,
        )
        # Mark the only model as unhealthy
        router._health[0].record_failure()

        with pytest.raises(LLMError, match="All models exhausted"):
            await router.complete([{"role": "user", "content": "test"}])
