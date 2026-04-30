import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.chat import ChatSession, SessionMessage
from app.agent.schemas.chat import (
    AssistantMessage,
    FunctionCall,
    HumanMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
)
from app.services.chat_service import (
    create_chat_session,
    get_messages,
    get_messages_for_llm,
    heal_orphaned_tool_calls,
    hide_messages_before_summary,
    save_message,
)


@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine):
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session


@pytest.mark.asyncio
async def test_create_chat_session(session):
    chat_session = await create_chat_session(session, title="Test Session")
    assert chat_session.id is not None
    assert chat_session.title == "Test Session"

    # Verify it exists in DB
    db_session = await session.get(ChatSession, chat_session.id)
    assert db_session is not None


@pytest.mark.asyncio
async def test_save_and_get_messages(session):
    chat_session = await create_chat_session(session)

    messages = [
        SystemMessage(content="system"),
        HumanMessage(content="hello"),
        AssistantMessage(
            content="hi",
            reasoning_content="thinking",
            tool_calls=[
                ToolCall(id="c1", function=FunctionCall(name="f", arguments="{}"))
            ],
        ),
        ToolMessage(
            role="tool", content="result", tool_call_id="call_1", name="tool_name"
        ),
    ]

    for msg in messages:
        await save_message(session, chat_session.id, msg)

    fetched = await get_messages(session, chat_session.id)
    assert len(fetched) == 4
    assert isinstance(fetched[0], SystemMessage)
    assert isinstance(fetched[1], HumanMessage)
    assert isinstance(fetched[2], AssistantMessage)
    assert fetched[2].reasoning_content == "thinking"
    assert isinstance(fetched[2].tool_calls, list)
    assert len(fetched[2].tool_calls) == 1
    assert isinstance(fetched[3], ToolMessage)
    assert fetched[3].tool_call_id == "call_1"
    assert fetched[3].name == "tool_name"


@pytest.mark.asyncio
async def test_get_messages_unhandled_role(session):
    chat_session = await create_chat_session(session)

    # Manually insert a message with an unhandled role
    db_msg = SessionMessage(
        session_id=chat_session.id,
        role="unknown",
        content="something",
    )
    session.add(db_msg)
    await session.commit()

    fetched = await get_messages(session, chat_session.id)
    assert len(fetched) == 0  # It should be skipped by the current loop


# ── Summarisation: save_message flags ────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_message_with_summary_flag(session):
    """save_message persists is_summary=True correctly (summary is a HumanMessage)."""
    chat_session = await create_chat_session(session)
    msg = HumanMessage(content="Summary text.")
    saved = await save_message(session, chat_session.id, msg, is_summary=True)
    assert saved.is_summary is True
    assert saved.exclude_from_context is False
    assert saved.role == "user"


@pytest.mark.asyncio
async def test_save_message_with_hidden_flag(session):
    """save_message persists exclude_from_context=True correctly."""
    chat_session = await create_chat_session(session)
    msg = HumanMessage(content="Old message.")
    saved = await save_message(session, chat_session.id, msg, is_hidden=True)
    assert saved.exclude_from_context is True
    assert saved.is_summary is False


# ── get_messages excludes hidden ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_messages_excludes_hidden(session):
    """get_messages must not return is_hidden=True messages."""
    chat_session = await create_chat_session(session)

    await save_message(session, chat_session.id, HumanMessage(content="visible"))
    await save_message(
        session, chat_session.id, HumanMessage(content="hidden"), is_hidden=True
    )

    fetched = await get_messages(session, chat_session.id)
    assert len(fetched) == 1
    assert fetched[0].content == "visible"


@pytest.mark.asyncio
async def test_get_messages_includes_summary_message(session):
    """Summary messages (HumanMessage) are visible so get_messages returns them."""
    chat_session = await create_chat_session(session)
    await save_message(
        session,
        chat_session.id,
        HumanMessage(content="Summary."),
        is_summary=True,
    )

    fetched = await get_messages(session, chat_session.id)
    assert len(fetched) == 1
    assert isinstance(fetched[0], HumanMessage)
    assert fetched[0].content == "Summary."


