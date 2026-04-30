"""Tests for the dream service."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import patch

import pytest

from app.agent.agent_loop import Agent
from app.agent.providers.base import LLMProviderBase
from app.agent.schemas.chat import (
    AssistantMessage,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionDelta,
    ChatMessage,
    Usage,
)
from app.models.chat import ChatSession, DreamLog, SessionMessage
from app.services.dream import (
    _load_dream_agent,
    _synthesise_note,
    _synthesise_session,
    get_unprocessed_notes,
    get_unprocessed_sessions,
    mark_note_processed,
    mark_session_processed,
    run_dream,
)


# ── Mock LLM provider ─────────────────────────────────────────────────────────


class _MockProvider(LLMProviderBase):
    model = "mock-model"

    def __init__(self, reply: str = "Done."):
        super().__init__()
        self._reply = reply

    def stream(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> AsyncIterator[ChatCompletionChunk]:
        reply = self._reply

        async def _gen() -> AsyncIterator[ChatCompletionChunk]:
            yield ChatCompletionChunk(
                id="c1",
                created=1_000_000,
                model="mock-model",
                choices=[
                    ChatCompletionChunkChoice(
                        index=0,
                        delta=ChatCompletionDelta(content=reply),
                        finish_reason="stop",
                    )
                ],
                usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        return _gen()

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> AssistantMessage:
        return AssistantMessage(content=self._reply)


def _make_dream_agent() -> Agent:
    return Agent(name="dream", llm_provider=_MockProvider())


@pytest.fixture(autouse=True)
def _wiki_dir(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    target = tmp_path / "wiki"
    monkeypatch.setattr(settings, "OPENAGENTD_WIKI_DIR", str(target))
    (target / "notes").mkdir(parents=True, exist_ok=True)
    yield target


# ── get_unprocessed_sessions ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_unprocessed_sessions_empty(setup_db):
    """No sessions → empty list."""
    from app.core.db import async_session_factory

    async with async_session_factory() as db:
        result = await get_unprocessed_sessions(db)
    assert result == []


@pytest.mark.asyncio
async def test_get_unprocessed_sessions_returns_unprocessed(setup_db):
    """Sessions not in dream_log are returned (if they have messages)."""
    from app.core.db import async_session_factory

    session = ChatSession(agent_name="test-agent")
    async with async_session_factory() as db:
        db.add(session)
        await db.flush()
        db.add(
            SessionMessage(
                session_id=session.id,
                role="user",
                content="Hello!",
                exclude_from_context=False,
            )
        )
        await db.commit()

    async with async_session_factory() as db:
        result = await get_unprocessed_sessions(db)
    assert len(result) == 1
    assert result[0].id == session.id


@pytest.mark.asyncio
async def test_get_unprocessed_sessions_excludes_processed(setup_db):
    """Sessions already in dream_log are excluded."""
    from app.core.db import async_session_factory

    session = ChatSession(agent_name="test-agent")
    async with async_session_factory() as db:
        db.add(session)
        await db.commit()

    async with async_session_factory() as db:
        await mark_session_processed(db, session.id, "test-agent", [])
        await db.commit()

    async with async_session_factory() as db:
        result = await get_unprocessed_sessions(db)
    assert result == []


# ── mark_session_processed ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_session_processed_inserts_row(setup_db):
    """mark_session_processed should insert a DreamLog row."""
    from sqlmodel import select

    from app.core.db import async_session_factory

    session_id = uuid.uuid4()
    async with async_session_factory() as db:
        await mark_session_processed(db, session_id, "agent", ["topic-a"])
        await db.commit()

    async with async_session_factory() as db:
        result = await db.exec(select(DreamLog))
        rows = result.all()
    assert len(rows) == 1
    assert rows[0].agent_name == "agent"


# ── get_unprocessed_notes ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_unprocessed_notes_empty(setup_db, _wiki_dir: Path):
    """No note files → empty list."""
    from app.core.db import async_session_factory

    async with async_session_factory() as db:
        result = await get_unprocessed_notes(db)
    assert result == []


@pytest.mark.asyncio
async def test_get_unprocessed_notes_returns_unprocessed(setup_db, _wiki_dir: Path):
    """Note files not in dream_notes_log are returned."""
    from app.core.db import async_session_factory

    note_file = _wiki_dir / "notes" / "2026-04-29-abc.md"
    note_file.write_text("Note content.", encoding="utf-8")

    async with async_session_factory() as db:
        result = await get_unprocessed_notes(db)
    assert "2026-04-29-abc.md" in result


@pytest.mark.asyncio
async def test_get_unprocessed_notes_excludes_processed(setup_db, _wiki_dir: Path):
    """Note files already in dream_notes_log are excluded."""
    from app.core.db import async_session_factory

    note_file = _wiki_dir / "notes" / "2026-04-29-abc.md"
    note_file.write_text("Note content.", encoding="utf-8")

    async with async_session_factory() as db:
        await mark_note_processed(db, "2026-04-29-abc.md")
        await db.commit()

    async with async_session_factory() as db:
        result = await get_unprocessed_notes(db)
    assert result == []


# ── run_dream ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_dream_nothing_to_process(setup_db, _wiki_dir: Path):
    """run_dream with nothing to process returns zeros."""
    from app.core.db import async_session_factory

    async with async_session_factory() as db:
        result = await run_dream(db)
    assert result["sessions_processed"] == 0
    assert result["notes_processed"] == 0


@pytest.mark.asyncio
async def test_run_dream_processes_sessions(setup_db, _wiki_dir: Path):
    """run_dream marks sessions as processed (if they have messages)."""
    from sqlmodel import select

    from app.core.db import async_session_factory

    session = ChatSession(agent_name="test-agent")
    async with async_session_factory() as db:
        db.add(session)
        await db.flush()
        db.add(
            SessionMessage(
                session_id=session.id,
                role="user",
                content="Hello!",
                exclude_from_context=False,
            )
        )
        await db.commit()

    async with async_session_factory() as db:
        result = await run_dream(db)
    assert result["sessions_processed"] == 1

    async with async_session_factory() as db:
        rows = (await db.exec(select(DreamLog))).all()
    assert len(rows) == 1


# ── _load_dream_agent ─────────────────────────────────────────────────────────


def test_load_dream_agent_returns_none_when_missing(tmp_path, monkeypatch):
    """Returns None when dream.md does not exist."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "OPENAGENTD_CONFIG_DIR", str(tmp_path))
    assert _load_dream_agent() is None


