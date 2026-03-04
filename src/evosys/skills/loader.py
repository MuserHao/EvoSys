"""Load built-in skills into a SkillRegistry."""

from __future__ import annotations

from evosys.schemas._types import ImplementationType
from evosys.schemas.skill import SkillRecord
from evosys.skills.library import (
    ArticleMetadataSkill,
    HackerNewsSkill,
    WikipediaSummarySkill,
)
from evosys.skills.registry import SkillRegistry

# (name, description, implementation_type, skill_class)
_BUILTIN_SKILLS: list[
    tuple[str, str, ImplementationType, type]
] = [
    (
        "extract:news.ycombinator.com",
        "Extract structured data from Hacker News item pages",
        ImplementationType.DETERMINISTIC,
        HackerNewsSkill,
    ),
    (
        "extract:en.wikipedia.org",
        "Extract summary data from Wikipedia article pages",
        ImplementationType.DETERMINISTIC,
        WikipediaSummarySkill,
    ),
]

# ArticleMetadataSkill is a generic fallback — registered for common
# content sites.  More domains can be added here.
_ARTICLE_DOMAINS = [
    "medium.com",
    "dev.to",
    "techcrunch.com",
    "arstechnica.com",
    "theverge.com",
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

    for domain in _ARTICLE_DOMAINS:
        name = f"extract:{domain}"
        if name in registry:
            continue
        record = SkillRecord(
            name=name,
            description=f"Extract article metadata from {domain}",
            implementation_type=ImplementationType.DETERMINISTIC,
            implementation_path="evosys.skills.library.ArticleMetadataSkill",
            test_suite_path="tests/test_skills/test_library.py",
        )
        registry.register(record, ArticleMetadataSkill())
        count += 1

    return count
