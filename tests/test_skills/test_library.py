"""Tests for built-in skill library."""

from __future__ import annotations

from evosys.skills.library import (
    ArticleMetadataSkill,
    ArxivPaperSkill,
    GitHubRepoSkill,
    HackerNewsSkill,
    ProductPageSkill,
    RecipeSkill,
    RedditThreadSkill,
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


# ---------------------------------------------------------------------------
# GitHubRepoSkill
# ---------------------------------------------------------------------------

_GITHUB_HTML = """\
<html>
<head>
<meta property="og:title" content="user/my-awesome-lib" />
</head>
<body>
<strong itemprop="name">my-awesome-lib</strong>
<p class="f4 my-3" itemprop="about">A fast library for doing awesome things.</p>
<span itemprop="programmingLanguage">Python</span>
<span id="repo-stars-counter-star" aria-label="12345 users starred this repository">12,345</span>
<span id="repo-network-counter" aria-label="1234 users forked this repository">1,234</span>
<a href="/user/my-awesome-lib/blob/main/LICENSE">MIT License</a>
<a data-topic-tag="python">python</a>
<a data-topic-tag="async">async</a>
</body>
</html>
"""


class TestGitHubRepoSkill:
    async def test_extracts_name(self):
        result = await GitHubRepoSkill().invoke({"html": _GITHUB_HTML})
        assert result["name"] == "my-awesome-lib"

    async def test_extracts_description(self):
        result = await GitHubRepoSkill().invoke({"html": _GITHUB_HTML})
        assert "awesome" in result["description"]

    async def test_extracts_language(self):
        result = await GitHubRepoSkill().invoke({"html": _GITHUB_HTML})
        assert result["language"] == "Python"

    async def test_extracts_stars(self):
        result = await GitHubRepoSkill().invoke({"html": _GITHUB_HTML})
        assert result["stars"] == 12345

    async def test_extracts_topics(self):
        result = await GitHubRepoSkill().invoke({"html": _GITHUB_HTML})
        assert "python" in result["topics"]

    async def test_handles_empty_html(self):
        result = await GitHubRepoSkill().invoke({"html": ""})
        assert result["stars"] == 0
        assert result["topics"] == []

    async def test_validate(self):
        assert GitHubRepoSkill().validate() is True


# ---------------------------------------------------------------------------
# ArxivPaperSkill
# ---------------------------------------------------------------------------

_ARXIV_HTML = """\
<html>
<head><title>LoRA: Low-Rank Adaptation of Large Language Models</title></head>
<body>
<h1 class="title mathjax">
  <span>Title:</span>LoRA: Low-Rank Adaptation of Large Language Models
</h1>
<div class="authors">
  <a href="/a/hu.html">Edward J. Hu</a>,
  <a href="/a/shen.html">Yelong Shen</a>
</div>
<blockquote class="abstract mathjax">
  <span class="descriptor">Abstract:</span>
  We propose a method called Low-Rank Adaptation.
</blockquote>
<div class="submission-history">
  Submitted on 17 Jun 2021
</div>
<span class="primary-subject">Machine Learning (cs.LG)</span>
</body>
</html>
"""


class TestArxivPaperSkill:
    async def test_extracts_title(self):
        result = await ArxivPaperSkill().invoke({
            "html": _ARXIV_HTML, "url": "https://arxiv.org/abs/2106.09685"
        })
        assert "LoRA" in result["title"]

    async def test_extracts_arxiv_id(self):
        result = await ArxivPaperSkill().invoke({
            "html": _ARXIV_HTML, "url": "https://arxiv.org/abs/2106.09685"
        })
        assert result["arxiv_id"] == "2106.09685"

    async def test_extracts_authors(self):
        result = await ArxivPaperSkill().invoke({"html": _ARXIV_HTML, "url": ""})
        assert "Edward J. Hu" in result["authors"]
        assert "Yelong Shen" in result["authors"]

    async def test_extracts_abstract(self):
        result = await ArxivPaperSkill().invoke({"html": _ARXIV_HTML, "url": ""})
        assert "Low-Rank" in result["abstract"]

    async def test_extracts_subjects(self):
        result = await ArxivPaperSkill().invoke({"html": _ARXIV_HTML, "url": ""})
        assert "cs.LG" in result["subjects"]

    async def test_handles_empty_html(self):
        result = await ArxivPaperSkill().invoke({"html": "", "url": ""})
        assert result["authors"] == []
        assert result["arxiv_id"] == ""

    async def test_validate(self):
        assert ArxivPaperSkill().validate() is True


# ---------------------------------------------------------------------------
# RedditThreadSkill
# ---------------------------------------------------------------------------

_REDDIT_HTML = """\
<html>
<head>
<meta property="og:title" content="ELI5: How do computers work?" />
</head>
<body>
<a href="/r/explainlikeimfive/">r/explainlikeimfive</a>
<div class="score unvoted" title="not voted yet">1234 points</div>
<a class="author">questioner99</a>
<p>42 comments</p>
<div class="md"><p>Computers use transistors to represent binary data.</p></div>
<div class="md"><p>At the most basic level everything is 0s and 1s.</p></div>
</body>
</html>
"""


class TestRedditThreadSkill:
    async def test_extracts_title(self):
        result = await RedditThreadSkill().invoke({"html": _REDDIT_HTML})
        assert "computers" in result["title"].lower()

    async def test_extracts_subreddit(self):
        result = await RedditThreadSkill().invoke({"html": _REDDIT_HTML})
        assert result["subreddit"] == "explainlikeimfive"

    async def test_extracts_author(self):
        result = await RedditThreadSkill().invoke({"html": _REDDIT_HTML})
        assert result["author"] == "questioner99"

    async def test_extracts_comment_count(self):
        result = await RedditThreadSkill().invoke({"html": _REDDIT_HTML})
        assert result["comment_count"] == 42

    async def test_extracts_top_comments(self):
        result = await RedditThreadSkill().invoke({"html": _REDDIT_HTML})
        assert len(result["top_comments"]) > 0

    async def test_handles_empty_html(self):
        result = await RedditThreadSkill().invoke({"html": ""})
        assert result["subreddit"] == ""
        assert result["top_comments"] == []

    async def test_validate(self):
        assert RedditThreadSkill().validate() is True


# ---------------------------------------------------------------------------
# RecipeSkill (schema.org JSON-LD path)
# ---------------------------------------------------------------------------

_RECIPE_HTML = """\
<html>
<head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Recipe",
  "name": "Classic Chocolate Chip Cookies",
  "description": "The best cookies you will ever make.",
  "prepTime": "PT15M",
  "cookTime": "PT12M",
  "totalTime": "PT27M",
  "recipeYield": "24 cookies",
  "recipeIngredient": [
    "2 1/4 cups all-purpose flour",
    "1 tsp baking soda",
    "2 eggs"
  ],
  "recipeInstructions": [
    {"@type": "HowToStep", "text": "Preheat oven to 375F."},
    {"@type": "HowToStep", "text": "Mix dry ingredients."},
    {"@type": "HowToStep", "text": "Bake for 11-13 minutes."}
  ],
  "nutrition": {"@type": "NutritionInformation", "calories": "150 calories"},
  "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.9"}
}
</script>
</head>
<body><h1>Chocolate Chip Cookies</h1></body>
</html>
"""


class TestRecipeSkill:
    async def test_extracts_name(self):
        result = await RecipeSkill().invoke({"html": _RECIPE_HTML})
        assert result["name"] == "Classic Chocolate Chip Cookies"

    async def test_extracts_times(self):
        result = await RecipeSkill().invoke({"html": _RECIPE_HTML})
        assert result["prep_time"] == "PT15M"
        assert result["cook_time"] == "PT12M"

    async def test_extracts_ingredients(self):
        result = await RecipeSkill().invoke({"html": _RECIPE_HTML})
        assert len(result["ingredients"]) == 3

    async def test_extracts_instruction_count(self):
        result = await RecipeSkill().invoke({"html": _RECIPE_HTML})
        assert result["instructions_count"] == 3

    async def test_extracts_calories(self):
        result = await RecipeSkill().invoke({"html": _RECIPE_HTML})
        assert "150" in result["calories"]

    async def test_extracts_rating(self):
        result = await RecipeSkill().invoke({"html": _RECIPE_HTML})
        assert result["rating"] == "4.9"

    async def test_fallback_for_non_json_ld_page(self):
        html = (
            "<html><head>"
            "<meta property='og:title' content='Simple Soup' />"
            "<meta property='og:description' content='Easy soup recipe.' />"
            "</head><body></body></html>"
        )
        result = await RecipeSkill().invoke({"html": html})
        assert result["name"] == "Simple Soup"
        assert result["ingredients"] == []

    async def test_validate(self):
        assert RecipeSkill().validate() is True


# ---------------------------------------------------------------------------
# ProductPageSkill (schema.org JSON-LD path)
# ---------------------------------------------------------------------------

_PRODUCT_HTML = """\
<html>
<head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "Wireless Noise-Cancelling Headphones",
  "brand": {"@type": "Brand", "name": "SoundCo"},
  "description": "Premium headphones with 30-hour battery life.",
  "offers": {
    "@type": "Offer",
    "price": "79.99",
    "priceCurrency": "USD",
    "availability": "https://schema.org/InStock"
  },
  "aggregateRating": {
    "@type": "AggregateRating",
    "ratingValue": "4.5",
    "reviewCount": "1823"
  }
}
</script>
</head>
<body><h1>Wireless Headphones</h1></body>
</html>
"""


class TestProductPageSkill:
    async def test_extracts_name(self):
        result = await ProductPageSkill().invoke({"html": _PRODUCT_HTML})
        assert result["name"] == "Wireless Noise-Cancelling Headphones"

    async def test_extracts_price(self):
        result = await ProductPageSkill().invoke({"html": _PRODUCT_HTML})
        assert result["price"] == "79.99"
        assert result["currency"] == "USD"

    async def test_extracts_availability(self):
        result = await ProductPageSkill().invoke({"html": _PRODUCT_HTML})
        assert result["availability"] == "InStock"

    async def test_extracts_rating(self):
        result = await ProductPageSkill().invoke({"html": _PRODUCT_HTML})
        assert result["rating"] == "4.5"
        assert result["review_count"] == "1823"

    async def test_extracts_brand(self):
        result = await ProductPageSkill().invoke({"html": _PRODUCT_HTML})
        assert result["brand"] == "SoundCo"

    async def test_fallback_for_non_json_ld_page(self):
        html = (
            "<html><head>"
            "<meta property='og:title' content='Some Product' />"
            "</head><body></body></html>"
        )
        result = await ProductPageSkill().invoke({"html": html})
        assert result["name"] == "Some Product"
        assert result["price"] == ""

    async def test_validate(self):
        assert ProductPageSkill().validate() is True
