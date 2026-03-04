"""Tests for skill loader."""

from __future__ import annotations

from evosys.skills.loader import register_builtin_skills
from evosys.skills.registry import SkillRegistry


class TestRegisterBuiltinSkills:
    def test_registers_skills(self):
        reg = SkillRegistry()
        count = register_builtin_skills(reg)
        assert count > 0
        assert len(reg) == count

    def test_includes_hackernews(self):
        reg = SkillRegistry()
        register_builtin_skills(reg)
        assert "extract:news.ycombinator.com" in reg

    def test_includes_wikipedia(self):
        reg = SkillRegistry()
        register_builtin_skills(reg)
        assert "extract:en.wikipedia.org" in reg

    def test_includes_article_domains(self):
        reg = SkillRegistry()
        register_builtin_skills(reg)
        assert "extract:medium.com" in reg
        assert "extract:techcrunch.com" in reg

    def test_skips_already_registered(self):
        reg = SkillRegistry()
        first = register_builtin_skills(reg)
        second = register_builtin_skills(reg)
        assert second == 0
        assert len(reg) == first

    def test_all_skills_are_active(self):
        reg = SkillRegistry()
        register_builtin_skills(reg)
        active = reg.list_active()
        assert len(active) == len(reg)
