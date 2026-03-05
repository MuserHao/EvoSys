"""Tests for local model probe and tier strategy."""

from __future__ import annotations

from evosys.llm.local_probe import LocalModel, LocalModelProbe
from evosys.llm.tier_strategy import TierStrategy


class TestLocalModelProbe:
    async def test_is_available_false_on_connection_error(self) -> None:
        probe = LocalModelProbe("http://localhost:99999")
        assert await probe.is_available() is False

    async def test_list_models_empty_on_error(self) -> None:
        probe = LocalModelProbe("http://localhost:99999")
        models = await probe.list_models()
        assert models == []

    async def test_get_best_model_none_when_unavailable(self) -> None:
        probe = LocalModelProbe("http://localhost:99999")
        assert await probe.get_best_model() is None


class TestLocalModel:
    def test_model_fields(self) -> None:
        m = LocalModel(name="llama3:latest", size_bytes=4_000_000_000, parameter_count="8B")
        assert m.name == "llama3:latest"
        assert m.size_bytes == 4_000_000_000


class TestTierStrategy:
    def test_short_message_routes_local(self) -> None:
        strategy = TierStrategy("ollama/llama3", "anthropic/claude-sonnet-4-20250514")
        decision = strategy.decide(
            [{"role": "user", "content": "What is 2+2?"}]
        )
        assert decision.tier == "local"

    def test_long_message_routes_cloud(self) -> None:
        strategy = TierStrategy(
            "ollama/llama3", "anthropic/claude-sonnet-4-20250514",
            max_local_tokens=100,
        )
        long_text = "x" * 2000  # ~500 tokens
        decision = strategy.decide(
            [{"role": "user", "content": long_text}]
        )
        assert decision.tier == "cloud"

    def test_many_tools_routes_cloud(self) -> None:
        strategy = TierStrategy(
            "ollama/llama3", "anthropic/claude-sonnet-4-20250514",
            max_local_tools=2,
        )
        tools = [{"type": "function", "function": {"name": f"tool_{i}"}} for i in range(5)]
        decision = strategy.decide(
            [{"role": "user", "content": "hi"}],
            tools=tools,
        )
        assert decision.tier == "cloud"
        assert "tools" in decision.reason.lower()

    def test_no_tools_short_message_local(self) -> None:
        strategy = TierStrategy("ollama/llama3", "cloud-model")
        decision = strategy.decide(
            [{"role": "user", "content": "hello"}],
            tools=None,
        )
        assert decision.tier == "local"

    def test_complex_indicator_routes_cloud(self) -> None:
        strategy = TierStrategy("ollama/llama3", "cloud-model", max_local_tools=10)
        tools = [{"type": "function", "function": {"name": "web_fetch"}}]
        decision = strategy.decide(
            [{"role": "user", "content": "search for python tutorials"}],
            tools=tools,
        )
        assert decision.tier == "cloud"
