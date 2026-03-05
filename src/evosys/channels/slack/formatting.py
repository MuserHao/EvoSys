"""Markdown → Slack mrkdwn conversion."""

from __future__ import annotations

import re


def to_slack_mrkdwn(text: str) -> str:
    """Convert standard markdown to Slack's mrkdwn format.

    Handles the most common differences:
    - **bold** → *bold*
    - _italic_ stays as-is (Slack uses _ too)
    - [link](url) → <url|link>
    - ```code``` stays as-is (Slack supports triple backtick)
    - # headers → *headers* (bold)
    """
    if not text:
        return text

    # Convert markdown links [text](url) → <url|text>
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", text)

    # Convert **bold** → *bold* (Slack uses single * for bold)
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)

    # Convert ## headers → *bold text*
    text = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)

    return text