# ── get_messages_for_llm ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_messages_for_llm_no_summary_returns_all_visible(session):
    """With no summary, get_messages_for_llm behaves like get_messages."""
    chat_session = await create_chat_session(session)

    await save_message(session, chat_session.id, HumanMessage(content="a"))
    await save_message(session, chat_session.id, AssistantMessage(content="b"))

    result = await get_messages_for_llm(session, chat_session.id)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_get_messages_for_llm_returns_summary_plus_newer_messages(session):
    """With a summary present, only the summary and post-summary messages are returned."""
    chat_session = await create_chat_session(session)

    # Old messages that will be hidden
    await save_message(
        session, chat_session.id, HumanMessage(content="old 1"), is_hidden=True
    )
    await save_message(
        session, chat_session.id, AssistantMessage(content="old 2"), is_hidden=True
    )

    # Summary is stored as HumanMessage
    await save_message(
        session,
        chat_session.id,
        HumanMessage(content="Summary of old conversation."),
        is_summary=True,
    )

    # New messages after the summary
    await save_message(session, chat_session.id, HumanMessage(content="new 1"))
    await save_message(session, chat_session.id, AssistantMessage(content="new 2"))

    result = await get_messages_for_llm(session, chat_session.id)

    contents = [m.content for m in result]
    # Must include the summary itself
    assert "Summary of old conversation." in contents
    # Summary must be a HumanMessage (not AssistantMessage) for valid role ordering
    summary_msg = next(m for m in result if m.content == "Summary of old conversation.")
    assert isinstance(summary_msg, HumanMessage)
    # Must include post-summary messages
    assert "new 1" in contents
    assert "new 2" in contents
    # Must NOT include hidden old messages
    assert "old 1" not in contents
    assert "old 2" not in contents
    # Summary must be first
    assert result[0].content == "Summary of old conversation."


@pytest.mark.asyncio
async def test_get_messages_for_llm_uses_most_recent_summary(session):
    """When multiple summaries exist, only the latest one and messages after it are included."""
    chat_session = await create_chat_session(session)

    await save_message(
        session,
        chat_session.id,
        HumanMessage(content="First summary."),
        is_summary=True,
        is_hidden=False,
    )
    await save_message(
        session, chat_session.id, HumanMessage(content="middle"), is_hidden=True
    )
    await save_message(
        session,
        chat_session.id,
        HumanMessage(content="Latest summary."),
        is_summary=True,
    )
    await save_message(session, chat_session.id, HumanMessage(content="after latest"))

    result = await get_messages_for_llm(session, chat_session.id)
    contents = [m.content for m in result]
    assert "Latest summary." in contents
    assert "after latest" in contents
    # First summary is older than latest_summary.created_at and is_hidden=False
    # but created_at <= latest_summary.created_at so it won't be included via
    # the "after" branch; it's also not the latest summary row selected
    assert "First summary." not in contents
    assert "middle" not in contents


# ── hide_messages_before_summary ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hide_messages_before_summary(session):
    """hide_messages_before_summary marks all non-summary older messages as hidden."""
    chat_session = await create_chat_session(session)

    m1 = await save_message(session, chat_session.id, HumanMessage(content="msg 1"))
    m2 = await save_message(session, chat_session.id, AssistantMessage(content="msg 2"))
    summary = await save_message(
        session,
        chat_session.id,
        HumanMessage(content="Summary"),
        is_summary=True,
    )
    m4 = await save_message(session, chat_session.id, HumanMessage(content="msg 4"))

    hidden_count = await hide_messages_before_summary(
        session, chat_session.id, summary.id
    )
    await session.commit()

    assert hidden_count == 2

    # Reload from DB
    from sqlmodel import col, select
    from app.models.chat import SessionMessage

    rows = (
        await session.exec(
            select(SessionMessage).where(
                col(SessionMessage.session_id) == chat_session.id
            )
        )
    ).all()
    by_id = {r.id: r for r in rows}

    assert by_id[m1.id].exclude_from_context is True
    assert by_id[m2.id].exclude_from_context is True
    assert (
        by_id[summary.id].exclude_from_context is False
    )  # summary itself not excluded
    assert by_id[m4.id].exclude_from_context is False  # after summary — not touched


@pytest.mark.asyncio
async def test_hide_messages_before_summary_missing_summary(session):
    """Returns 0 when the summary message id does not exist."""
    from uuid import uuid7

    chat_session = await create_chat_session(session)
    count = await hide_messages_before_summary(session, chat_session.id, uuid7())
    assert count == 0


