import asyncio
import json
import shutil
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from uuid import UUID

from loguru import logger
from sqlmodel import and_, col, not_, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from pydantic import TypeAdapter

from app.agent.multimodal import build_parts_from_metas
from app.agent.schemas.chat import (
    AssistantMessage,
    ChatMessage,
    HumanMessage,
    ToolMessage,
)
from app.core.paths import uploads_dir, workspace_dir
from app.models.chat import ChatSession, SessionMessage

# Me build once — reused by _deserialize_messages for discriminated union parsing
_chat_message_adapter: TypeAdapter[ChatMessage] = TypeAdapter(ChatMessage)


async def create_chat_session(
    db: AsyncSession,
    title: str | None = None,
    parent_session_id: UUID | None = None,
    agent_name: str | None = None,
) -> ChatSession:
    """Creates a new chat session.

    Args:
        db: Async database session.
        title: Optional human-readable title.
        parent_session_id: If set, links this session as a child of another
            (e.g. a subagent session within a supervisor run).
        agent_name: Name of the agent that owns this session.
    """
    logger.debug("creating_chat_session title={} agent_name={}", title, agent_name)
    try:
        session = ChatSession(
            title=title,
            parent_session_id=parent_session_id,
            agent_name=agent_name,
        )
        db.add(session)
        await db.flush()
        await db.refresh(session)
        logger.info("chat_session_created session_id={} title={}", session.id, title)
        return session
    except Exception as e:
        logger.error("chat_session_creation_failed error={} title={}", e, title)
        raise


_INTERRUPTED_TOOL_RESULT = (
    "Tool execution was interrupted before a result could be recorded."
)


async def heal_orphaned_tool_calls(db: AsyncSession, session_id: UUID) -> int:
    """Insert synthetic ``ToolMessage`` rows for unmatched tool_calls.

    Background — the agent loop persists the assistant turn (with
    ``tool_calls``) *before* tools run, so a server restart mid-tool
    leaves an assistant message whose ``tool_calls`` have no following
    ``tool`` rows.  The next turn would then 400 against any provider
    that enforces the assistant→tool pairing (OpenAI, Anthropic, …)::

        No tool output found for function call fc_…

    Heal strategy: peek at the last *visible* assistant message in the
    session.  If it has ``tool_calls``, look up which IDs are already
    paired with a ``tool`` reply and INSERT a stub for any that are
    missing.  The stub sits in the same DB transaction as the caller,
    so the heal lands atomically with the next user message.

    Only the latest assistant message is inspected: a healthy turn
    always either ends without tool_calls (final answer) or has every
    tool_call paired before the next assistant message; an earlier
    orphan would have crashed the loop on the previous turn before the
    log got this deep.

    Returns the number of synthetic rows inserted (``0`` in the healthy
    case).  Caller is responsible for the commit.
    """
    last_assistant_stmt = (
        select(SessionMessage)
        .where(col(SessionMessage.session_id) == session_id)
        .where(col(SessionMessage.role) == "assistant")
        .order_by(col(SessionMessage.created_at).desc())
        .limit(1)
    )
    last_assistant = (await db.exec(last_assistant_stmt)).first()
    if last_assistant is None or not last_assistant.tool_calls:
        return 0

    expected_ids: list[str] = [
        tc["id"] for tc in last_assistant.tool_calls if tc.get("id")
    ]
    if not expected_ids:
        return 0

    matched_stmt = (
        select(SessionMessage.tool_call_id)
        .where(col(SessionMessage.session_id) == session_id)
        .where(col(SessionMessage.role) == "tool")
        .where(col(SessionMessage.created_at) >= last_assistant.created_at)
        .where(col(SessionMessage.tool_call_id).in_(expected_ids))
    )
    matched_ids = {row for row in (await db.exec(matched_stmt)).all() if row}
    missing = [
        tc for tc in last_assistant.tool_calls if tc.get("id") not in matched_ids
    ]
    if not missing:
        return 0

    # Anchor synthetic timestamps to the orphaned assistant message so
    # that even if the user sends the next message in the same micro-
    # second as the heal runs, the LLM input order is unambiguous:
    # ``assistant{tool_calls} → tool (synth) → tool (synth) → … → user``.
    # ``+1µs * (i+1)`` keeps multiple stubs strictly monotonic relative
    # to one another, and well before any new ``utcnow()`` write.
    for i, tc in enumerate(missing):
        stub = ToolMessage(
            content=_INTERRUPTED_TOOL_RESULT,
            tool_call_id=tc["id"],
            name=tc.get("function", {}).get("name", "unknown"),
        )
        await save_message(
            db,
            session_id,
            stub,
            created_at=last_assistant.created_at + timedelta(microseconds=i + 1),
        )

    logger.warning(
        "tool_call_orphans_healed session_id={} count={} ids=[{}]",
        session_id,
        len(missing),
        ", ".join(tc["id"] for tc in missing),
    )
    return len(missing)


