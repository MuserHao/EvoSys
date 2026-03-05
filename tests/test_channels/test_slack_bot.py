"""Tests for Slack bot components."""

from __future__ import annotations

from evosys.channels.slack.formatting import to_slack_mrkdwn
from evosys.channels.slack.threading import resolve_thread_id


class TestFormatting:
    def test_bold_conversion(self) -> None:
        assert to_slack_mrkdwn("**hello**") == "*hello*"

    def test_link_conversion(self) -> None:
        result = to_slack_mrkdwn("[click](https://example.com)")
        assert result == "<https://example.com|click>"

    def test_header_conversion(self) -> None:
        assert to_slack_mrkdwn("## Title") == "*Title*"

    def test_empty_text(self) -> None:
        assert to_slack_mrkdwn("") == ""

    def test_code_blocks_preserved(self) -> None:
        text = "```python\nprint('hi')\n```"
        assert "```" in to_slack_mrkdwn(text)

    def test_combined_formatting(self) -> None:
        text = "**Bold** and [link](https://x.com)"
        result = to_slack_mrkdwn(text)
        assert "*Bold*" in result
        assert "<https://x.com|link>" in result


class TestThreading:
    def test_existing_thread(self) -> None:
        event = {"thread_ts": "123.456", "ts": "789.012"}
        assert resolve_thread_id(event, True) == "123.456"
        assert resolve_thread_id(event, False) == "123.456"

    def test_top_level_with_threading(self) -> None:
        event = {"ts": "111.222"}
        assert resolve_thread_id(event, True) == "111.222"

    def test_top_level_without_threading(self) -> None:
        event = {"ts": "111.222"}
        assert resolve_thread_id(event, False) is None
