"""Tests for the wiki service."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.wiki import (
    DEFAULT_USER_FILE,
    INDEX_FILE,
    NOTES_DIR,
    TOPICS_DIR,
    USER_FILE,
    WikiPathError,
    WikiTree,
    list_tree,
    parse_frontmatter,
    read_file,
    validate_wiki_path,
    wiki_root,
    write_file,
    write_note,
)


@pytest.fixture(autouse=True)
def _wiki_dir(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    target = tmp_path / "wiki"
    target.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "OPENAGENTD_WIKI_DIR", str(target))
    yield target


# ── wiki_root ─────────────────────────────────────────────────────────────────


def test_wiki_root_creates_dir(_wiki_dir: Path):
    root = wiki_root()
    assert root.exists()
    assert root.is_dir()


# ── validate_wiki_path ────────────────────────────────────────────────────────


def test_validate_user_md(_wiki_dir: Path):
    path = validate_wiki_path(USER_FILE)
    assert path.name == USER_FILE


def test_validate_index_md(_wiki_dir: Path):
    path = validate_wiki_path(INDEX_FILE)
    assert path.name == INDEX_FILE


def test_validate_topics_file(_wiki_dir: Path):
    path = validate_wiki_path("topics/auth.md")
    assert path.name == "auth.md"


def test_validate_notes_file(_wiki_dir: Path):
    path = validate_wiki_path("notes/2026-04-29-abc.md")
    assert path.name == "2026-04-29-abc.md"


def test_validate_rejects_traversal(_wiki_dir: Path):
    with pytest.raises(WikiPathError):
        validate_wiki_path("topics/../USER.md")


def test_validate_rejects_non_md(_wiki_dir: Path):
    with pytest.raises(WikiPathError):
        validate_wiki_path("topics/auth.txt")


def test_validate_rejects_unknown_root_file(_wiki_dir: Path):
    with pytest.raises(WikiPathError):
        validate_wiki_path("random.md")


def test_validate_rejects_unknown_subdir(_wiki_dir: Path):
    with pytest.raises(WikiPathError):
        validate_wiki_path("system/user.md")


# ── parse_frontmatter ─────────────────────────────────────────────────────────


def test_parse_frontmatter_with_yaml():
    raw = "---\ndescription: Test topic\ntags: [a, b]\nupdated: 2026-04-17\n---\n\nBody here.\n"
    parsed = parse_frontmatter(raw)
    assert parsed.description == "Test topic"
    assert parsed.tags == ("a", "b")
    assert parsed.updated == "2026-04-17"
    assert "Body here." in parsed.body


def test_parse_frontmatter_no_yaml():
    raw = "# Just a heading\n\nNo frontmatter.\n"
    parsed = parse_frontmatter(raw)
    assert parsed.description == ""
    assert parsed.tags == ()
    assert parsed.updated is None


# ── list_tree ─────────────────────────────────────────────────────────────────


def test_list_tree_empty(_wiki_dir: Path):
    tree = list_tree()
    assert isinstance(tree, WikiTree)
    assert tree.system == []
    assert tree.topics == []
    assert tree.notes == []


def test_list_tree_with_user_md(_wiki_dir: Path):
    (_wiki_dir / USER_FILE).write_text("# User\n", encoding="utf-8")
    tree = list_tree()
    assert len(tree.system) == 1
    assert tree.system[0].path == USER_FILE


def test_list_tree_with_topics(_wiki_dir: Path):
    topics_dir = _wiki_dir / TOPICS_DIR
    topics_dir.mkdir(parents=True, exist_ok=True)
    (topics_dir / "auth.md").write_text(
        "---\ndescription: Auth topic\ntags: [auth]\nupdated: 2026-04-17\n---\nbody\n",
        encoding="utf-8",
    )
    tree = list_tree()
    assert len(tree.topics) == 1
    assert tree.topics[0].path == "topics/auth.md"
    assert tree.topics[0].description == "Auth topic"


def test_list_tree_with_notes(_wiki_dir: Path):
    notes_dir = _wiki_dir / NOTES_DIR
    notes_dir.mkdir(parents=True, exist_ok=True)
    (notes_dir / "2026-04-29-abc.md").write_text("Note content.\n", encoding="utf-8")
    tree = list_tree()
    assert len(tree.notes) == 1
    assert tree.notes[0].path == "notes/2026-04-29-abc.md"


# ── read_file / write_file ────────────────────────────────────────────────────


def test_write_and_read_topic(_wiki_dir: Path):
    (_wiki_dir / TOPICS_DIR).mkdir(parents=True, exist_ok=True)
    content = "---\ndescription: Auth\ntags: []\nupdated: 2026-04-17\n---\nbody\n"
    write_file("topics/auth.md", content)
    result = read_file("topics/auth.md")
    assert result.content == content
    assert result.description == "Auth"


def test_write_user_md(_wiki_dir: Path):
    write_file(USER_FILE, "# User\n\n## Identity\nHoang.\n")
    result = read_file(USER_FILE)
    assert "Hoang." in result.content


def test_read_nonexistent_raises(_wiki_dir: Path):
    (_wiki_dir / TOPICS_DIR).mkdir(parents=True, exist_ok=True)
    with pytest.raises(FileNotFoundError):
        read_file("topics/missing.md")


# ── write_note ────────────────────────────────────────────────────────────────


def test_write_note_creates_file(_wiki_dir: Path):
    path = write_note("My note content.")
    assert path.exists()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert path.name == f"{today}.md"
    content = path.read_text(encoding="utf-8")
    assert "My note content." in content
    assert content.startswith("## ")
    assert "UTC" in content
    assert "---" not in content


def test_write_note_appends(_wiki_dir: Path):
    write_note("First.")
    write_note("Second.")
    notes_dir = _wiki_dir / NOTES_DIR
    files = list(notes_dir.glob("*.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "First." in content
    assert "Second." in content


def test_default_user_file_content():
    assert "## Identity" in DEFAULT_USER_FILE
    assert "## Preferences" in DEFAULT_USER_FILE
    assert "## Working style" in DEFAULT_USER_FILE


# ── New tests for recent changes ──────────────────────────────────────────────


def test_list_tree_includes_index_md(_wiki_dir: Path):
    """list_tree includes both USER.md and INDEX.md in system section."""
    (_wiki_dir / USER_FILE).write_text("# User\n", encoding="utf-8")
    (_wiki_dir / INDEX_FILE).write_text("# Index\n", encoding="utf-8")
    tree = list_tree()
    assert len(tree.system) == 2
    paths = [f.path for f in tree.system]
    assert USER_FILE in paths
    assert INDEX_FILE in paths


def test_list_tree_system_order(_wiki_dir: Path):
    """USER.md comes before INDEX.md in system list."""
    (_wiki_dir / USER_FILE).write_text("# User\n", encoding="utf-8")
    (_wiki_dir / INDEX_FILE).write_text("# Index\n", encoding="utf-8")
    tree = list_tree()
    assert len(tree.system) == 2
    assert tree.system[0].path == USER_FILE
    assert tree.system[1].path == INDEX_FILE


def test_delete_index_md_raises(_wiki_dir: Path):
    """delete_file('INDEX.md') raises WikiPathError."""
    from app.services.wiki import delete_file

    (_wiki_dir / INDEX_FILE).write_text("# Index\n", encoding="utf-8")
    with pytest.raises(WikiPathError, match="Refusing to delete wiki root file"):
        delete_file(INDEX_FILE)


def test_write_file_tags_in_content(_wiki_dir: Path):
    """write_file returns WikiFileContent with correct tags tuple from frontmatter."""
    (_wiki_dir / TOPICS_DIR).mkdir(parents=True, exist_ok=True)
    content = "---\ndescription: Auth topic\ntags: [auth, security, oauth]\nupdated: 2026-04-17\n---\nbody\n"
    result = write_file("topics/auth.md", content)
    assert result.tags == ("auth", "security", "oauth")
    assert result.description == "Auth topic"


def test_write_note_no_session_id(_wiki_dir: Path):
    """write_note(content) creates {date}.md without session_id in filename."""
    path = write_note("Test content.")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert path.name == f"{today}.md"
    # Verify no session_id suffix
    assert "-" not in path.name.replace("-", "").replace(".md", "")  # only date dashes


def test_write_note_multiple_sessions_same_file(_wiki_dir: Path):
    """Calling write_note twice (simulating two sessions) appends to same daily file."""
    path1 = write_note("Session 1 note.")
    path2 = write_note("Session 2 note.")
    # Both should write to the same file
    assert path1 == path2
    content = path1.read_text(encoding="utf-8")
    assert "Session 1 note." in content
    assert "Session 2 note." in content
    # Verify two separate timestamp headers
    assert content.count("## ") == 2
