"""Tests for app/tools/builtin/skill.py."""

from __future__ import annotations

import pytest

from app.agent.tools.builtin.skill import (
    _parse_frontmatter,
    discover_skills,
    load_skill,
)


# ---------------------------------------------------------------------------
# _parse_frontmatter
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_with_frontmatter(self):
        text = "---\nname: test\ndescription: A test skill\n---\nBody content here."
        meta, body = _parse_frontmatter(text)
        assert meta["name"] == "test"
        assert meta["description"] == "A test skill"
        assert body == "Body content here."

    def test_no_frontmatter(self):
        text = "Just plain markdown body."
        meta, body = _parse_frontmatter(text)
        assert meta == {}
        assert body == "Just plain markdown body."

    def test_empty_frontmatter(self):
        text = "---\n\n---\nBody after empty frontmatter."
        meta, body = _parse_frontmatter(text)
        assert meta == {}
        assert body == "Body after empty frontmatter."


# ---------------------------------------------------------------------------
# discover_skills
# ---------------------------------------------------------------------------


class TestDiscoverSkills:
    def test_discover_skills_from_dir(self, tmp_path):
        skill_dir = tmp_path / "web-research"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: web-research\ndescription: Research the web\n---\nInstructions."
        )
        result = discover_skills(skills_dir=tmp_path)
        assert "web-research" in result
        assert result["web-research"]["description"] == "Research the web"
        assert result["web-research"]["file"] == "web-research/SKILL.md"

    def test_discover_skills_empty_dir(self, tmp_path):
        result = discover_skills(skills_dir=tmp_path)
        assert result == {}

    def test_discover_skills_missing_dir(self, tmp_path):
        result = discover_skills(skills_dir=tmp_path / "nonexistent")
        assert result == {}

    def test_discover_skills_name_from_stem(self, tmp_path):
        """If frontmatter has no name, fall back to the subdirectory name."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\ndescription: desc\n---\nBody.")
        result = discover_skills(skills_dir=tmp_path)
        assert "my-skill" in result

    def test_discover_multiple_skills(self, tmp_path):
        for name, body in [("alpha", "A instructions."), ("beta", "B instructions.")]:
            d = tmp_path / name
            d.mkdir()
            (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n{body}")
        result = discover_skills(skills_dir=tmp_path)
        assert len(result) == 2
        assert "alpha" in result
        assert "beta" in result

    def test_subdir_without_skill_md_is_ignored(self, tmp_path):
        """A subdirectory that has no SKILL.md must not appear in results."""
        orphan = tmp_path / "orphan"
        orphan.mkdir()
        (orphan / "notes.md").write_text("not a skill")
        result = discover_skills(skills_dir=tmp_path)
        assert result == {}


# ---------------------------------------------------------------------------
# load_skill
# ---------------------------------------------------------------------------


class TestLoadSkill:
    @pytest.mark.asyncio
    async def test_load_skill_by_name(self, tmp_path, monkeypatch):
        d = tmp_path / "analysis"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: analysis\n---\nAnalyse data carefully.")
        monkeypatch.setattr("app.agent.tools.builtin.skill._SKILLS_DIR", tmp_path)
        result = await load_skill("analysis")
        assert result == "Analyse data carefully."

    @pytest.mark.asyncio
    async def test_load_skill_by_subdir_name(self, tmp_path, monkeypatch):
        """Match by subdirectory name when frontmatter name differs."""
        d = tmp_path / "my-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: different-name\n---\nBody content.")
        monkeypatch.setattr("app.agent.tools.builtin.skill._SKILLS_DIR", tmp_path)
        result = await load_skill("my-skill")
        assert result == "Body content."

    @pytest.mark.asyncio
    async def test_load_skill_not_found(self, tmp_path, monkeypatch):
        d = tmp_path / "existing"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: existing\n---\nBody.")
        monkeypatch.setattr("app.agent.tools.builtin.skill._SKILLS_DIR", tmp_path)
        result = await load_skill("nonexistent")
        assert "not found" in result
        assert "existing" in result

    @pytest.mark.asyncio
    async def test_load_skill_dir_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.agent.tools.builtin.skill._SKILLS_DIR",
            tmp_path / "gone",
        )
        result = await load_skill("anything")
        assert "Skills directory not found" in result


# ---------------------------------------------------------------------------
# Path-token substitution
#
# The skill tool replaces a small whitelist of ``{TOKEN}`` placeholders in
# both the discovered description (which gets injected into the agent's
# system prompt) and the body returned by ``load_skill``. This is what
# lets a skill say ``cat {OPENAGENTD_CONFIG_DIR}/mcp.json`` and have the
# agent receive a concrete absolute path it can hand to its file/shell
# tools without further interpretation.
#
# We invalidate the lru-cached discovery between tests because the cache
# key is the directory path, and ``_render_tokens`` reads ``settings``
# fresh on each call — but the cache hit would short-circuit that.
# ---------------------------------------------------------------------------


class TestTokenSubstitution:
    @pytest.fixture(autouse=True)
    def _clear_skill_cache(self):
        from app.agent.tools.builtin.skill import _discover_skills_cached

        _discover_skills_cached.cache_clear()
        yield
        _discover_skills_cached.cache_clear()

    def test_description_tokens_replaced_in_discovery(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.OPENAGENTD_CONFIG_DIR", "/x/cfg")
        d = tmp_path / "demo"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: demo\ndescription: edits {OPENAGENTD_CONFIG_DIR}/mcp.json\n---\nBody."
        )

        result = discover_skills(skills_dir=tmp_path)

        # The literal placeholder must NOT survive into what the LLM sees.
        assert result["demo"]["description"] == "edits /x/cfg/mcp.json"
        # The new ``dir`` field exposes the skill's absolute directory
        # so callers don't need a second filesystem walk.
        assert result["demo"]["dir"] == str(d)

    def test_unknown_braces_in_description_preserved(self, tmp_path):
        """Anything not in the recognised whitelist (e.g. format-string
        placeholders in a description) must round-trip unchanged."""
        d = tmp_path / "demo"
        d.mkdir()
        # Quoted YAML scalar so the colon inside braces doesn't trip
        # the parser. ``{NOT_A_TOKEN}`` is what we actually want to test.
        (d / "SKILL.md").write_text(
            '---\nname: demo\ndescription: "see {NOT_A_TOKEN} for details"\n---\nBody.'
        )

        result = discover_skills(skills_dir=tmp_path)
        assert result["demo"]["description"] == "see {NOT_A_TOKEN} for details"

    @pytest.mark.asyncio
    async def test_body_tokens_replaced_on_load(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.OPENAGENTD_CONFIG_DIR", "/x/cfg")
        monkeypatch.setattr("app.core.config.settings.AGENTS_DIR", "/x/cfg/agents")
        monkeypatch.setattr("app.core.config.settings.SKILLS_DIR", "/x/cfg/skills")
        d = tmp_path / "mcp-installer"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: mcp-installer\n---\n"
            "Edit {OPENAGENTD_CONFIG_DIR}/mcp.json. "
            "Agents live under {AGENTS_DIR}. "
            "Other skills under {SKILLS_DIR}. "
            "Run {SKILL_DIR}/scripts/mcp.py."
        )
        monkeypatch.setattr("app.agent.tools.builtin.skill._SKILLS_DIR", tmp_path)

        body = await load_skill("mcp-installer")

        assert "{OPENAGENTD_CONFIG_DIR}" not in body
        assert "{AGENTS_DIR}" not in body
        assert "{SKILLS_DIR}" not in body
        assert "{SKILL_DIR}" not in body
        assert "/x/cfg/mcp.json" in body
        assert "/x/cfg/agents" in body
        assert "/x/cfg/skills" in body
        # SKILL_DIR resolves to this skill's absolute directory.
        assert str(d.resolve()) in body

    @pytest.mark.asyncio
    async def test_body_unknown_braces_preserved(self, tmp_path, monkeypatch):
        """JSON examples and other ``{...}`` content inside the body must
        survive substitution untouched — only the four whitelisted token
        names are replaced."""
        d = tmp_path / "demo"
        d.mkdir()
        body_text = (
            'Use this payload: {"servers": {"name": "x"}}\n'
            "And refer to {NOT_A_TOKEN} for context."
        )
        (d / "SKILL.md").write_text(f"---\nname: demo\n---\n{body_text}")
        monkeypatch.setattr("app.agent.tools.builtin.skill._SKILLS_DIR", tmp_path)

        body = await load_skill("demo")
        assert body == body_text