def test_load_dream_agent_returns_none_when_no_model(tmp_path, monkeypatch):
    """Returns None when dream.md has no model field."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "OPENAGENTD_CONFIG_DIR", str(tmp_path))
    dream_md = tmp_path / "dream.md"
    dream_md.write_text(
        "---\nenabled: true\n---\n\nYou are the dream agent.\n",
        encoding="utf-8",
    )
    assert _load_dream_agent() is None


# ── _synthesise_session ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_synthesise_session_empty(setup_db, _wiki_dir: Path):
    """Empty session produces no topics and doesn't crash."""
    from app.core.db import async_session_factory

    session = ChatSession(agent_name="test-agent")
    async with async_session_factory() as db:
        db.add(session)
        await db.commit()

    agent = _make_dream_agent()
    async with async_session_factory() as db:
        result = await _synthesise_session(agent, db, session)

    assert result == []


@pytest.mark.asyncio
async def test_synthesise_session_with_messages(setup_db, _wiki_dir: Path):
    """Session with messages runs agent.run() without error."""
    from app.core.db import async_session_factory

    session = ChatSession(agent_name="test-agent")
    async with async_session_factory() as db:
        db.add(session)
        await db.flush()
        db.add(
            SessionMessage(
                session_id=session.id,
                role="user",
                content="Hello, I use Python.",
            )
        )
        db.add(
            SessionMessage(
                session_id=session.id,
                role="assistant",
                content="Got it! Python is great.",
            )
        )
        await db.commit()

    agent = _make_dream_agent()
    async with async_session_factory() as db:
        # Should not raise; topics list may be empty (mock agent writes nothing).
        result = await _synthesise_session(agent, db, session)

    assert isinstance(result, list)


# ── _synthesise_note ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_synthesise_note_with_content(setup_db, _wiki_dir: Path):
    """Note file with content runs agent.run() without error."""
    note_file = _wiki_dir / "notes" / "2026-04-29-test.md"
    note_file.write_text("I prefer dark mode.\n", encoding="utf-8")

    agent = _make_dream_agent()
    result = await _synthesise_note(agent, "2026-04-29-test.md")

    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_synthesise_note_missing_file(setup_db, _wiki_dir: Path):
    """Missing note file returns empty list without crashing."""
    agent = _make_dream_agent()
    result = await _synthesise_note(agent, "nonexistent.md")
    assert result == []