@pytest.mark.asyncio
async def test_hide_messages_before_summary_keep_last_n_all_spare(session):
    """When keep_last_n >= number of pre-summary messages, nothing is hidden."""
    chat_session = await create_chat_session(session)

    m1 = await save_message(session, chat_session.id, HumanMessage(content="msg 1"))
    m2 = await save_message(session, chat_session.id, AssistantMessage(content="msg 2"))
    summary = await save_message(
        session,
        chat_session.id,
        HumanMessage(content="Summary"),
        is_summary=True,
    )

    # keep_last_n=5 but only 2 pre-summary messages — all should be spared
    hidden_count = await hide_messages_before_summary(
        session, chat_session.id, summary.id, keep_last_n=5
    )
    await session.commit()
    assert hidden_count == 0

    from sqlmodel import col, select
    from app.models.chat import SessionMessage

    rows = (
        await session.exec(
            select(SessionMessage).where(
                col(SessionMessage.session_id) == chat_session.id
            )
        )
    ).all()
    by_id = {r.id: r for r in rows}
    assert by_id[m1.id].exclude_from_context is False
    assert by_id[m2.id].exclude_from_context is False


@pytest.mark.asyncio
async def test_create_chat_session_error_propagates(session):
    """create_chat_session re-raises on DB error."""
    from unittest.mock import patch

    with patch.object(session, "flush", side_effect=Exception("db error")):
        with pytest.raises(Exception, match="db error"):
            await create_chat_session(session, title="fail")


@pytest.mark.asyncio
async def test_save_message_error_propagates(session):
    """save_message re-raises on DB error."""
    from unittest.mock import patch

    chat_session = await create_chat_session(session)
    with patch.object(session, "flush", side_effect=Exception("write error")):
        with pytest.raises(Exception, match="write error"):
            await save_message(session, chat_session.id, HumanMessage(content="x"))


@pytest.mark.asyncio
async def test_get_messages_error_propagates(session):
    """get_messages re-raises on DB error."""
    from unittest.mock import patch
    from uuid import uuid7

    with patch.object(session, "exec", side_effect=Exception("read error")):
        with pytest.raises(Exception, match="read error"):
            await get_messages(session, uuid7())


@pytest.mark.asyncio
async def test_get_messages_for_llm_error_propagates(session):
    """get_messages_for_llm re-raises on DB error."""
    from unittest.mock import patch
    from uuid import uuid7

    with patch.object(session, "exec", side_effect=Exception("llm read error")):
        with pytest.raises(Exception, match="llm read error"):
            await get_messages_for_llm(session, uuid7())


# ── Summarisation integration: full flow ────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_flow_produces_valid_llm_context(session):
    """Integration: save messages, insert summary, hide old ones, check get_messages_for_llm.

    Verifies:
    - Summary (HumanMessage) is first in the returned list.
    - Post-summary messages follow in order.
    - Hidden pre-summary messages are excluded.
    - Exact count and types are correct.
    """
    chat_session = await create_chat_session(session)

    # Initial conversation (will be hidden after summarization)
    await save_message(session, chat_session.id, HumanMessage(content="Hello"))
    await save_message(session, chat_session.id, AssistantMessage(content="Hi there"))
    await save_message(
        session, chat_session.id, HumanMessage(content="What is Python?")
    )
    await save_message(
        session, chat_session.id, AssistantMessage(content="A programming language.")
    )

    # Summarization fires: save summary as HumanMessage with is_summary=True
    summary = await save_message(
        session,
        chat_session.id,
        HumanMessage(
            content="[Summary] User asked about Python. Bot explained it is a programming language."
        ),
        is_summary=True,
    )

    # Hide all pre-summary messages (keep_last_n=0 for this test)
    hidden_count = await hide_messages_before_summary(
        session, chat_session.id, summary.id, keep_last_n=0
    )
    await session.commit()
    assert hidden_count == 4

    # New conversation turn after summarization
    await save_message(session, chat_session.id, HumanMessage(content="Tell me more"))
    await save_message(session, chat_session.id, AssistantMessage(content="Sure!"))
    await session.commit()

    result = await get_messages_for_llm(session, chat_session.id)

    # Summary is first and is a HumanMessage
    assert len(result) == 3
    assert isinstance(result[0], HumanMessage)
    assert result[0].content is not None
    assert "[Summary]" in result[0].content

    # Followed by the two new messages in order
    assert isinstance(result[1], HumanMessage)
    assert result[1].content == "Tell me more"
    assert isinstance(result[2], AssistantMessage)
    assert result[2].content == "Sure!"

    # Hidden old messages not present
    old_contents = {m.content for m in result}
    assert "Hello" not in old_contents
    assert "Hi there" not in old_contents
    assert "What is Python?" not in old_contents
    assert "A programming language." not in old_contents


