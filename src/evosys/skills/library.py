"""Hand-crafted extraction skills for known domains.

These are Tier 0/1 skills — deterministic HTML parsing, no LLM needed.
They answer questions users actually have, not just "what metadata is on
this page."  Each skill returns structured data meaningful to a person:
price + rating for products, score + comments for HN, abstract for papers,
ingredients + time for recipes, etc.
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


# ---------------------------------------------------------------------------
# Skill: GitHub repository
# ---------------------------------------------------------------------------


class GitHubRepoSkill(BaseSkill):
    """Extract key facts from a GitHub repository page.

    Returns: name, description, language, stars, forks, license, topics
    Answers: "What does this repo do? Is it popular? What language?"
    """

    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        html = str(input_data.get("html", ""))

        # Repo name: <strong itemprop="name">...</strong>
        name_m = re.search(r'itemprop="name"[^>]*>\s*([^<\s][^<]*?)\s*<', html)
        name = name_m.group(1).strip() if name_m else ""

        # Description: <p itemprop="description" ...>
        desc_m = re.search(
            r'itemprop="about"[^>]*>\s*(.*?)\s*</p>', html, re.DOTALL
        )
        if not desc_m:
            desc_m = re.search(
                r'<p\s+class="f4[^"]*"[^>]*>\s*(.*?)\s*</p>', html, re.DOTALL
            )
        description = re.sub(r"<[^>]+>", "", desc_m.group(1)).strip() if desc_m else ""

        # Primary language
        lang_m = re.search(
            r'itemprop="programmingLanguage"[^>]*>\s*([^<]+)\s*<', html
        )
        language = lang_m.group(1).strip() if lang_m else ""

        # Stars
        stars_m = re.search(
            r'id="repo-stars-counter-star"[^>]*>\s*([\d,]+)', html
        )
        stars_raw = stars_m.group(1).replace(",", "") if stars_m else "0"
        try:
            stars = int(stars_raw)
        except ValueError:
            stars = 0

        # Forks
        forks_m = re.search(
            r'id="repo-network-counter"[^>]*>\s*([\d,]+)', html
        )
        forks_raw = forks_m.group(1).replace(",", "") if forks_m else "0"
        try:
            forks = int(forks_raw)
        except ValueError:
            forks = 0

        # License
        license_m = re.search(
            r'<a[^>]+href="[^"]+/blob/[^"]+/LICENSE[^"]*"[^>]*>\s*([^<]+)\s*</a>',
            html,
            re.IGNORECASE,
        )
        if not license_m:
            license_m = re.search(r'"license":\s*\{[^}]*"spdx_id":\s*"([^"]+)"', html)
        license_name = license_m.group(1).strip() if license_m else ""

        # Topics
        topics: list[str] = []
        for tm in re.finditer(r'data-topic-tag="([^"]+)"', html):
            t = tm.group(1).strip()
            if t and t not in topics:
                topics.append(t)

        return {
            "name": name,
            "description": description,
            "language": language,
            "stars": stars,
            "forks": forks,
            "license": license_name,
            "topics": topics[:10],
        }

    def validate(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Skill: arXiv paper
# ---------------------------------------------------------------------------


class ArxivPaperSkill(BaseSkill):
    """Extract structured data from an arXiv abstract page.

    Returns: title, authors, abstract, submitted, subjects, arxiv_id
    Answers: "What is this paper about? Who wrote it? When was it published?"
    """

    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        html = str(input_data.get("html", ""))
        url = str(input_data.get("url", ""))

        # arXiv ID from URL or og:url
        arxiv_id = ""
        id_m = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s/?#]+)", url)
        if id_m:
            arxiv_id = id_m.group(1)

        # Title: <h1 class="title mathjax">
        title_m = re.search(
            r'class="title[^"]*"[^>]*>(.*?)</h1>', html, re.DOTALL
        )
        if title_m:
            raw = re.sub(r"<[^>]+>", "", title_m.group(1))
            title = re.sub(r"\s+", " ", raw).strip().removeprefix("Title:").strip()
        else:
            title = _extract_og(html, "title")

        # Authors: <div class="authors"><a ...>Name</a>, ...
        authors: list[str] = []
        authors_m = re.search(
            r'class="authors"[^>]*>(.*?)</div>', html, re.DOTALL
        )
        if authors_m:
            for am in re.finditer(r"<a[^>]*>([^<]+)</a>", authors_m.group(1)):
                a = am.group(1).strip()
                if a:
                    authors.append(a)

        # Abstract
        abs_m = re.search(
            r'class="abstract[^"]*"[^>]*>.*?Abstract:\s*(.*?)</blockquote>',
            html,
            re.DOTALL,
        )
        if abs_m:
            abstract = re.sub(r"<[^>]+>", "", abs_m.group(1)).strip()
            abstract = re.sub(r"\s+", " ", abstract)
        else:
            abstract = ""

        # Submission date
        date_m = re.search(r"Submitted on ([^<;]+)", html)
        submitted = date_m.group(1).strip() if date_m else ""

        # Primary subject
        subj_m = re.search(r'class="primary-subject"[^>]*>([^<]+)<', html)
        subjects = subj_m.group(1).strip() if subj_m else ""

        return {
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": authors,
            "abstract": abstract,
            "submitted": submitted,
            "subjects": subjects,
        }

    def validate(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Skill: Reddit thread
# ---------------------------------------------------------------------------


class RedditThreadSkill(BaseSkill):
    """Extract structured data from a Reddit thread page (old.reddit.com).

    Returns: title, subreddit, score, comment_count, author, url, top_comments
    Answers: "What's this thread about? How popular is it? What do people say?"
    """

    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        html = str(input_data.get("html", ""))

        title = _extract_og(html, "title") or _extract_tag(html, "title")

        # Subreddit
        sub_m = re.search(r'href="(?:https?://[^/]+)?/r/([^/"]+)/"', html)
        subreddit = sub_m.group(1) if sub_m else ""

        # Score (upvotes)
        score_m = re.search(r'class="score[^"]*"[^>]*>(\d+)\s*(?:point|upvote)', html)
        score = int(score_m.group(1)) if score_m else 0

        # Comment count
        comment_m = re.search(r"(\d+)\s+comment", html)
        comment_count = int(comment_m.group(1)) if comment_m else 0

        # Post author
        author_m = re.search(r'class="author[^"]*"[^>]*>([^<]+)<', html)
        author = author_m.group(1).strip() if author_m else ""

        # Top-level comment texts (first 3, stripped)
        top_comments: list[str] = []
        for cm in re.finditer(
            r'class="md"[^>]*><p>(.*?)</p>', html, re.DOTALL
        ):
            text = re.sub(r"<[^>]+>", "", cm.group(1)).strip()
            if len(text) > 20 and len(top_comments) < 3:
                top_comments.append(text[:500])

        return {
            "title": title,
            "subreddit": subreddit,
            "score": score,
            "comment_count": comment_count,
            "author": author,
            "top_comments": top_comments,
        }

    def validate(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Skill: Recipe page (schema.org / standard meta patterns)
# ---------------------------------------------------------------------------


class RecipeSkill(BaseSkill):
    """Extract a recipe from a standard recipe page.

    Returns: name, description, prep_time, cook_time, servings, ingredients,
             instructions_count, calories
    Answers: "What do I need? How long does it take? How many servings?"
    Works on AllRecipes, Food Network, Epicurious, and any site using
    schema.org/Recipe JSON-LD.
    """

    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        import json as _json

        html = str(input_data.get("html", ""))

        # Try schema.org JSON-LD first — most modern recipe sites use it
        for ld_m in re.finditer(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html,
            re.DOTALL | re.IGNORECASE,
        ):
            try:
                data = _json.loads(ld_m.group(1))
                # Handle @graph arrays
                if isinstance(data, dict) and "@graph" in data:
                    data = next(
                        (
                            x for x in data["@graph"]
                            if isinstance(x, dict)
                            and "Recipe" in str(x.get("@type", ""))
                        ),
                        data,
                    )
                if isinstance(data, dict) and "Recipe" in str(data.get("@type", "")):
                    ingredients = data.get("recipeIngredient", [])
                    instructions = data.get("recipeInstructions", [])
                    nutrition = data.get("nutrition", {})
                    return {
                        "name": str(data.get("name", "")),
                        "description": str(data.get("description", ""))[:500],
                        "prep_time": str(data.get("prepTime", "")),
                        "cook_time": str(data.get("cookTime", "")),
                        "total_time": str(data.get("totalTime", "")),
                        "servings": str(data.get("recipeYield", "")),
                        "ingredients": ingredients[:30],
                        "instructions_count": len(instructions),
                        "calories": str(nutrition.get("calories", "")) if nutrition else "",
                        "rating": str(data.get("aggregateRating", {}).get("ratingValue", "")),
                    }
            except Exception:
                continue

        # Fallback: og:title + meta description
        return {
            "name": _extract_og(html, "title") or _extract_tag(html, "title"),
            "description": _extract_og(html, "description") or _extract_meta(html, "description"),
            "prep_time": "",
            "cook_time": "",
            "total_time": "",
            "servings": "",
            "ingredients": [],
            "instructions_count": 0,
            "calories": "",
            "rating": "",
        }

    def validate(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Skill: Product page (generic — Amazon, Best Buy, etc.)
# ---------------------------------------------------------------------------


class ProductPageSkill(BaseSkill):
    """Extract product information from a shopping page.

    Returns: name, price, currency, rating, review_count, availability,
             description, brand
    Answers: "How much does it cost? Is it in stock? What do buyers think?"
    Uses schema.org/Product JSON-LD when available, falls back to meta tags.
    """

    async def invoke(self, input_data: dict[str, object]) -> dict[str, object]:
        import json as _json

        html = str(input_data.get("html", ""))

        # schema.org Product JSON-LD
        for ld_m in re.finditer(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html,
            re.DOTALL | re.IGNORECASE,
        ):
            try:
                data = _json.loads(ld_m.group(1))
                if isinstance(data, dict) and "@graph" in data:
                    data = next(
                        (
                            x for x in data["@graph"]
                            if isinstance(x, dict)
                            and "Product" in str(x.get("@type", ""))
                        ),
                        data,
                    )
                if isinstance(data, dict) and "Product" in str(data.get("@type", "")):
                    offers = data.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    agg = data.get("aggregateRating", {})
                    brand_raw = data.get("brand", "")
                    brand = str(
                        brand_raw.get("name", "") if isinstance(brand_raw, dict)
                        else brand_raw
                    )
                    return {
                        "name": str(data.get("name", "")),
                        "brand": brand,
                        "description": str(data.get("description", ""))[:500],
                        "price": str(offers.get("price", "")),
                        "currency": str(offers.get("priceCurrency", "")),
                        "availability": str(offers.get("availability", "")).split("/")[-1],
                        "rating": str(agg.get("ratingValue", "")),
                        "review_count": str(agg.get("reviewCount", agg.get("ratingCount", ""))),
                    }
            except Exception:
                continue

        # Fallback: og tags + meta
        price_pattern = r'(?:og:price:amount|product:price:amount)[^>]*content="([^"]+)"'
        price_m = re.search(price_pattern, html, re.IGNORECASE)
        return {
            "name": _extract_og(html, "title") or _extract_tag(html, "title"),
            "brand": _extract_og(html, "brand") or "",
            "description": _extract_og(html, "description") or _extract_meta(html, "description"),
            "price": price_m.group(1) if price_m else _extract_og(html, "price:amount"),
            "currency": _extract_og(html, "price:currency"),
            "availability": _extract_og(html, "availability"),
            "rating": "",
            "review_count": "",
        }

    def validate(self) -> bool:
        return True