@pytest.mark.asyncio
async def test_synthesise_note_empty_file(setup_db, _wiki_dir: Path):
    """Empty note file returns empty list without calling agent."""
    note_file = _wiki_dir / "notes" / "2026-04-29-empty.md"
    note_file.write_text("   \n", encoding="utf-8")

    agent = _make_dream_agent()
    # Wrap run() to assert it's NOT called for empty content.
    run_calls = []
    original_run = agent.run

    async def _spy(*args, **kwargs):
        run_calls.append(args)
        return await original_run(*args, **kwargs)

    agent.run = _spy  # type: ignore[method-assign]
    result = await _synthesise_note(agent, "2026-04-29-empty.md")

    assert result == []
    assert run_calls == [], "agent.run() should not be called for empty notes"


# ── run_dream with mocked agent ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_dream_with_agent_processes_session(setup_db, _wiki_dir: Path):
    """run_dream uses dream agent when _load_dream_agent returns one."""
    from app.core.db import async_session_factory

    session = ChatSession(agent_name="test-agent")
    async with async_session_factory() as db:
        db.add(session)
        await db.flush()
        db.add(
            SessionMessage(
                session_id=session.id,
                role="user",
                content="Hello!",
                exclude_from_context=False,
            )
        )
        await db.commit()

    with patch(
        "app.services.dream._load_dream_agent", return_value=_make_dream_agent()
    ):
        async with async_session_factory() as db:
            result = await run_dream(db)

    assert result["sessions_processed"] == 1
    assert result["notes_processed"] == 0


@pytest.mark.asyncio
async def test_run_dream_with_agent_processes_note(setup_db, _wiki_dir: Path):
    """run_dream uses dream agent to process note files."""
    from app.core.db import async_session_factory

    note_file = _wiki_dir / "notes" / "2026-04-29-note.md"
    note_file.write_text("User prefers Vim.\n", encoding="utf-8")

    with patch(
        "app.services.dream._load_dream_agent", return_value=_make_dream_agent()
    ):
        async with async_session_factory() as db:
            result = await run_dream(db)

    assert result["notes_processed"] == 1
    assert result["sessions_processed"] == 0


@pytest.mark.asyncio
async def test_run_dream_topics_written_recorded(setup_db, _wiki_dir: Path):
    """Topics created by dream agent are recorded in dream_log."""
    from sqlmodel import select

    from app.core.db import async_session_factory

    session = ChatSession(agent_name="test-agent")
    async with async_session_factory() as db:
        db.add(session)
        await db.flush()
        db.add(
            SessionMessage(
                session_id=session.id,
                role="user",
                content="I love Python.",
            )
        )
        await db.commit()

    # Create a topic file during synthesis to simulate agent writing one.
    topics_dir = _wiki_dir / "topics"
    topics_dir.mkdir(exist_ok=True)

    async def _fake_synthesise(agent, db, sess):
        # Simulate agent writing a topic file.
        (topics_dir / "python.md").write_text(
            "---\ndescription: Python programming.\ntags: [python]\n---\n",
            encoding="utf-8",
        )
        return ["python"]

    with patch(
        "app.services.dream._load_dream_agent", return_value=_make_dream_agent()
    ):
        with patch(
            "app.services.dream._synthesise_session", side_effect=_fake_synthesise
        ):
            async with async_session_factory() as db:
                await run_dream(db)

    async with async_session_factory() as db:
        rows = (await db.exec(select(DreamLog))).all()

    assert len(rows) == 1
    import json

    assert json.loads(rows[0].topics_written) == ["python"]


# ── New tests for recent changes ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_unprocessed_sessions_skips_empty(setup_db):
    """Session with no messages is NOT returned, but IS auto-marked in dream_log."""
    from sqlmodel import select

    from app.core.db import async_session_factory

    session = ChatSession(agent_name="test-agent")
    async with async_session_factory() as db:
        db.add(session)
        await db.commit()

    # Call get_unprocessed_sessions — should skip the empty session
    async with async_session_factory() as db:
        result = await get_unprocessed_sessions(db)
        assert result == []
        # Verify the session was auto-marked as processed in dream_log
        # (within the same session since flush() was used)
        rows = (await db.exec(select(DreamLog))).all()
        assert len(rows) == 1
        assert rows[0].session_id == session.id