async def save_message(
    db: AsyncSession,
    session_id: UUID,
    message: ChatMessage,
    *,
    is_summary: bool = False,
    is_hidden: bool = False,
    exclude_from_context: bool | None = None,
    extra: dict | None = None,
    created_at: datetime | None = None,
) -> SessionMessage:
    """Saves a ChatMessage to the database.

    Args:
        db: Async database session.
        session_id: The session to attach the message to.
        message: The chat message to persist.
        is_summary: When ``True`` this message is a conversation summary
            (produced by :class:`~app.hooks.summarization.SummarizationHook`).
        is_hidden: Deprecated alias for ``exclude_from_context``.
        exclude_from_context: When ``True`` this message is excluded from the
            LLM context window but retained for audit / history.
        created_at: Optional explicit timestamp.  Defaults to ``utcnow()``
            via the model's Field default.  Used by
            :func:`heal_orphaned_tool_calls` to anchor synthetic tool
            replies immediately after the orphaned assistant message
            (so the LLM sees ``assistant{tool_calls} → tool → user``,
            not ``assistant{tool_calls} → user → tool``).
    """
    # Me support both old and new param names during transition
    _exclude = exclude_from_context if exclude_from_context is not None else is_hidden
    logger.debug(
        "saving_message session_id={} role={} content_length={} is_summary={} exclude_from_context={}",
        session_id,
        message.role,
        len(message.content or ""),
        is_summary,
        _exclude,
    )

    tool_calls = None
    tool_call_id = None
    name = None
    reasoning_content = None

    if isinstance(message, AssistantMessage):
        reasoning_content = message.reasoning_content
        if message.tool_calls:
            tool_calls = [tc.model_dump() for tc in message.tool_calls]
            logger.debug(
                "assistant_message_has_tool_calls session_id={} count={}",
                session_id,
                len(tool_calls),
            )
    elif isinstance(message, ToolMessage):
        tool_call_id = message.tool_call_id
        name = message.name
        logger.debug(
            "tool_message_with_result session_id={} tool={} id={}",
            session_id,
            name,
            tool_call_id,
        )

    try:
        kwargs: dict = dict(
            session_id=session_id,
            role=message.role,
            content=message.content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            name=name,
            is_summary=is_summary,
            exclude_from_context=_exclude,
            extra=extra,
        )
        if created_at is not None:
            kwargs["created_at"] = created_at
        db_message = SessionMessage(**kwargs)
        db.add(db_message)
        await db.flush()
        await db.refresh(db_message)
        logger.debug(
            "message_saved session_id={} message_id={} role={}",
            session_id,
            db_message.id,
            message.role,
        )
        return db_message
    except Exception as e:
        logger.error(
            "message_save_failed session_id={} role={} error={}",
            session_id,
            message.role,
            e,
        )
        raise


