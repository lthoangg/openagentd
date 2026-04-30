"""Tests for the note built-in tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.tools.builtin.note import _note


@pytest.fixture(autouse=True)
def _wiki_dir(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    target = tmp_path / "wiki"
    monkeypatch.setattr(settings, "OPENAGENTD_WIKI_DIR", str(target))
    yield target


# ── Basic note creation ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_note_creates_file(_wiki_dir: Path):
    result = await _note(content="Remember: user prefers dark mode.")
    assert "Note recorded to" in result

    notes_dir = _wiki_dir / "notes"
    files = list(notes_dir.glob("*.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "Remember: user prefers dark mode." in content


@pytest.mark.asyncio
async def test_note_has_timestamp_header(_wiki_dir: Path):
    """Each entry must start with a ## HH:MM UTC header — no frontmatter."""
    await _note(content="Test note.")

    notes_dir = _wiki_dir / "notes"
    content = list(notes_dir.glob("*.md"))[0].read_text(encoding="utf-8")
    assert content.startswith("## ")
    assert "UTC" in content
    assert "---" not in content  # no YAML frontmatter


# ── Append on second call ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_note_appends_on_second_call(_wiki_dir: Path):
    """Two calls on the same day write to the same file."""
    await _note(content="First note.")
    await _note(content="Second note.")

    notes_dir = _wiki_dir / "notes"
    files = list(notes_dir.glob("*.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "First note." in content
    assert "Second note." in content


@pytest.mark.asyncio
async def test_note_appended_entries_have_separate_headers(_wiki_dir: Path):
    """Each appended entry must have its own ## timestamp header."""
    await _note(content="Alpha.")
    await _note(content="Beta.")

    notes_dir = _wiki_dir / "notes"
    content = list(notes_dir.glob("*.md"))[0].read_text(encoding="utf-8")
    # Two separate ## headers
    assert content.count("## ") == 2


# ── Return value ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_note_returns_filename(_wiki_dir: Path):
    result = await _note(content="Test note.")
    assert ".md" in result


# ── New tests for recent changes ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_note_tool_no_state_still_works(_wiki_dir: Path):
    """Calling _note(content="x") with no _state arg works fine."""
    # The function signature no longer requires _state
    result = await _note(content="Test without state.")
    assert "Note recorded to" in result
    assert ".md" in result


@pytest.mark.asyncio
async def test_note_writes_to_daily_file(_wiki_dir: Path):
    """Result filename matches today's date, no session_id suffix."""
    from datetime import datetime, timezone

    result = await _note(content="Daily note.")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert today in result
    # Verify no session_id suffix (format should be YYYY-MM-DD.md)
    assert result.endswith(f"{today}.md.")  # ends with date.md.
