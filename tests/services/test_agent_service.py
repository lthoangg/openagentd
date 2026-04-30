"""Tests for app.services.agent_service — attachment validation + dispatch."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent_service import (
    GLOBAL_SIZE_LIMIT,
    AttachmentError,
    NoTeamConfigured,
    RawAttachment,
    _default_ext,
    _validate_ext_mime_consistency,
    _validate_magic_bytes,
    categorize,
    dispatch_user_message,
    interrupt_team,
    require_team,
    validate_and_persist_attachments,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_team(*, vision: bool = True, document_text: bool = True) -> MagicMock:
    """Build a minimal AgentTeam stub."""
    caps = MagicMock()
    caps.input.vision = vision
    caps.input.document_text = document_text

    agent = MagicMock()
    agent.capabilities = caps

    lead = MagicMock()
    lead.agent = agent

    team = MagicMock()
    team.lead = lead
    team.handle_user_message = AsyncMock()
    return team


# ── AttachmentError ───────────────────────────────────────────────────────────


def test_attachment_error_stores_status():
    err = AttachmentError("too big", status=413)
    assert str(err) == "too big"
    assert err.status == 413


def test_attachment_error_default_is_not_overridden():
    # Each status is an explicit choice by the caller — make sure it round-trips.
    for code in (400, 413, 415, 422):
        assert AttachmentError("x", status=code).status == code


# ── require_team ──────────────────────────────────────────────────────────────


def test_require_team_returns_team():
    team = _make_team()
    assert require_team(team) is team


def test_require_team_raises_when_none():
    with pytest.raises(NoTeamConfigured):
        require_team(None)


# ── categorize ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "filename,content_type,expected",
    [
        ("photo.jpg", "image/jpeg", "image"),
        ("doc.pdf", "application/pdf", "document"),
        ("notes.txt", "text/plain", "text"),
        # Extension fallback when MIME is absent
        ("data.csv", None, "text"),
        ("report.docx", None, "document"),
        ("pic.png", None, "image"),
        # Extension fallback when MIME is unrecognised
        ("file.md", "application/octet-stream", "text"),
        # Unknown extension → None
        ("binary.exe", None, None),
        ("noext", "application/octet-stream", None),
    ],
)
def test_categorize(filename, content_type, expected):
    assert categorize(filename, content_type) == expected


def test_categorize_mime_wins_over_extension():
    # MIME takes priority when recognised
    assert categorize("file.txt", "image/png") == "image"


# ── _validate_magic_bytes ─────────────────────────────────────────────────────


def test_magic_bytes_jpeg_valid():
    data = b"\xff\xd8\xff" + b"\x00" * 100
    assert _validate_magic_bytes(data, "image/jpeg") is True


def test_magic_bytes_jpeg_invalid():
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # PNG header, claimed as JPEG
    assert _validate_magic_bytes(data, "image/jpeg") is False


def test_magic_bytes_png_valid():
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    assert _validate_magic_bytes(data, "image/png") is True


def test_magic_bytes_pdf_valid():
    data = b"%PDF-1.4 ..." + b"\x00" * 50
    assert _validate_magic_bytes(data, "application/pdf") is True


def test_magic_bytes_unknown_mime_passes():
    # No signatures registered → always passes (don't block unknown types)
    assert _validate_magic_bytes(b"\x00\x01\x02", "text/plain") is True


def test_magic_bytes_gif_valid():
    data = b"GIF89a" + b"\x00" * 20
    assert _validate_magic_bytes(data, "image/gif") is True


# ── _validate_ext_mime_consistency ────────────────────────────────────────────


def test_ext_mime_consistent():
    assert _validate_ext_mime_consistency("photo.jpg", "image/jpeg") is True


def test_ext_mime_inconsistent():
    # .jpg extension but PDF MIME
    assert _validate_ext_mime_consistency("photo.jpg", "application/pdf") is False


def test_ext_mime_unknown_ext_passes():
    # Unknown extension → we can't validate, so pass through
    assert _validate_ext_mime_consistency("file.xyz", "image/png") is True


def test_ext_mime_unknown_mime_passes():
    assert _validate_ext_mime_consistency("file.jpg", "application/unknown") is True


# ── _default_ext ─────────────────────────────────────────────────────────────


def test_default_ext_known_categories():
    assert _default_ext("text") == ".txt"
    assert _default_ext("image") == ".jpg"
    assert _default_ext("document") == ".pdf"


def test_default_ext_unknown_category_returns_bin():
    assert _default_ext("video") == ".bin"
    assert _default_ext("audio") == ".bin"
    assert _default_ext("") == ".bin"


# ── validate_and_persist_attachments ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_unsupported_extension(tmp_path):
    team = _make_team()
    att = RawAttachment(filename="virus.exe", content_type=None, data=b"\x4d\x5a" * 10)
    with pytest.raises(AttachmentError) as exc_info:
        await validate_and_persist_attachments(team, [att])
    assert exc_info.value.status == 415
    assert ".exe" in str(exc_info.value)


@pytest.mark.asyncio
async def test_validate_image_rejected_when_no_vision(tmp_path):
    team = _make_team(vision=False)
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
    att = RawAttachment(filename="img.png", content_type="image/png", data=data)
    with pytest.raises(AttachmentError) as exc_info:
        await validate_and_persist_attachments(team, [att])
    assert exc_info.value.status == 422
    assert "image" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_validate_document_rejected_when_no_document_text(tmp_path):
    team = _make_team(document_text=False)
    data = b"%PDF-1.4" + b"\x00" * 50
    att = RawAttachment(filename="doc.pdf", content_type="application/pdf", data=data)
    with pytest.raises(AttachmentError) as exc_info:
        await validate_and_persist_attachments(team, [att])
    assert exc_info.value.status == 422
    assert "document" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_validate_global_size_limit_exceeded():
    team = _make_team()
    # Two text files, each just over half the global limit
    chunk = b"a" * (GLOBAL_SIZE_LIMIT // 2 + 1)
    att1 = RawAttachment(filename="big1.txt", content_type="text/plain", data=chunk)
    att2 = RawAttachment(filename="big2.txt", content_type="text/plain", data=chunk)
    with pytest.raises(AttachmentError) as exc_info:
        await validate_and_persist_attachments(team, [att1, att2])
    assert exc_info.value.status == 413
    assert "global" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_validate_empty_filename_skipped(tmp_path):
    """Attachments with empty filenames are silently skipped."""
    team = _make_team()
    with patch("app.services.agent_service._uploads_dir", return_value=tmp_path):
        sid, metas = await validate_and_persist_attachments(
            team,
            [RawAttachment(filename="", content_type="text/plain", data=b"hello")],
        )
    assert metas == []


@pytest.mark.asyncio
async def test_validate_and_persist_text_file(tmp_path):
    team = _make_team()
    content = b"hello world"
    att = RawAttachment(filename="notes.txt", content_type="text/plain", data=content)
    with patch("app.services.agent_service._uploads_dir", return_value=tmp_path):
        sid, metas = await validate_and_persist_attachments(team, [att])
    assert len(metas) == 1
    meta = metas[0]
    assert meta["category"] == "text"
    assert meta["converted_text"] == "hello world"
    assert meta["original_name"] == "notes.txt"
    # The saved file should exist on disk
    saved = tmp_path / meta["filename"]
    assert saved.is_file()
    assert saved.read_bytes() == content
    # ``path`` is the absolute on-disk location persisted for rehydration —
    # see ``app/agent/multimodal.py`` ``build_parts_from_metas``.
    assert meta["path"] == str(saved)
    assert Path(meta["path"]).is_file()


@pytest.mark.asyncio
async def test_validate_and_persist_mints_sid_when_session_id_none(tmp_path):
    team = _make_team()
    att = RawAttachment(filename="a.txt", content_type="text/plain", data=b"hi")
    with patch("app.services.agent_service._uploads_dir", return_value=tmp_path):
        sid, metas = await validate_and_persist_attachments(team, [att])
    # Should be a non-empty UUID-like string
    assert sid and len(sid) > 10
    # Meta carries the absolute on-disk path — rehydration relies on it
    # (no longer derived from message ``session_id``).
    assert len(metas) == 1
    assert "path" in metas[0]
    assert Path(metas[0]["path"]).is_file()


@pytest.mark.asyncio
async def test_validate_and_persist_uses_provided_session_id(tmp_path):
    """When ``session_id`` is supplied the function reuses it verbatim
    instead of minting a fresh one — uploads land under the chat
    session's workspace."""
    team = _make_team()
    att = RawAttachment(filename="a.txt", content_type="text/plain", data=b"hi")
    with patch("app.services.agent_service._uploads_dir", return_value=tmp_path):
        sid, metas = await validate_and_persist_attachments(
            team, [att], session_id="existing-sid-xyz"
        )
    assert sid == "existing-sid-xyz"
    assert len(metas) == 1