def _visible_messages_stmt(session_id: UUID):
    """Base query: all non-excluded messages for a session, oldest first.

    Used by both :func:`get_messages` (UI view) and
    :func:`get_messages_for_llm` (LLM context window).
    """
    return (
        select(SessionMessage)
        .where(col(SessionMessage.session_id) == session_id)
        .where(~col(SessionMessage.exclude_from_context))
        .order_by(col(SessionMessage.created_at).asc())
    )


async def get_messages(db: AsyncSession, session_id: UUID) -> list[ChatMessage]:
    """Retrieves all *visible* ChatMessages for a session.

    Excluded messages (``exclude_from_context=True``) are filtered out — this
    is the list shown to the end user.  Summary messages (``is_summary=True``)
    are included so the UI can render them.

    To get the context window sent to the LLM, use
    :func:`get_messages_for_llm` instead.
    """
    logger.debug("loading_messages session_id={}", session_id)
    try:
        db_messages = (await db.exec(_visible_messages_stmt(session_id))).all()
        logger.debug(
            "messages_fetched session_id={} count={}", session_id, len(db_messages)
        )
        # Me run in thread — _deserialize_messages does disk I/O for image hydration
        return await asyncio.to_thread(_deserialize_messages, db_messages)
    except Exception as e:
        logger.error("load_messages_failed session_id={} error={}", session_id, e)
        raise


async def get_messages_for_llm(db: AsyncSession, session_id: UUID) -> list[ChatMessage]:
    """Return the message window that should be sent to the LLM.

    Strategy
    --------
    1. Find the most recent ``is_summary=True`` message.
    2. If one exists, return ``[latest_summary] + [non-hidden, non-summary
       messages ordered by created_at]``.  This correctly handles:
       - Multiple summaries: only the latest is prepended; older summary rows
         are excluded by the ``not is_summary`` filter.
       - ``keep_last_n`` messages: they were not hidden so they appear after
         the summary in chronological order, even though their ``created_at``
         is earlier than the summary's.
       - Fresh messages added after the summary: included in order.
    3. If no summary exists, fall back to all visible (non-hidden) messages —
       identical to :func:`get_messages`.
    """
    logger.debug("loading_llm_messages session_id={}", session_id)
    try:
        # Find the latest summary message
        summary_stmt = (
            select(SessionMessage)
            .where(col(SessionMessage.session_id) == session_id)
            .where(col(SessionMessage.is_summary))
            .order_by(col(SessionMessage.created_at).desc())
            .limit(1)
        )
        latest_summary = (await db.exec(summary_stmt)).first()

        if latest_summary is None:
            # No summary yet — use all visible messages
            return await get_messages(db, session_id)

        # Fetch all non-hidden, non-summary messages.  This naturally includes:
        #   - keep_last_n messages (not hidden, created before the summary)
        #   - fresh messages added after the summary
        # It excludes:
        #   - hidden messages (superseded by the summary)
        #   - other summary rows (older summaries are also excluded)
        #   - the latest summary itself (prepended explicitly below)
        rest_stmt = _visible_messages_stmt(session_id).where(
            ~col(SessionMessage.is_summary)
        )
        rest_messages = list((await db.exec(rest_stmt)).all())

        db_messages = [latest_summary] + rest_messages

        logger.debug(
            "llm_messages_fetched session_id={} count={} summary_id={}",
            session_id,
            len(db_messages),
            latest_summary.id,
        )
        # Me run in thread — _deserialize_messages does disk I/O for image hydration
        return await asyncio.to_thread(_deserialize_messages, db_messages)
    except Exception as e:
        logger.error("load_llm_messages_failed session_id={} error={}", session_id, e)
        raise


