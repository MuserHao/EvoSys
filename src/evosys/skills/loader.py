"""Load built-in skills into a SkillRegistry."""

from __future__ import annotations

from evosys.schemas._types import ImplementationType
from evosys.schemas.skill import SkillRecord
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
from evosys.skills.registry import SkillRegistry

# ---------------------------------------------------------------------------
# Domain-specific skills (precise parsers for well-known sites)
# ---------------------------------------------------------------------------

_BUILTIN_SKILLS: list[tuple[str, str, ImplementationType, type]] = [
    (
        "extract:news.ycombinator.com",
        "Extract title, score, author, and comment count from a Hacker News item page",
        ImplementationType.DETERMINISTIC,
        HackerNewsSkill,
    ),
    (
        "extract:en.wikipedia.org",
        "Extract title, first paragraph, categories, and last-edited date from Wikipedia",
        ImplementationType.DETERMINISTIC,
        WikipediaSummarySkill,
    ),
    (
        "extract:github.com",
        "Extract repo name, description, language, stars, forks, license, and topics from GitHub",
        ImplementationType.DETERMINISTIC,
        GitHubRepoSkill,
    ),
    (
        "extract:arxiv.org",
        "Extract title, authors, abstract, submission date, and subjects from an arXiv paper page",
        ImplementationType.DETERMINISTIC,
        ArxivPaperSkill,
    ),
    (
        "extract:old.reddit.com",
        "Extract title, subreddit, score, comment count, and top comments from a Reddit thread",
        ImplementationType.DETERMINISTIC,
        RedditThreadSkill,
    ),
    (
        "extract:www.reddit.com",
        "Extract title, subreddit, score, comment count, and top comments from a Reddit thread",
        ImplementationType.DETERMINISTIC,
        RedditThreadSkill,
    ),
]

# ---------------------------------------------------------------------------
# Recipe sites — schema.org/Recipe JSON-LD works on all of these
# ---------------------------------------------------------------------------

_RECIPE_DOMAINS = [
    "www.allrecipes.com",
    "www.foodnetwork.com",
    "www.epicurious.com",
    "www.seriouseats.com",
    "www.bonappetit.com",
    "tasty.co",
    "www.bbcgoodfood.com",
    "www.simplyrecipes.com",
]

# ---------------------------------------------------------------------------
# Shopping / product sites — schema.org/Product JSON-LD
# ---------------------------------------------------------------------------

_PRODUCT_DOMAINS = [
    "www.amazon.com",
    "www.bestbuy.com",
    "www.target.com",
    "www.walmart.com",
    "www.newegg.com",
    "www.bhphotovideo.com",
]

# ---------------------------------------------------------------------------
# General article / news sites — og: + meta tag extraction
# ---------------------------------------------------------------------------

_ARTICLE_DOMAINS = [
    "medium.com",
    "dev.to",
    "techcrunch.com",
    "arstechnica.com",
    "theverge.com",
    "wired.com",
    "www.bbc.com",
    "www.nytimes.com",
    "www.theguardian.com",
    "news.yahoo.com",
    "www.reuters.com",
    "apnews.com",
    "www.wsj.com",
    "www.bloomberg.com",
]


def register_builtin_skills(registry: SkillRegistry) -> int:
    """Register all built-in skills and return the count registered.

    Skips any skill whose name is already taken (allows user overrides).
    """
    count = 0

    for name, description, impl_type, cls in _BUILTIN_SKILLS:
        if name in registry:
            continue
        record = SkillRecord(
            name=name,
            description=description,
            implementation_type=impl_type,
            implementation_path=f"evosys.skills.library.{cls.__name__}",
            test_suite_path="tests/test_skills/test_library.py",
        )
        registry.register(record, cls())
        count += 1

    for domain in _RECIPE_DOMAINS:
        name = f"extract:{domain}"
        if name in registry:
            continue
        record = SkillRecord(
            name=name,
            description=f"Extract recipe name, ingredients, times, and nutrition from {domain}",
            implementation_type=ImplementationType.DETERMINISTIC,
            implementation_path="evosys.skills.library.RecipeSkill",
            test_suite_path="tests/test_skills/test_library.py",
        )
        registry.register(record, RecipeSkill())
        count += 1

    for domain in _PRODUCT_DOMAINS:
        name = f"extract:{domain}"
        if name in registry:
            continue
        record = SkillRecord(
            name=name,
            description=f"Extract product name, price, rating, and availability from {domain}",
            implementation_type=ImplementationType.DETERMINISTIC,
            implementation_path="evosys.skills.library.ProductPageSkill",
            test_suite_path="tests/test_skills/test_library.py",
        )
        registry.register(record, ProductPageSkill())
        count += 1

    for domain in _ARTICLE_DOMAINS:
        name = f"extract:{domain}"
        if name in registry:
            continue
        record = SkillRecord(
            name=name,
            description=(
                f"Extract article title, description, author, and publication date"
                f" from {domain}"
            ),
            implementation_type=ImplementationType.DETERMINISTIC,
            implementation_path="evosys.skills.library.ArticleMetadataSkill",
            test_suite_path="tests/test_skills/test_library.py",
        )
        registry.register(record, ArticleMetadataSkill())
        count += 1

    return count