# ── dispatch_user_message ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_generates_sid_when_none():
    team = _make_team()
    sid, n = await dispatch_user_message(team, content="hello", session_id=None)
    assert sid and len(sid) > 8
    assert n == 0
    team.handle_user_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_reuses_provided_sid():
    team = _make_team()
    sid, n = await dispatch_user_message(team, content="hi", session_id="my-sid-123")
    assert sid == "my-sid-123"
    assert n == 0


@pytest.mark.asyncio
async def test_dispatch_with_attachments_uses_fresh_sid_when_session_id_none(tmp_path):
    team = _make_team()
    att = RawAttachment(filename="f.txt", content_type="text/plain", data=b"content")
    with patch("app.services.agent_service._uploads_dir", return_value=tmp_path):
        sid, n = await dispatch_user_message(
            team, content="hi", session_id=None, attachments=[att]
        )
    assert n == 1
    assert sid and len(sid) > 8


@pytest.mark.asyncio
async def test_dispatch_with_attachments_prefers_provided_session_id(tmp_path):
    team = _make_team()
    att = RawAttachment(filename="f.txt", content_type="text/plain", data=b"x")
    with patch("app.services.agent_service._uploads_dir", return_value=tmp_path):
        sid, n = await dispatch_user_message(
            team, content="hi", session_id="existing-123", attachments=[att]
        )
    assert sid == "existing-123"
    assert n == 1


# ── interrupt_team ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_interrupt_team_cancels_working_members():
    cancel_event = MagicMock()

    working = MagicMock()
    working.state = "working"
    working.name = "worker-a"
    working._cancel_event = cancel_event

    idle = MagicMock()
    idle.state = "idle"
    idle.name = "idler"

    team = MagicMock()
    team.all_members = [working, idle]

    names = await interrupt_team(team, session_id="sess-1")
    assert names == ["worker-a"]
    cancel_event.set.assert_called_once()


@pytest.mark.asyncio
async def test_interrupt_team_no_working_members():
    idle = MagicMock()
    idle.state = "idle"
    idle.name = "idler"

    team = MagicMock()
    team.all_members = [idle]

    names = await interrupt_team(team, session_id=None)
    assert names == []