async def exclude_messages_before_summary(
    db: AsyncSession,
    session_id: UUID,
    summary_message_id: UUID,
    keep_last_n: int = 0,
) -> int:
    """Mark messages older than ``summary_message_id`` as excluded from context.

    Excludes:
    - All previous ``is_summary=True`` rows (superseded summaries).
    - All regular (non-summary) messages created before the new summary,
      except the last ``keep_last_n`` which are kept verbatim.

    When ``keep_last_n > 0``, the *most recent* ``keep_last_n`` visible
    non-summary messages created **before** the summary are preserved so
    they remain in the LLM context window alongside the new summary.

    Returns the total number of messages excluded.
    """
    # Me fetch summary row to get its created_at timestamp
    summary_msg = await db.get(SessionMessage, summary_message_id)
    if summary_msg is None:
        logger.warning(
            "exclude_messages_before_summary_not_found summary_id={}",
            summary_message_id,
        )
        return 0

    # ── Exclude all previous summaries (superseded by the new one) ──────
    old_summaries_stmt = (
        select(SessionMessage)
        .where(col(SessionMessage.session_id) == session_id)
        .where(col(SessionMessage.is_summary))
        .where(col(SessionMessage.id) != summary_message_id)
        .where(~col(SessionMessage.exclude_from_context))
    )
    old_summaries = list((await db.exec(old_summaries_stmt)).all())
    for row in old_summaries:
        row.exclude_from_context = True
        db.add(row)

    # ── Exclude regular messages before the summary ──────────────────────
    # All visible non-summary messages created before the summary, oldest-first.
    stmt = (
        select(SessionMessage)
        .where(col(SessionMessage.session_id) == session_id)
        .where(
            or_(
                col(SessionMessage.created_at) < summary_msg.created_at,
                and_(
                    col(SessionMessage.created_at) == summary_msg.created_at,
                    col(SessionMessage.id) != summary_msg.id,
                    ~col(SessionMessage.is_summary),
                ),
            )
        )
        .where(~col(SessionMessage.exclude_from_context))
        .where(~col(SessionMessage.is_summary))
        .order_by(col(SessionMessage.created_at).asc())
    )
    rows = list((await db.exec(stmt)).all())

    # Me spare the tail when keep_last_n set
    if keep_last_n > 0 and len(rows) > keep_last_n:
        rows_to_exclude = rows[:-keep_last_n]
    else:
        rows_to_exclude = rows if keep_last_n == 0 else []

    for row in rows_to_exclude:
        row.exclude_from_context = True
        db.add(row)

    await db.flush()
    total_excluded = len(old_summaries) + len(rows_to_exclude)
    logger.info(
        "messages_excluded session_id={} count={} old_summaries={} kept={} before_summary={}",
        session_id,
        total_excluded,
        len(old_summaries),
        len(rows) - len(rows_to_exclude),
        summary_message_id,
    )
    return total_excluded


# Me keep backward-compat alias during transition
hide_messages_before_summary = exclude_messages_before_summary


# ── Session CRUD ─────────────────────────────────────────────────────────────


async def list_sessions_page(
    db: AsyncSession,
    *,
    before: str | None = None,
    limit: int = 20,
) -> tuple[list[ChatSession], str | None, bool]:
    """Return a cursor-paginated page of top-level sessions (newest-first).

    Top-level sessions are those without a ``parent_session_id`` (team leads
    and scheduled tasks). Sub-sessions are excluded.

    Args:
        db: Async database session.
        before: ISO 8601 ``created_at`` cursor — return sessions older than this.
        limit: Maximum number of sessions to return (1–100).

    Returns:
        A tuple of ``(sessions, next_cursor, has_more)`` where ``next_cursor``
        is the ISO 8601 ``created_at`` of the last session on this page, or
        ``None`` if this is the last page.

    Raises:
        ValueError: If *before* is not a valid ISO 8601 datetime string.
    """
    stmt = (
        select(ChatSession)
        .where(col(ChatSession.parent_session_id).is_(None))
        .order_by(col(ChatSession.created_at).desc())
    )

    if before:
        cursor_dt = datetime.fromisoformat(before.replace("Z", "+00:00"))
        stmt = stmt.where(col(ChatSession.created_at) < cursor_dt)

    rows = (await db.exec(stmt.limit(limit + 1))).all()

    has_more = len(rows) > limit
    rows = list(rows[:limit])

    next_cursor: str | None = None
    if has_more and rows:
        last_created = rows[-1].created_at
        if last_created is not None:
            if last_created.tzinfo is None:
                last_created = last_created.replace(tzinfo=timezone.utc)
            next_cursor = last_created.isoformat().replace("+00:00", "Z")

    return rows, next_cursor, has_more


