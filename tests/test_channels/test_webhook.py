"""Tests for webhook notifier."""

from __future__ import annotations

from evosys.channels.webhook import WebhookNotifier


class TestWebhookNotifier:
    def test_not_configured_empty_urls(self) -> None:
        n = WebhookNotifier()
        assert n.is_configured is False

    def test_configured_with_urls(self) -> None:
        n = WebhookNotifier(["https://example.com/hook"])
        assert n.is_configured is True

    async def test_notify_no_urls(self) -> None:
        n = WebhookNotifier()
        count = await n.notify("test_event", {"key": "value"})
        assert count == 0

    async def test_task_complete_no_urls(self) -> None:
        n = WebhookNotifier()
        count = await n.task_complete("task", "answer", "sid", 100)
        assert count == 0

    async def test_skill_forged_no_urls(self) -> None:
        n = WebhookNotifier()
        count = await n.skill_forged("extract:x", 0.9, "x")
        assert count == 0

    async def test_evolution_cycle_no_urls(self) -> None:
        n = WebhookNotifier()
        count = await n.evolution_cycle(1, 5, 2)
        assert count == 0