@pytest.mark.asyncio
async def test_get_unprocessed_sessions_keeps_session_with_messages(setup_db):
    """Session WITH a user message IS returned."""
    from app.core.db import async_session_factory

    session = ChatSession(agent_name="test-agent")
    async with async_session_factory() as db:
        db.add(session)
        await db.flush()
        db.add(
            SessionMessage(
                session_id=session.id,
                role="user",
                content="Hello, world!",
                exclude_from_context=False,
            )
        )
        await db.commit()

    async with async_session_factory() as db:
        result = await get_unprocessed_sessions(db)
    assert len(result) == 1
    assert result[0].id == session.id


@pytest.mark.asyncio
async def test_get_unprocessed_sessions_skips_system_only(setup_db):
    """Session with only system messages is treated as empty."""
    from app.core.db import async_session_factory

    session = ChatSession(agent_name="test-agent")
    async with async_session_factory() as db:
        db.add(session)
        await db.flush()
        db.add(
            SessionMessage(
                session_id=session.id,
                role="system",
                content="System message.",
                exclude_from_context=False,
            )
        )
        await db.commit()

    async with async_session_factory() as db:
        result = await get_unprocessed_sessions(db)
    assert result == []


@pytest.mark.asyncio
async def test_get_unprocessed_sessions_skips_excluded(setup_db):
    """Session with only exclude_from_context=True messages is treated as empty."""
    from app.core.db import async_session_factory

    session = ChatSession(agent_name="test-agent")
    async with async_session_factory() as db:
        db.add(session)
        await db.flush()
        db.add(
            SessionMessage(
                session_id=session.id,
                role="user",
                content="This is excluded.",
                exclude_from_context=True,
            )
        )
        await db.commit()

    async with async_session_factory() as db:
        result = await get_unprocessed_sessions(db)
    assert result == []


@pytest.mark.asyncio
async def test_run_dream_empty_sessions_not_counted_in_sessions_processed(setup_db):
    """sessions_processed in result reflects only non-empty sessions."""
    from sqlmodel import select

    from app.core.db import async_session_factory

    # Create one empty session and one with a message
    empty_session = ChatSession(agent_name="test-agent")
    session_with_msg = ChatSession(agent_name="test-agent")

    async with async_session_factory() as db:
        db.add(empty_session)
        db.add(session_with_msg)
        await db.flush()
        db.add(
            SessionMessage(
                session_id=session_with_msg.id,
                role="user",
                content="Hello!",
                exclude_from_context=False,
            )
        )
        await db.commit()

    async with async_session_factory() as db:
        result = await run_dream(db)

    # Only the non-empty session should be processed
    assert result["sessions_processed"] == 1
    # Empty session should be auto-marked but not counted in sessions_processed
    async with async_session_factory() as db:
        rows = (await db.exec(select(DreamLog))).all()
    assert len(rows) == 2  # Both sessions in dream_log


@pytest.mark.asyncio
async def test_run_dream_batch_budget_shared(setup_db, _wiki_dir: Path):
    """With batch_size=2, sessions fill budget first, then notes fill remainder."""
    from app.core.db import async_session_factory
    from app.core.config import settings

    # Create dream.md with batch_size=2
    config_dir = Path(settings.OPENAGENTD_CONFIG_DIR)
    config_dir.mkdir(parents=True, exist_ok=True)
    dream_md = config_dir / "dream.md"
    dream_md.write_text(
        "---\nname: dream\nmodel: mock:model\nbatch_size: 2\nenabled: true\n---\nYou are the dream agent.\n",
        encoding="utf-8",
    )

    # Create 1 session with message and 2 note files
    session1 = ChatSession(agent_name="test-agent")
    async with async_session_factory() as db:
        db.add(session1)
        await db.flush()
        db.add(
            SessionMessage(
                session_id=session1.id,
                role="user",
                content="Hello!",
                exclude_from_context=False,
            )
        )
        await db.commit()

    # Create 2 note files
    note_file1 = _wiki_dir / "notes" / "2026-04-29-note1.md"
    note_file1.write_text("Test note 1.\n", encoding="utf-8")
    note_file2 = _wiki_dir / "notes" / "2026-04-29-note2.md"
    note_file2.write_text("Test note 2.\n", encoding="utf-8")

    with patch(
        "app.services.dream._load_dream_agent", return_value=_make_dream_agent()
    ):
        async with async_session_factory() as db:
            result = await run_dream(db)

    # With batch_size=2: 1 session + 1 note (note_budget = 2 - 1 = 1)
    assert result["sessions_processed"] == 1
    assert result["notes_processed"] == 1
    assert result["remaining"] == 1  # 1 note left unprocessed