async def delete_session(db: AsyncSession, session_id: UUID) -> bool:
    """Delete a session, all its messages, and associated on-disk artifacts.

    Deletes the ``ChatSession`` row plus all ``SessionMessage`` children inside
    a single transaction, then removes the uploads and workspace directories
    from disk (outside the transaction — best-effort).

    Args:
        db: Async database session.
        session_id: UUID of the session to delete.

    Returns:
        ``True`` if the session existed and was deleted, ``False`` if not found.
    """
    async with db.begin():
        session = await db.get(ChatSession, session_id)
        if not session:
            return False
        messages = (
            await db.exec(
                select(SessionMessage).where(
                    col(SessionMessage.session_id) == session_id
                )
            )
        ).all()
        for msg in messages:
            await db.delete(msg)
        await db.delete(session)

    sid_str = str(session_id)
    uploads = uploads_dir(sid_str)
    if uploads.exists():
        await asyncio.to_thread(shutil.rmtree, uploads, ignore_errors=True)
        logger.info("uploads_dir_deleted session_id={}", session_id)

    workspace = workspace_dir(sid_str)
    if workspace.exists():
        await asyncio.to_thread(shutil.rmtree, workspace, ignore_errors=True)
        logger.info("workspace_dir_deleted session_id={}", session_id)

    logger.info("session_deleted session_id={}", session_id)
    return True


class TeamHistoryMemberData(NamedTuple):
    """One sub-session and its paginated, non-summary messages."""

    session: ChatSession
    messages: list[SessionMessage]


class TeamHistoryData(NamedTuple):
    """Full history payload for a team lead session.

    Returned by :func:`get_team_history`.
    """

    lead_session: ChatSession
    lead_messages: list[SessionMessage]
    members: list[TeamHistoryMemberData]


