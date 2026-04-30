"""Filesystem service for agent and skill ``.md`` files.

Thin wrapper around the agents and skills directories. Handles path
validation, filename derivation, and atomic writes. All paths are kept
inside the configured root directory — traversal attempts raise
``AgentFsPathError``.

Used by ``app.api.routes.agents`` and ``app.api.routes.skills``.  Validation
of YAML frontmatter happens in ``app.services.team_manager`` (agents) or
by re-parsing after write (skills).
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from app.core.config import settings


# ── Errors ───────────────────────────────────────────────────────────────────


class AgentFsPathError(ValueError):
    """Raised when a caller-supplied path escapes the managed directory."""


class AgentFsNotFoundError(FileNotFoundError):
    """Raised when the requested .md file does not exist."""


class AgentFsConflictError(ValueError):
    """Raised when a create would overwrite an existing file."""


# ── Validation ───────────────────────────────────────────────────────────────

_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")


def _validate_name(name: str) -> str:
    """Reject names that would escape the directory or break YAML parsing."""
    if not name or not _NAME_RE.match(name):
        raise AgentFsPathError(
            f"Invalid name '{name}'. Use letters, digits, '.', '_', '-' only "
            "(1-64 chars, must start with letter/digit)."
        )
    return name


# ── Paths ────────────────────────────────────────────────────────────────────


def agents_dir() -> Path:
    return Path(settings.AGENTS_DIR).resolve()


def skills_dir() -> Path:
    return Path(settings.SKILLS_DIR).resolve()


def _agent_file(name: str) -> Path:
    root = agents_dir()
    file = (root / f"{_validate_name(name)}.md").resolve()
    if not file.is_relative_to(root):
        raise AgentFsPathError(f"Path escapes agents directory: '{name}'.")
    return file


def _skill_file(name: str) -> Path:
    root = skills_dir()
    file = (root / _validate_name(name) / "SKILL.md").resolve()
    if not file.is_relative_to(root):
        raise AgentFsPathError(f"Path escapes skills directory: '{name}'.")
    return file


# ── Atomic write ─────────────────────────────────────────────────────────────


def _atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* atomically (tmp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


# ── Public dataclasses ───────────────────────────────────────────────────────


@dataclass
class AgentFileRecord:
    """On-disk representation of an agent .md file."""

    name: str
    path: str  # absolute path
    content: str  # raw file text (frontmatter + body)


@dataclass
class SkillFileRecord:
    """On-disk representation of a skill SKILL.md file."""

    name: str
    path: str
    content: str


# ── Agents ───────────────────────────────────────────────────────────────────


def list_agents() -> list[str]:
    """Return the list of agent names (stem of each .md file)."""
    root = agents_dir()
    if not root.exists():
        return []
    return sorted(p.stem for p in root.glob("*.md"))


def read_agent(name: str) -> AgentFileRecord:
    file = _agent_file(name)
    if not file.is_file():
        raise AgentFsNotFoundError(f"Agent '{name}' not found.")
    return AgentFileRecord(
        name=name, path=str(file), content=file.read_text(encoding="utf-8")
    )


def write_agent(name: str, content: str, *, create: bool) -> AgentFileRecord:
    """Write an agent .md file. Set *create* = True to require the file not
    already exist (POST semantics); False to allow overwrite (PUT semantics).
    """
    file = _agent_file(name)
    if create and file.exists():
        raise AgentFsConflictError(f"Agent '{name}' already exists.")
    _atomic_write(file, content)
    logger.info("agent_fs_write name={} bytes={}", name, len(content))
    return AgentFileRecord(name=name, path=str(file), content=content)


def delete_agent(name: str) -> None:
    file = _agent_file(name)
    if not file.is_file():
        raise AgentFsNotFoundError(f"Agent '{name}' not found.")
    file.unlink()
    logger.info("agent_fs_delete name={}", name)


# ── Skills ───────────────────────────────────────────────────────────────────


def list_skills() -> list[str]:
    """Return the list of skill names — directories containing SKILL.md."""
    root = skills_dir()
    if not root.exists():
        return []
    return sorted(
        p.name for p in root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()
    )


def read_skill(name: str) -> SkillFileRecord:
    file = _skill_file(name)
    if not file.is_file():
        raise AgentFsNotFoundError(f"Skill '{name}' not found.")
    return SkillFileRecord(
        name=name, path=str(file), content=file.read_text(encoding="utf-8")
    )


def write_skill(name: str, content: str, *, create: bool) -> SkillFileRecord:
    file = _skill_file(name)
    if create and file.exists():
        raise AgentFsConflictError(f"Skill '{name}' already exists.")
    _atomic_write(file, content)
    logger.info("skill_fs_write name={} bytes={}", name, len(content))
    return SkillFileRecord(name=name, path=str(file), content=content)


def delete_skill(name: str) -> None:
    file = _skill_file(name)
    if not file.is_file():
        raise AgentFsNotFoundError(f"Skill '{name}' not found.")
    file.unlink()
    # Remove the now-empty skill directory if nothing else sits alongside it.
    try:
        file.parent.rmdir()
    except OSError:
        # Directory not empty (e.g. reference/, scripts/) — leave it.
        pass
    logger.info("skill_fs_delete name={}", name)
