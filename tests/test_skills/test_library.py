"""Tests for built-in skill library."""

from __future__ import annotations

from evosys.skills.library import (
    ArticleMetadataSkill,
    HackerNewsSkill,
    WikipediaSummarySkill,
)

# ---------------------------------------------------------------------------
# HackerNewsSkill
# ---------------------------------------------------------------------------

_HN_HTML = """\
<html>
<head><title>Show HN: My Project | Hacker News</title></head>
<body>
<table>
<tr class="athing"><td class="title"><span class="titleline">
<a href="https://example.com/project">Show HN: My Project</a>
</span></td></tr>
<tr><td>
<span class="score" id="score_123">142 points</span>
by <a class="hnuser" href="user?id=alice">alice</a>
| <a href="item?id=123">87&nbsp;comments</a>
</td></tr>
</table>
</body>
</html>
"""


class TestHackerNewsSkill:
    async def test_extracts_title(self):
        skill = HackerNewsSkill()
        result = await skill.invoke({"html": _HN_HTML, "url": "https://news.ycombinator.com/item?id=123"})
        assert result["title"] == "Show HN: My Project"

    async def test_extracts_score(self):
        skill = HackerNewsSkill()
        result = await skill.invoke({"html": _HN_HTML})
        assert result["score"] == 142

    async def test_extracts_author(self):
        skill = HackerNewsSkill()
        result = await skill.invoke({"html": _HN_HTML})
        assert result["author"] == "alice"

    async def test_extracts_comment_count(self):
        skill = HackerNewsSkill()
        result = await skill.invoke({"html": _HN_HTML})
        assert result["comment_count"] == 87

    async def test_extracts_story_url(self):
        skill = HackerNewsSkill()
        result = await skill.invoke({"html": _HN_HTML})
        assert result["story_url"] == "https://example.com/project"

    async def test_validate(self):
        assert HackerNewsSkill().validate() is True

    async def test_handles_empty_html(self):
        skill = HackerNewsSkill()
        result = await skill.invoke({"html": "", "url": "https://news.ycombinator.com"})
        assert result["title"] == ""
        assert result["score"] == 0


# ---------------------------------------------------------------------------
# ArticleMetadataSkill
# ---------------------------------------------------------------------------

_ARTICLE_HTML = """\
<html>
<head>
<title>How to Build a Startup</title>
<meta property="og:title" content="How to Build a Startup" />
<meta property="og:description" content="A comprehensive guide to startup building." />
<meta name="author" content="Jane Doe" />
<meta name="article:published_time" content="2025-01-15" />
<link rel="canonical" href="https://blog.example.com/startup-guide" />
</head>
<body><p>Content here.</p></body>
</html>
"""


class TestArticleMetadataSkill:
    async def test_extracts_title(self):
        skill = ArticleMetadataSkill()
        result = await skill.invoke({"html": _ARTICLE_HTML, "url": "https://blog.example.com/startup-guide"})
        assert result["title"] == "How to Build a Startup"

    async def test_extracts_description(self):
        skill = ArticleMetadataSkill()
        result = await skill.invoke({"html": _ARTICLE_HTML})
        assert "comprehensive guide" in result["description"]

    async def test_extracts_author(self):
        skill = ArticleMetadataSkill()
        result = await skill.invoke({"html": _ARTICLE_HTML})
        assert result["author"] == "Jane Doe"

    async def test_extracts_published_date(self):
        skill = ArticleMetadataSkill()
        result = await skill.invoke({"html": _ARTICLE_HTML})
        assert result["published_date"] == "2025-01-15"

    async def test_extracts_canonical_url(self):
        skill = ArticleMetadataSkill()
        result = await skill.invoke({"html": _ARTICLE_HTML})
        assert result["canonical_url"] == "https://blog.example.com/startup-guide"

    async def test_validate(self):
        assert ArticleMetadataSkill().validate() is True

    async def test_falls_back_to_title_tag(self):
        html = "<html><head><title>Fallback Title</title></head><body></body></html>"
        skill = ArticleMetadataSkill()
        result = await skill.invoke({"html": html, "url": "https://example.com"})
        assert result["title"] == "Fallback Title"

    async def test_falls_back_url_for_canonical(self):
        html = "<html><head><title>Test</title></head><body></body></html>"
        skill = ArticleMetadataSkill()
        result = await skill.invoke({"html": html, "url": "https://example.com/page"})
        assert result["canonical_url"] == "https://example.com/page"


# ---------------------------------------------------------------------------
# WikipediaSummarySkill
# ---------------------------------------------------------------------------

_WIKI_HTML = """\
<html>
<head><title>Python (programming language) - Wikipedia</title></head>
<body>
<div id="mw-content-text">
<p class="stub">Short stub paragraph.</p>
<p>Python is a high-level, general-purpose programming language. Its design
philosophy emphasizes code readability with the use of significant indentation.
Python is dynamically typed and garbage-collected.[1]</p>
<p>Python was conceived in the late 1980s by Guido van Rossum.</p>
</div>
<div id="catlinks">
<a title="Category:Programming languages">Programming languages</a>
<a title="Category:Python (programming language)">Python</a>
</div>
<li id="footer-info-lastmod">This page was last edited on 15 January 2025.</li>
</body>
</html>
"""


class TestWikipediaSummarySkill:
    async def test_extracts_title(self):
        skill = WikipediaSummarySkill()
        result = await skill.invoke({"html": _WIKI_HTML})
        assert result["title"] == "Python (programming language)"

    async def test_extracts_first_paragraph(self):
        skill = WikipediaSummarySkill()
        result = await skill.invoke({"html": _WIKI_HTML})
        assert "high-level" in result["first_paragraph"]
        # Citation refs should be stripped
        assert "[1]" not in result["first_paragraph"]

    async def test_skips_stub_paragraphs(self):
        skill = WikipediaSummarySkill()
        result = await skill.invoke({"html": _WIKI_HTML})
        assert "stub" not in result["first_paragraph"].lower()

    async def test_extracts_categories(self):
        skill = WikipediaSummarySkill()
        result = await skill.invoke({"html": _WIKI_HTML})
        assert "Programming languages" in result["categories"]

    async def test_extracts_last_edited(self):
        skill = WikipediaSummarySkill()
        result = await skill.invoke({"html": _WIKI_HTML})
        assert "15 January 2025" in result["last_edited"]

    async def test_validate(self):
        assert WikipediaSummarySkill().validate() is True

    async def test_handles_empty_html(self):
        skill = WikipediaSummarySkill()
        result = await skill.invoke({"html": ""})
        assert result["title"] == ""
        assert result["first_paragraph"] == ""
        assert result["categories"] == []