async def get_team_history(
    db: AsyncSession,
    lead_session_id: UUID,
    *,
    offset: int = 0,
    limit: int = 200,
) -> TeamHistoryData | None:
    """Fetch full history for a team lead session and all its sub-sessions.

    Args:
        db: Async database session.
        lead_session_id: UUID of the lead (top-level) session.
        offset: Pagination offset applied to each message query.
        limit: Pagination limit applied to each message query.

    Returns:
        A :class:`TeamHistoryData` with the lead session, its non-summary
        paginated messages, and one :class:`TeamHistoryMemberData` per child
        session. Returns ``None`` if the lead session does not exist.
    """
    lead_session = await db.get(ChatSession, lead_session_id)
    if lead_session is None:
        return None

    lead_msgs = (
        await db.exec(
            select(SessionMessage)
            .where(col(SessionMessage.session_id) == lead_session_id)
            .where(not_(SessionMessage.is_summary))
            .order_by(col(SessionMessage.created_at).asc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    sub_sessions = (
        await db.exec(
            select(ChatSession)
            .where(col(ChatSession.parent_session_id) == lead_session_id)
            .order_by(col(ChatSession.created_at).asc())
        )
    ).all()

    # TODO: N+1 — issues one message query per sub-session.  Replace with a
    # single ``WHERE session_id IN (...)`` query and group in Python once
    # offset/limit semantics per sub-session are no longer needed (or pushed
    # to the API layer as a single global cursor).
    members: list[TeamHistoryMemberData] = []
    for sub in sub_sessions:
        member_msgs = (
            await db.exec(
                select(SessionMessage)
                .where(col(SessionMessage.session_id) == sub.id)
                .where(not_(SessionMessage.is_summary))
                .order_by(col(SessionMessage.created_at).asc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
        members.append(TeamHistoryMemberData(session=sub, messages=list(member_msgs)))

    return TeamHistoryData(
        lead_session=lead_session,
        lead_messages=list(lead_msgs),
        members=members,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────


def _deserialize_messages(db_messages: Sequence[SessionMessage]) -> list[ChatMessage]:
    """Convert ORM rows into typed ChatMessage objects via TypeAdapter.

    Uses ``model_dump()`` → ``TypeAdapter.validate_python()`` so the
    discriminated union on ``role`` picks the right subclass automatically.
    ``BaseMessage.model_config = ConfigDict(extra="ignore")`` drops DB-only
    columns (``id``, ``session_id``, ``created_at``).

    For user messages with file attachments (stored in extra.attachments),
    re-hydrates ``parts`` from disk so the LLM sees images in every turn.

    Rows with unrecognised ``role`` values are silently skipped with a warning.
    """
    result: list[ChatMessage] = []
    for m in db_messages:
        try:
            d = m.model_dump()
            # Me coerce None → "" so ToolMessage(tool_call_id: str) no explode
            if d.get("tool_call_id") is None:
                d["tool_call_id"] = ""
            msg = _chat_message_adapter.validate_python(d)
            # Me stash DB row PK so checkpointer can do reliable PK lookups
            msg.db_id = m.id

            # Me re-hydrate multimodal parts for user messages that have file attachments
            if isinstance(msg, HumanMessage) and m.extra:
                attachments = m.extra.get("attachments")
                if attachments and isinstance(attachments, list):
                    parts = _build_parts(msg.content or "", attachments)
                    if parts:
                        msg.parts = parts

            result.append(msg)
        except Exception:
            # Me skip rows with unknown role — no crash the caller
            logger.warning(
                "deserialize_skip_unknown_role session_id={} message_id={} role={}",
                m.session_id,
                m.id,
                m.role,
            )

    # Strip tool calls whose arguments are not valid JSON — this happens when
    # the user interrupts the agent mid-stream before the LLM has finished
    # emitting the arguments. The partial JSON is persisted to the DB and would
    # cause a JSONDecodeError on the next turn when tool_executor tries to parse
    # it. Drop the bad tool calls from the assistant message and remove any
    # orphaned ToolMessage results that reference them.
    bad_tool_call_ids: set[str] = set()
    for msg in result:
        if not isinstance(msg, AssistantMessage) or not msg.tool_calls:
            continue
        clean: list = []
        for tc in msg.tool_calls:
            try:
                json.loads(tc.function.arguments)
                clean.append(tc)
            except (json.JSONDecodeError, ValueError):
                bad_tool_call_ids.add(tc.id)
                logger.warning(
                    "deserialize_drop_partial_tool_call tool={} id={} args_prefix={!r}",
                    tc.function.name,
                    tc.id,
                    tc.function.arguments[:80],
                )
        if len(clean) != len(msg.tool_calls):
            msg.tool_calls = clean or None

    if bad_tool_call_ids:
        result = [
            m for m in result
            if not (
                isinstance(m, ToolMessage)
                and m.tool_call_id in bad_tool_call_ids
            )
        ]

    return result


def _build_parts(text: str, attachments: list[dict]) -> list | None:
    """Build LLM content parts from persisted attachment metadata.

    Uses ``build_parts_from_metas`` (fast path: ``converted_text`` in meta,
    slow path: read from ``att["path"]`` for images / native-PDF documents).

    Returns None if only the trailing user-text block would be produced
    (i.e. no file content — no point setting HumanMessage.parts in that case).
    """
    parts = build_parts_from_metas(text, attachments)
    # build_parts_from_metas always appends a trailing TextBlock for `text`.
    # If no file blocks were produced (all attachments missing), skip parts.
    has_file_blocks = any(
        not (hasattr(p, "text") and getattr(p, "text") == text) for p in parts
    )
    return parts if has_file_blocks else None
