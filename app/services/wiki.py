"""Wiki service — file operations for the wiki knowledge store.

Storage layout::

    {OPENAGENTD_WIKI_DIR}/
      USER.md          # always injected into system prompt
      INDEX.md         # dream-maintained table of contents
      topics/          # durable knowledge base
        {slug}.md
      notes/           # session notes + dumps
        {date}-{session_id}.md

This module is the single source of truth for path validation, frontmatter
parsing, and tree assembly for the wiki system.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import yaml
from loguru import logger

from app.core.config import settings

# ── Layout constants ─────────────────────────────────────────────────────────

USER_FILE = "USER.md"  # wiki/USER.md — always injected
INDEX_FILE = "INDEX.md"  # wiki/INDEX.md — dream-maintained TOC
TOPICS_DIR = "topics"  # wiki/topics/{slug}.md
NOTES_DIR = "notes"  # wiki/notes/{date}.md

#: Default content for USER.md on first seed.
DEFAULT_USER_FILE = """\
# User

## Identity
(not yet known)

## Preferences
(not yet known)

## Working style
(not yet known)
"""

#: Frontmatter delimiter pattern — matches ``---\n<yaml>\n---\n`` at start of file.
_FRONTMATTER_RE = re.compile(r"^\s*---\r?\n(.*?)\r?\n---\r?\n?(.*)", re.DOTALL)


# ── Data types ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WikiFileInfo:
    """Metadata for a single wiki file surfaced in the tree view."""

    path: str  # relative to OPENAGENTD_WIKI_DIR, e.g. "topics/auth.md"
    description: str  # from frontmatter, or "" for system files
    updated: str | None  # ISO date string or None
    tags: tuple[str, ...] = ()  # from frontmatter ``tags`` list (topics only)


@dataclass
class WikiTree:
    """Structured view of the wiki store for UI and prompt injection."""

    system: list[WikiFileInfo] = field(default_factory=list)
    notes: list[WikiFileInfo] = field(default_factory=list)
    topics: list[WikiFileInfo] = field(default_factory=list)


@dataclass(frozen=True)
class WikiFileContent:
    """Raw file contents plus structural metadata."""

    path: str
    content: str
    description: str
    updated: str | None
    tags: tuple[str, ...] = ()


# ── Root resolution ──────────────────────────────────────────────────────────


def wiki_root() -> Path:
    """Return the absolute wiki root directory, creating it if missing."""
    root = Path(settings.OPENAGENTD_WIKI_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


# ── Path validation ──────────────────────────────────────────────────────────


class WikiPathError(ValueError):
    """Raised when a relative wiki path is invalid or unsafe."""


def validate_wiki_path(rel_path: str) -> Path:
    """Validate *rel_path* and return its resolved absolute path under OPENAGENTD_WIKI_DIR.

    Rules:
      - ``USER.md`` and ``INDEX.md`` are valid at root level.
      - ``topics/*.md`` valid.
      - ``notes/*.md`` valid.
      - No path traversal; must stay inside wiki root.
      - Must end in ``.md``.
    """
    if not rel_path:
        raise WikiPathError("Wiki path must not be empty.")
    if rel_path.startswith(("/", "~")):
        raise WikiPathError(f"Wiki path must be relative: {rel_path}")

    p = Path(rel_path)
    if p.is_absolute():
        raise WikiPathError(f"Wiki path must be relative: {rel_path}")

    if p.suffix != ".md":
        raise WikiPathError(f"Wiki files must be Markdown (.md): {rel_path}")

    # Reject traversal segments in the raw string before Path normalises them away.
    # Path("topics/./test.md").parts == ("topics", "test.md") — dot is silently
    # dropped, so we must check the raw string components, not p.parts.
    raw_parts = rel_path.replace("\\", "/").split("/")
    if any(part in ("..", ".") for part in raw_parts):
        raise WikiPathError(f"Wiki path may not contain '..' or '.': {rel_path}")

    parts = p.parts
    # Root-level files: USER.md and INDEX.md only
    if len(parts) == 1:
        if rel_path not in (USER_FILE, INDEX_FILE):
            raise WikiPathError(
                f"Only {USER_FILE} and {INDEX_FILE} are valid at wiki root level: {rel_path}"
            )
    elif len(parts) == 2:
        if parts[0] not in (TOPICS_DIR, NOTES_DIR):
            raise WikiPathError(
                f"Wiki subdir must be '{TOPICS_DIR}' or '{NOTES_DIR}': got {parts[0]!r}"
            )
    else:
        raise WikiPathError(f"Wiki path too deep (max 2 components): {rel_path}")

    root = wiki_root()
    candidate = root / p
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WikiPathError(f"Wiki path escapes root: {rel_path}") from exc
    return resolved


# ── Frontmatter parsing ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ParsedMarkdown:
    description: str
    updated: str | None
    tags: tuple[str, ...]
    body: str
    raw: str


def parse_frontmatter(raw: str) -> ParsedMarkdown:
    """Parse YAML frontmatter from *raw*.

    Returns a :class:`ParsedMarkdown` with empty description/updated/tags when
    no frontmatter is present.
    """
    m = _FRONTMATTER_RE.match(raw)
    if not m:
        return ParsedMarkdown(description="", updated=None, tags=(), body=raw, raw=raw)
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return ParsedMarkdown(description="", updated=None, tags=(), body=raw, raw=raw)

    description = (
        str(data.get("description", "")).strip() if isinstance(data, dict) else ""
    )
    updated_val = data.get("updated") if isinstance(data, dict) else None
    updated: str | None
    if isinstance(updated_val, (date, datetime)):
        updated = updated_val.isoformat()
    elif isinstance(updated_val, str):
        updated = updated_val.strip() or None
    else:
        updated = None

    raw_tags = data.get("tags") if isinstance(data, dict) else None
    if isinstance(raw_tags, list):
        tags: tuple[str, ...] = tuple(
            str(t).strip().lower() for t in raw_tags if str(t).strip()
        )
    else:
        tags = ()

    body = m.group(2).lstrip("\n")
    return ParsedMarkdown(
        description=description, updated=updated, tags=tags, body=body, raw=raw
    )


# ── Tree listing ─────────────────────────────────────────────────────────────


def _list_subdir(subdir: str) -> list[WikiFileInfo]:
    root = wiki_root() / subdir
    if not root.is_dir():
        return []
    infos: list[WikiFileInfo] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_file() or entry.suffix != ".md":
            continue
        rel = f"{subdir}/{entry.name}"
        try:
            raw = entry.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("wiki_read_failed path={} error={}", rel, exc)
            infos.append(WikiFileInfo(path=rel, description="", updated=None))
            continue
        parsed = parse_frontmatter(raw)
        infos.append(
            WikiFileInfo(
                path=rel,
                description=parsed.description,
                updated=parsed.updated,
                tags=parsed.tags,
            )
        )
    return infos


def list_tree(*, unprocessed_notes: set[str] | None = None) -> WikiTree:
    """Return the current wiki tree grouped by section.

    Args:
      unprocessed_notes: When provided, only notes whose filename is in this
        set are included.  Pass ``None`` (default) to include all notes.

    Returns:
      - ``system``: ``[WikiFileInfo for USER.md]`` if it exists.
      - ``topics``: files under ``topics/``.
      - ``notes``: files under ``notes/``, optionally filtered to unprocessed.
    """
    root = wiki_root()
    system: list[WikiFileInfo] = []

    for root_file in (USER_FILE, INDEX_FILE):
        path = root / root_file
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("wiki_read_failed path={} error={}", root_file, exc)
            raw = ""
        parsed = parse_frontmatter(raw)
        system.append(
            WikiFileInfo(
                path=root_file,
                description=parsed.description,
                updated=parsed.updated,
                tags=parsed.tags,
            )
        )

    all_notes = _list_subdir(NOTES_DIR)
    if unprocessed_notes is not None:
        notes = [n for n in all_notes if Path(n.path).name in unprocessed_notes]
    else:
        notes = all_notes

    return WikiTree(
        system=system,
        topics=_list_subdir(TOPICS_DIR),
        notes=notes,
    )


# ── File CRUD ────────────────────────────────────────────────────────────────


def read_file(rel_path: str) -> WikiFileContent:
    """Read a wiki file and return its raw contents + parsed metadata."""
    resolved = validate_wiki_path(rel_path)
    if not resolved.is_file():
        raise FileNotFoundError(f"Wiki file not found: {rel_path}")
    raw = resolved.read_text(encoding="utf-8")
    parsed = parse_frontmatter(raw)
    return WikiFileContent(
        path=rel_path,
        content=raw,
        description=parsed.description,
        updated=parsed.updated,
        tags=parsed.tags,
    )


def write_file(rel_path: str, content: str) -> WikiFileContent:
    """Create or overwrite a wiki file."""
    resolved = validate_wiki_path(rel_path)
    parsed = parse_frontmatter(content)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    logger.info(
        "wiki_file_written path={} bytes={}", rel_path, len(content.encode("utf-8"))
    )
    return WikiFileContent(
        path=rel_path,
        content=content,
        description=parsed.description,
        updated=parsed.updated,
        tags=parsed.tags,
    )


def delete_file(rel_path: str) -> None:
    """Delete a wiki file. USER.md and INDEX.md cannot be deleted."""
    resolved = validate_wiki_path(rel_path)
    if rel_path in (USER_FILE, INDEX_FILE):
        raise WikiPathError(
            f"Refusing to delete wiki root file: {rel_path}. "
            "Overwrite the contents instead."
        )
    if not resolved.exists():
        raise FileNotFoundError(f"Wiki file not found: {rel_path}")
    resolved.unlink()
    logger.info("wiki_file_deleted path={}", rel_path)


# ── Note helper ──────────────────────────────────────────────────────────────


def write_note(content: str) -> Path:
    """Append one note entry to ``wiki/notes/{date}.md``.

    All notes for the same day share one file. Each call appends a
    ``## HH:MM UTC`` header so entries remain readable.
    No frontmatter — plain markdown logs.

    Returns the resolved path.
    """
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%H:%M UTC")
    filename = f"{today}.md"
    root = wiki_root()
    notes_dir = root / NOTES_DIR
    notes_dir.mkdir(parents=True, exist_ok=True)
    dest = notes_dir / filename

    entry = f"## {timestamp}\n\n{content.strip()}\n"

    if dest.exists():
        existing = dest.read_text(encoding="utf-8")
        dest.write_text(existing + "\n" + entry, encoding="utf-8")
        logger.info(
            "wiki_note_appended path={} bytes={}", dest, len(content.encode("utf-8"))
        )
    else:
        dest.write_text(entry, encoding="utf-8")
        logger.info(
            "wiki_note_written path={} bytes={}", dest, len(content.encode("utf-8"))
        )
    return dest
