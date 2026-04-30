"""Skill loader tool — lets agents dynamically load skill instructions.

Skills live in the ``skills/`` directory at the project root using the
directory layout ``skills/{skill_name}/SKILL.md``.  Each ``SKILL.md``
has YAML frontmatter (name, description) followed by a markdown body.
Extra files (e.g. ``creating.md``, ``reference/``) may sit alongside
``SKILL.md`` for the agent to read separately via file tools.

The ``load_skill`` tool reads the skill file and returns its content
so the LLM can apply the instructions in subsequent reasoning.
"""

from __future__ import annotations

import asyncio
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import yaml

from loguru import logger
from pydantic import Field

from app.agent.tools.registry import tool


def _default_skills_dir() -> Path:
    from app.core.config import settings

    return Path(settings.SKILLS_DIR)


_SKILLS_DIR: Path = _default_skills_dir()


def _render_tokens(text: str, *, skill_dir: Path | None = None) -> str:
    """Replace ``{OPENAGENTD_CONFIG_DIR}`` / ``{SKILLS_DIR}`` / ``{AGENTS_DIR}`` /
    ``{SKILL_DIR}`` placeholders so the agent sees concrete paths it can
    hand straight to its file and shell tools.

    Only the four names below are substituted — anything else inside
    braces (JSON examples, format strings) is left untouched.
    """
    if not text:
        return text
    # Lazy import matches the existing convention in this module
    # (see ``_default_skills_dir``) — builtin tools avoid pulling
    # ``settings`` at import time.
    from app.core.config import settings

    tokens = {
        "OPENAGENTD_CONFIG_DIR": settings.OPENAGENTD_CONFIG_DIR,
        "AGENTS_DIR": settings.AGENTS_DIR,
        "SKILLS_DIR": settings.SKILLS_DIR,
    }
    if skill_dir is not None:
        tokens["SKILL_DIR"] = str(skill_dir.resolve())
    for name, value in tokens.items():
        text = text.replace("{" + name + "}", value)
    return text


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from markdown body.

    Returns ``(metadata_dict, body_str)``.  If no frontmatter is
    found, metadata is empty and body is the full text.
    """
    match = re.match(
        r"^---\s*\n(.*?)\n---\s*\n(.*)$",
        text,
        re.DOTALL,
    )
    if not match:
        return {}, text.strip()
    meta = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).strip()
    return meta, body


def discover_skills(
    skills_dir: Path | None = None,
) -> dict[str, dict]:
    """Discover all available skills and their metadata.

    Returns a dict mapping skill name → metadata dict.
    Uses cached version for default skills dir (avoids filesystem walk per request).
    """
    directory = skills_dir or _SKILLS_DIR
    return _discover_skills_cached(str(directory))


@lru_cache(maxsize=4)
def _discover_skills_cached(directory_str: str) -> dict[str, dict]:
    """Me cache by dir path — files no change at runtime."""
    return _discover_skills_uncached(Path(directory_str))


def _iter_skill_paths(directory: Path):
    """Yield (skill_file_path, stem) for all skills in *directory*.

    Only the directory layout is supported: ``skills/{name}/SKILL.md``.
    """
    for subdir in sorted(p for p in directory.iterdir() if p.is_dir()):
        skill_file = subdir / "SKILL.md"
        if skill_file.is_file():
            yield skill_file, subdir.name


def _discover_skills_uncached(directory: Path) -> dict[str, dict]:
    """Walk directory and parse skill frontmatter."""
    if not directory.is_dir():
        return {}

    skills: dict[str, dict] = {}
    for path, stem in _iter_skill_paths(directory):
        text = path.read_text(encoding="utf-8")
        meta, _ = _parse_frontmatter(text)
        name = meta.get("name", stem)
        # Substitute path tokens in description so the skill list shown
        # to the agent ("## Available skills" section) renders concrete
        # paths instead of literal {OPENAGENTD_CONFIG_DIR}/etc placeholders.
        description = _render_tokens(meta.get("description", ""), skill_dir=path.parent)
        skills[name] = {
            "name": name,
            "description": description,
            "file": str(path.relative_to(directory)),
            # Absolute path to the skill's directory — needed by callers
            # that want to render {SKILL_DIR} in the body without a
            # second filesystem walk.
            "dir": str(path.parent),
        }
    return skills


@tool(name="skill")
async def load_skill(
    skill_name: Annotated[
        str,
        Field(
            description="Skill name as listed in Available Skills (e.g. 'web-research')."
        ),
    ],
) -> str:
    """Load skill instructions into context. Call before starting skill-matched work."""
    skills_dir = _SKILLS_DIR
    if not skills_dir.is_dir():
        return "Skills directory not found."

    for path, stem in _iter_skill_paths(skills_dir):
        text = await asyncio.to_thread(path.read_text, encoding="utf-8")
        meta, body = _parse_frontmatter(text)
        name = meta.get("name", stem)
        if name == skill_name or stem == skill_name:
            rel = path.relative_to(skills_dir)
            logger.info("skill_loaded name={} file={}", name, rel)
            # Expand placeholders ({OPENAGENTD_CONFIG_DIR}, {SKILL_DIR}, etc.)
            # so the agent receives concrete paths it can hand to its
            # file/shell tools without further interpretation.
            return _render_tokens(body, skill_dir=path.parent)

    available = list(discover_skills(skills_dir).keys())
    return f"Skill '{skill_name}' not found. Available: {available}"