@pytest.mark.asyncio
async def test_summary_flow_with_keep_last_n(session):
    """Integration: keep_last_n=2 preserves last 2 messages before summary in LLM context.

    After summarization with keep_last_n=2, get_messages_for_llm should return:
    [summary, kept_msg_3, kept_msg_4, post_summary_msg]
    """
    chat_session = await create_chat_session(session)

    await save_message(session, chat_session.id, HumanMessage(content="msg 1"))
    await save_message(session, chat_session.id, AssistantMessage(content="msg 2"))
    await save_message(session, chat_session.id, HumanMessage(content="msg 3"))
    await save_message(session, chat_session.id, AssistantMessage(content="msg 4"))

    summary = await save_message(
        session,
        chat_session.id,
        HumanMessage(content="[Summary] First two messages covered greetings."),
        is_summary=True,
    )

    hidden_count = await hide_messages_before_summary(
        session, chat_session.id, summary.id, keep_last_n=2
    )
    await session.commit()
    # Only msg 1 and msg 2 should be hidden; msg 3 and msg 4 are kept
    assert hidden_count == 2

    await save_message(session, chat_session.id, HumanMessage(content="msg 5"))
    await session.commit()

    result = await get_messages_for_llm(session, chat_session.id)

    contents = [m.content for m in result]
    # Summary first
    assert result[0].content == "[Summary] First two messages covered greetings."
    assert isinstance(result[0], HumanMessage)
    # Kept messages and post-summary present
    assert "msg 3" in contents
    assert "msg 4" in contents
    assert "msg 5" in contents
    # Hidden messages excluded
    assert "msg 1" not in contents
    assert "msg 2" not in contents
    assert len(result) == 4  # summary + msg3 + msg4 + msg5


# ── exclude_messages_before_summary — old summaries excluded (lines 276-277) ─


@pytest.mark.asyncio
async def test_exclude_messages_before_summary_marks_old_summaries_excluded(session):
    """Lines 276-277: when a second summary is created, the first summary row
    is marked exclude_from_context=True by exclude_messages_before_summary."""
    from app.services.chat_service import exclude_messages_before_summary

    chat_session = await create_chat_session(session)

    # Me first summary (older)
    first_summary = await save_message(
        session,
        chat_session.id,
        HumanMessage(content="[Summary] First summary."),
        is_summary=True,
    )

    # Me some messages after first summary
    await save_message(
        session, chat_session.id, HumanMessage(content="msg after first")
    )

    # Me second (newer) summary
    second_summary = await save_message(
        session,
        chat_session.id,
        HumanMessage(content="[Summary] Second summary."),
        is_summary=True,
    )

    # Me call with second summary id — should exclude first summary
    await exclude_messages_before_summary(session, chat_session.id, second_summary.id)
    await session.commit()

    # Me reload first summary row from DB
    from sqlmodel import col, select
    from app.models.chat import SessionMessage

    rows = (
        await session.exec(
            select(SessionMessage).where(col(SessionMessage.id) == first_summary.id)
        )
    ).all()
    assert len(rows) == 1
    # Me first summary should now be excluded
    assert rows[0].exclude_from_context is True

    # Me second summary itself should NOT be excluded
    second_rows = (
        await session.exec(
            select(SessionMessage).where(col(SessionMessage.id) == second_summary.id)
        )
    ).all()
    assert second_rows[0].exclude_from_context is False


@pytest.mark.asyncio
async def test_get_messages_for_llm_summary_appears_exactly_once(session):
    """The summary row must appear exactly once even when other rows share its timestamp.

    get_messages_for_llm prepends the latest summary explicitly and then fetches
    non-summary rows, so the summary is never duplicated regardless of timestamps.
    """
    from app.models.chat import SessionMessage

    chat_session = await create_chat_session(session)

    await save_message(session, chat_session.id, HumanMessage(content="before"))
    summary = await save_message(
        session,
        chat_session.id,
        HumanMessage(content="[Summary] Compact history."),
        is_summary=True,
    )
    await session.commit()

    # Force a non-hidden, non-summary message to share the exact created_at as the summary.
    same_ts_msg = SessionMessage(
        session_id=chat_session.id,
        role="user",
        content="same-timestamp sibling",
        exclude_from_context=False,
        is_summary=False,
    )
    same_ts_msg.created_at = summary.created_at
    session.add(same_ts_msg)
    await session.commit()

    result = await get_messages_for_llm(session, chat_session.id)
    contents = [m.content for m in result]

    # Summary appears exactly once — never duplicated by the non-summary query
    assert contents.count("[Summary] Compact history.") == 1
    # Non-hidden, non-summary messages (before + sibling) are included
    assert "before" in contents
    assert "same-timestamp sibling" in contents


