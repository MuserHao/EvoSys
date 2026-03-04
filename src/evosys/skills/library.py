"""Hand-crafted extraction skills for known domains.

These are Tier 0/1 skills — deterministic HTML parsing, no LLM needed.
They serve as the first manually forged skills to validate the skill
routing pipeline end-to-end.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from evosys.core.interfaces import BaseSkill

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    """Simple HTML → plain-text extractor."""

    def __init__(self) -> None:
        super().__init__()
        self._pieces: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._pieces.append(data)

    def get_text(self) -> str:
        return " ".join(self._pieces)


def _extract_meta(html: str, name: str) -> str:
    """Extract content from <meta name="..." content="...">."""
    esc = re.escape(name)
    pattern = (
        rf'<meta\s+[^>]*?name\s*=\s*["\']?{esc}["\']?'
        rf'\s+[^>]*?content\s*=\s*["\']([^"\']*)["\']'
    )
    m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    # Try reversed attribute order
    pattern2 = (
        rf'<meta\s+[^>]*?content\s*=\s*["\']([^"\']*)["\']'
        rf'[^>]*?name\s*=\s*["\']?{esc}["\']?'
    )
    m2 = re.search(pattern2, html, re.IGNORECASE | re.DOTALL)
    return m2.group(1).strip() if m2 else ""


def _extract_tag(html: str, tag: str) -> str:
    """Extract text content of the first occurrence of <tag>...</tag>."""
    pattern = rf"<{tag}[^>]*>(.*?)</{tag}>"
    m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    # Strip inner tags
    inner = re.sub(r"<[^>]+>", "", m.group(1))
    return " ".join(inner.split()).strip()


def _extract_og(html: str, prop: str) -> str:
    """Extract content from <meta property="og:..." content="...">."""
    esc = re.escape(prop)
    pattern = (
        rf'<meta\s+[^>]*?property\s*=\s*["\']og:{esc}["\']'
        rf'[^>]*?content\s*=\s*["\']([^"\']*)["\']'
    )
    m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    pattern2 = (
        rf'<meta\s+[^>]*?content\s*=\s*["\']([^"\']*)["\']'
        rf'[^>]*?property\s*=\s*["\']og:{esc}["\']'
    )
    m2 = re.search(pattern2, html, re.IGNORECASE | re.DOTALL)
    return m2.group(1).strip() if m2 else ""


# ---------------------------------------------------------------------------
# Skill: HackerNews item extraction
# ---------------------------------------------------------------------------

class HackerNewsSkill(BaseSkill):
    """Extract structured data from a Hacker News item page.

    Returns: title, url, score, author, comment_count
    """

    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        html = str(input_data.get("html", ""))
        url = str(input_data.get("url", ""))

        title = _extract_tag(html, "title").removesuffix(" | Hacker News").strip()

        # Score: <span class="score" ...>123 points</span>
        score_m = re.search(r'class="score"[^>]*>(\d+)\s+point', html)
        score = int(score_m.group(1)) if score_m else 0

        # Author: <a ... class="hnuser">username</a>
        author_m = re.search(r'class="hnuser"[^>]*>([^<]+)<', html)
        author = author_m.group(1).strip() if author_m else ""

        # Comment count: <a ...>123&nbsp;comments</a>
        comment_m = re.search(r">(\d+)\s*&nbsp;comment", html)
        comment_count = int(comment_m.group(1)) if comment_m else 0

        # Story URL: <a ... class="titleline">...<a href="...">
        story_url_m = re.search(
            r'class="titleline"[^>]*>.*?<a\s+href="([^"]+)"', html, re.DOTALL
        )
        story_url = story_url_m.group(1) if story_url_m else url

        return {
            "title": title,
            "story_url": story_url,
            "score": score,
            "author": author,
            "comment_count": comment_count,
        }

    def validate(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Skill: Generic article/page metadata extraction
# ---------------------------------------------------------------------------

class ArticleMetadataSkill(BaseSkill):
    """Extract metadata from a generic article page using meta tags.

    Returns: title, description, author, published_date, canonical_url
    Works on most news sites, blogs, and content pages that follow
    standard meta tag conventions.
    """

    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        html = str(input_data.get("html", ""))
        url = str(input_data.get("url", ""))

        title = (
            _extract_og(html, "title")
            or _extract_meta(html, "title")
            or _extract_tag(html, "title")
        )

        description = (
            _extract_og(html, "description")
            or _extract_meta(html, "description")
        )

        author = (
            _extract_meta(html, "author")
            or _extract_meta(html, "article:author")
        )

        published_date = (
            _extract_meta(html, "article:published_time")
            or _extract_meta(html, "date")
            or _extract_meta(html, "pubdate")
        )

        canonical_m = re.search(
            r'<link\s+[^>]*?rel\s*=\s*["\']canonical["\'][^>]*?href\s*=\s*["\']([^"\']+)["\']',
            html,
            re.IGNORECASE,
        )
        canonical_url = canonical_m.group(1).strip() if canonical_m else url

        return {
            "title": title,
            "description": description,
            "author": author,
            "published_date": published_date,
            "canonical_url": canonical_url,
        }

    def validate(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Skill: Wikipedia article summary extraction
# ---------------------------------------------------------------------------

class WikipediaSummarySkill(BaseSkill):
    """Extract summary data from a Wikipedia article page.

    Returns: title, first_paragraph, categories, last_edited
    """

    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        html = str(input_data.get("html", ""))

        title = _extract_tag(html, "title").removesuffix(" - Wikipedia").strip()

        # First paragraph: content inside <p> tags in the body, skip empty
        paragraphs: list[str] = []
        for m in re.finditer(r"<p[^>]*>(.*?)</p>", html, re.DOTALL):
            text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            text = re.sub(r"\[\d+\]", "", text)  # strip citation refs
            if len(text) > 50:  # skip stub paragraphs
                paragraphs.append(text)
                break

        first_paragraph = paragraphs[0] if paragraphs else ""

        # Categories: <a ... title="Category:...">
        categories: list[str] = []
        for cm in re.finditer(r'title="Category:([^"]+)"', html):
            cat = cm.group(1).strip()
            if cat and cat not in categories:
                categories.append(cat)

        # Last edited: "This page was last edited on ..."
        edited_m = re.search(r"last edited on ([^<]+)", html)
        last_edited = edited_m.group(1).strip().rstrip(".") if edited_m else ""

        return {
            "title": title,
            "first_paragraph": first_paragraph,
            "categories": categories[:10],  # cap at 10
            "last_edited": last_edited,
        }

    def validate(self) -> bool:
        return True