# ---------------------------------------------------------------------------
# heal_orphaned_tool_calls
# ---------------------------------------------------------------------------


def _assistant_with_tool_calls(*ids_and_names: tuple[str, str]) -> AssistantMessage:
    """Build an assistant message carrying ``tool_calls`` for each (id, name)."""
    return AssistantMessage(
        content="",
        tool_calls=[
            ToolCall(id=tcid, function=FunctionCall(name=tcname, arguments="{}"))
            for tcid, tcname in ids_and_names
        ],
    )


@pytest.mark.asyncio
async def test_heal_noop_when_no_assistant_messages(session):
    """No assistant message in the session → nothing to heal."""
    chat_session = await create_chat_session(session)
    await save_message(session, chat_session.id, HumanMessage(content="hi"))
    await session.commit()

    healed = await heal_orphaned_tool_calls(session, chat_session.id)
    assert healed == 0


@pytest.mark.asyncio
async def test_heal_noop_when_last_assistant_has_no_tool_calls(session):
    """Final-answer assistant message → nothing to heal."""
    chat_session = await create_chat_session(session)
    await save_message(session, chat_session.id, HumanMessage(content="hi"))
    await save_message(session, chat_session.id, AssistantMessage(content="hello!"))
    await session.commit()

    healed = await heal_orphaned_tool_calls(session, chat_session.id)
    assert healed == 0


@pytest.mark.asyncio
async def test_heal_noop_when_all_tool_calls_have_results(session):
    """Healthy turn (assistant{tool_calls} + matching tool replies) → noop."""
    chat_session = await create_chat_session(session)
    await save_message(session, chat_session.id, HumanMessage(content="hi"))
    await save_message(
        session,
        chat_session.id,
        _assistant_with_tool_calls(("c1", "search"), ("c2", "fetch")),
    )
    await save_message(
        session,
        chat_session.id,
        ToolMessage(content="r1", tool_call_id="c1", name="search"),
    )
    await save_message(
        session,
        chat_session.id,
        ToolMessage(content="r2", tool_call_id="c2", name="fetch"),
    )
    await session.commit()

    healed = await heal_orphaned_tool_calls(session, chat_session.id)
    assert healed == 0


@pytest.mark.asyncio
async def test_heal_synthesises_stub_for_fully_orphaned_tool_calls(session):
    """Crash mid-tool: assistant{tool_calls} with zero tool replies → all stubbed."""
    chat_session = await create_chat_session(session)
    await save_message(session, chat_session.id, HumanMessage(content="hi"))
    await save_message(
        session,
        chat_session.id,
        _assistant_with_tool_calls(("c1", "search"), ("c2", "fetch")),
    )
    await session.commit()

    healed = await heal_orphaned_tool_calls(session, chat_session.id)
    await session.commit()

    assert healed == 2

    # Both stubs should now be visible, with the canonical interrupted message.
    msgs = await get_messages(session, chat_session.id)
    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    assert {m.tool_call_id for m in tool_msgs} == {"c1", "c2"}
    assert {m.name for m in tool_msgs} == {"search", "fetch"}
    for tm in tool_msgs:
        assert tm.content is not None and "interrupted" in tm.content.lower()


@pytest.mark.asyncio
async def test_heal_synthesises_stub_only_for_missing_ids(session):
    """Partial orphan: one tool call has a result, the other doesn't.

    Only the missing one is synthesised; the existing result is untouched.
    """
    chat_session = await create_chat_session(session)
    await save_message(session, chat_session.id, HumanMessage(content="hi"))
    await save_message(
        session,
        chat_session.id,
        _assistant_with_tool_calls(("c1", "search"), ("c2", "fetch")),
    )
    await save_message(
        session,
        chat_session.id,
        ToolMessage(content="real-result", tool_call_id="c1", name="search"),
    )
    await session.commit()

    healed = await heal_orphaned_tool_calls(session, chat_session.id)
    await session.commit()

    assert healed == 1

    msgs = await get_messages(session, chat_session.id)
    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 2
    by_id = {m.tool_call_id: m for m in tool_msgs}
    assert by_id["c1"].content == "real-result"
    c2_content = by_id["c2"].content
    assert c2_content is not None and "interrupted" in c2_content.lower()


@pytest.mark.asyncio
async def test_heal_is_idempotent(session):
    """Running the heal twice in a row inserts stubs only the first time."""
    chat_session = await create_chat_session(session)
    await save_message(session, chat_session.id, HumanMessage(content="hi"))
    await save_message(
        session,
        chat_session.id,
        _assistant_with_tool_calls(("c1", "search")),
    )
    await session.commit()

    first = await heal_orphaned_tool_calls(session, chat_session.id)
    await session.commit()
    second = await heal_orphaned_tool_calls(session, chat_session.id)
    await session.commit()

    assert first == 1
    assert second == 0


@pytest.mark.asyncio
async def test_heal_orders_stubs_between_assistant_and_next_user_message(session):
    """The synthesised tool replies must sit *between* the orphaned
    assistant turn and the new user message in chronological order, so
    that ``get_messages_for_llm`` returns
    ``assistant{tool_calls} → tool → user`` instead of
    ``assistant{tool_calls} → user → tool``.

    OpenAI rejects the latter with ``"No tool output found for function
    call …"``; this regression test pins the ordering invariant.
    """
    chat_session = await create_chat_session(session)
    await save_message(session, chat_session.id, HumanMessage(content="first"))
    await save_message(
        session,
        chat_session.id,
        _assistant_with_tool_calls(("c1", "search"), ("c2", "fetch")),
    )
    await session.commit()

    # Heal *before* persisting the new user message — same order as the
    # production call site in ``team.handle_user_message``.
    await heal_orphaned_tool_calls(session, chat_session.id)
    await save_message(session, chat_session.id, HumanMessage(content="follow-up"))
    await session.commit()

    msgs = await get_messages_for_llm(session, chat_session.id)
    roles = [m.role for m in msgs]
    # first user, assistant{tool_calls}, two tool stubs, then the new user.
    assert roles == ["user", "assistant", "tool", "tool", "user"]
    # Tool stubs must reference the orphaned assistant's IDs.
    stub_a, stub_b = msgs[2], msgs[3]
    assert isinstance(stub_a, ToolMessage) and isinstance(stub_b, ToolMessage)
    assert {stub_a.tool_call_id, stub_b.tool_call_id} == {"c1", "c2"}
    # And the follow-up user message is the actual tail.
    assert msgs[-1].content == "follow-up"


@pytest.mark.asyncio
async def test_heal_only_inspects_latest_assistant_message(session):
    """An older healthy turn followed by a newer healthy turn must not
    trigger heal even if the older turn has tool_calls.

    Guards the ``LIMIT 1`` peek logic — we only care about the tail."""
    chat_session = await create_chat_session(session)
    await save_message(session, chat_session.id, HumanMessage(content="q1"))
    await save_message(
        session,
        chat_session.id,
        _assistant_with_tool_calls(("c1", "search")),
    )
    await save_message(
        session,
        chat_session.id,
        ToolMessage(content="result", tool_call_id="c1", name="search"),
    )
    await save_message(session, chat_session.id, AssistantMessage(content="answer"))
    await session.commit()

    healed = await heal_orphaned_tool_calls(session, chat_session.id)
    assert healed == 0


@pytest.mark.asyncio
async def test_heal_skips_summary_messages_when_finding_latest_assistant(session):
    """SystemMessage rows in between mustn't confuse the lookup.

    The heal targets the latest *assistant* row specifically; system /
    summary rows (which never carry tool_calls) are irrelevant."""
    chat_session = await create_chat_session(session)
    await save_message(session, chat_session.id, SystemMessage(content="sys"))
    await save_message(session, chat_session.id, HumanMessage(content="hi"))
    await save_message(
        session,
        chat_session.id,
        _assistant_with_tool_calls(("c1", "search")),
    )
    await session.commit()

    healed = await heal_orphaned_tool_calls(session, chat_session.id)
    assert healed == 1
