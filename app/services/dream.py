"""Dream service — consolidate wiki from unprocessed sessions and notes.

Dream reads unprocessed chat sessions and note files, runs the dream agent
over each one, and writes to wiki/topics/, wiki/USER.md, wiki/INDEX.md.

The dream agent is loaded from .openagentd/config/dream.md.  If that file is
missing, has no ``model:`` field, or ``enabled: false``, synthesis is skipped
and items are still marked as processed (infrastructure-only mode).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from loguru import logger
from pydantic import BaseModel, model_validator
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.chat import ChatSession, DreamLog, DreamNotesLog, SessionMessage
from app.services.wiki import NOTES_DIR, TOPICS_DIR, wiki_root

if TYPE_CHECKING:
    from app.agent.agent_loop import Agent

_FRONTMATTER_RE = re.compile(r"^\s*---\r?\n(.*?)\r?\n---\r?\n?(.*)", re.DOTALL)

# ── Dream config schema ───────────────────────────────────────────────────────

# Tools always injected into the dream agent regardless of dream.md listing.
_REQUIRED_TOOLS: list[str] = ["read", "write", "ls", "wiki_search"]


class DreamAgentConfig(BaseModel):
    """Parsed configuration from dream.md.

    Extends the agent frontmatter schema with dream-specific fields
    (``enabled``, ``schedule``).  Dream.md is NOT a regular agent file —
    it has its own loader so these fields are first-class, not silently
    ignored extras.
    """

    # ── Agent identity (mirrors AgentConfig subset) ──
    name: str = "dream"
    model: str | None = None
    description: str | None = None
    temperature: float | None = None
    thinking_level: str | None = None
    tools: list[str] = []
    system_prompt: str = ""

    # ── Dream-specific ────────────────────────────────
    enabled: bool = False
    schedule: str = "0 2 * * *"
    batch_size: int = 1
    """Number of sessions/notes to process per run_dream() call.

    Defaults to 1 — each scheduler fire (or manual /dream/run trigger)
    processes exactly one item with a fresh agent instance.  Increase for
    bulk catch-up runs, but keep small enough that the LLM context stays
    focused on one conversation at a time.
    """

    @model_validator(mode="after")
    def _inject_required_tools(self) -> "DreamAgentConfig":
        for tool in _REQUIRED_TOOLS:
            if tool not in self.tools:
                self.tools.append(tool)
        return self

    @model_validator(mode="after")
    def _validate_model(self) -> "DreamAgentConfig":
        if self.model and ":" not in self.model:
            raise ValueError(
                f"Dream model '{self.model}' must be 'provider:model' "
                "(e.g. 'googlegenai:gemini-2.0-flash')."
            )
        return self


def parse_dream_md(path: Path) -> DreamAgentConfig:
    """Parse dream.md into a :class:`DreamAgentConfig`.

    dream.md uses the same ``---\\nyaml\\n---\\nbody`` format as agent files,
    with the body becoming the system prompt and two extra frontmatter keys:
    ``enabled`` (bool) and ``schedule`` (cron string).

    Raises :exc:`ValueError` when the file is missing a frontmatter block or
    the YAML is invalid.
    """
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError(
            f"dream.md at '{path}' is missing YAML frontmatter "
            "(expected '---\\n<yaml>\\n---\\n<system prompt>')."
        )
    try:
        raw: dict = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"dream.md YAML parse error: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("dream.md frontmatter must be a YAML mapping.")

    raw["system_prompt"] = m.group(2).strip() or "You are the dream agent."

    # name defaults to "dream" if not set in the file
    raw.setdefault("name", "dream")

    return DreamAgentConfig.model_validate(raw)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def get_unprocessed_sessions(db: AsyncSession) -> list[ChatSession]:
    """Return sessions not yet in dream_log, excluding sessions with no messages."""
    processed_ids_result = await db.exec(select(DreamLog.session_id))
    processed_ids = set(processed_ids_result.all())

    all_sessions_result = await db.exec(select(ChatSession))
    all_sessions = all_sessions_result.all()

    unprocessed = [s for s in all_sessions if s.id not in processed_ids]

    # Pre-filter sessions that have no meaningful messages — mark them
    # processed immediately so they never consume a batch slot.
    empty: list[ChatSession] = []
    non_empty: list[ChatSession] = []
    for session in unprocessed:
        stmt = (
            select(SessionMessage)
            .where(col(SessionMessage.session_id) == session.id)
            .where(~col(SessionMessage.exclude_from_context))
            .where(col(SessionMessage.role) != "system")
            .limit(1)
        )
        has_messages = bool((await db.exec(stmt)).first())
        if has_messages:
            non_empty.append(session)
        else:
            empty.append(session)

    if empty:
        for session in empty:
            log = DreamLog(
                session_id=session.id,
                processed_at=datetime.now(timezone.utc),
                agent_name=session.agent_name or "unknown",
                topics_written=None,
            )
            db.add(log)
        await db.flush()
        logger.info("dream_skipped_empty_sessions count={}", len(empty))

    return non_empty


async def get_unprocessed_notes(db: AsyncSession) -> list[str]:
    """Return note filenames not yet in dream_notes_log."""
    root = wiki_root()
    notes_dir = root / NOTES_DIR
    if not notes_dir.is_dir():
        return []

    processed_result = await db.exec(select(DreamNotesLog.filename))
    processed = set(processed_result.all())

    all_notes = [
        entry.name
        for entry in sorted(notes_dir.iterdir())
        if entry.is_file() and entry.suffix == ".md"
    ]
    return [n for n in all_notes if n not in processed]


async def mark_session_processed(
    db: AsyncSession,
    session_id: uuid.UUID,
    agent_name: str,
    topics_written: list[str],
) -> None:
    """Insert row into dream_log."""
    log = DreamLog(
        session_id=session_id,
        processed_at=datetime.now(timezone.utc),
        agent_name=agent_name,
        topics_written=json.dumps(topics_written) if topics_written else None,
    )
    db.add(log)
    await db.flush()


async def mark_note_processed(db: AsyncSession, filename: str) -> None:
    """Insert row into dream_notes_log."""
    log = DreamNotesLog(
        filename=filename,
        processed_at=datetime.now(timezone.utc),
    )
    db.add(log)
    await db.flush()


# ── Dream agent loader ────────────────────────────────────────────────────────


def _load_dream_agent() -> "Agent | None":
    """Load the dream agent from dream.md.  Returns None if unavailable."""
    from app.agent.loader import AgentConfig, _build_agent, _default_tool_registry
    from app.agent.providers.factory import build_provider
    from app.agent.sandbox import SandboxConfig, set_sandbox
    from app.core.config import settings

    config_path = Path(settings.OPENAGENTD_CONFIG_DIR) / "dream.md"
    if not config_path.exists():
        logger.debug("dream_agent_skip no dream.md at path={}", config_path)
        return None

    try:
        dream_cfg = parse_dream_md(config_path)
    except ValueError as exc:
        logger.warning("dream_agent_config_parse_failed error={}", exc)
        return None

    if not dream_cfg.model:
        logger.debug("dream_agent_skip no model configured")
        return None

    # Set the sandbox workspace to wiki_root() so the dream agent's filesystem
    # tools (ls, read, write) resolve relative paths against the wiki directory.
    # Without this, get_sandbox() falls back to a temp dir and ls("wiki") fails.
    set_sandbox(SandboxConfig(workspace=str(wiki_root())))

    # Project DreamAgentConfig → AgentConfig (the agent builder's contract).
    # role is always "member" for the dream agent — it never leads a team.
    try:
        agent_cfg = AgentConfig(
            name=dream_cfg.name,
            role="member",
            description=dream_cfg.description,
            model=dream_cfg.model,
            temperature=dream_cfg.temperature,
            thinking_level=dream_cfg.thinking_level,
            tools=list(dream_cfg.tools),
            system_prompt=dream_cfg.system_prompt,
        )
    except Exception as exc:
        logger.warning("dream_agent_config_build_failed error={}", exc)
        return None

    try:
        agent = _build_agent(
            agent_cfg, _default_tool_registry(), build_provider, source_path=config_path
        )
        logger.info(
            "dream_agent_loaded model={} tools={}", dream_cfg.model, dream_cfg.tools
        )
        return agent
    except Exception as exc:
        logger.warning("dream_agent_build_failed error={}", exc)
        return None


# ── Session transcript formatter ──────────────────────────────────────────────


async def _fetch_session_transcript(db: AsyncSession, session: ChatSession) -> str:
    """Return a readable transcript of the session for the dream agent."""
    stmt = (
        select(SessionMessage)
        .where(col(SessionMessage.session_id) == session.id)
        .where(~col(SessionMessage.exclude_from_context))
        .order_by(col(SessionMessage.created_at).asc())
    )
    rows = (await db.exec(stmt)).all()

    if not rows:
        return "(empty session)"

    lines: list[str] = [
        f"Session ID: {session.id}",
        f"Agent: {session.agent_name or 'unknown'}",
        f"Created: {session.created_at}",
        "",
    ]
    for msg in rows:
        content = msg.content or ""
        if len(content) > 4000:
            content = content[:4000] + "\n[... truncated ...]"
        lines.append(f"### {msg.role.upper()}")
        lines.append(content)
        lines.append("")

    return "\n".join(lines)


# ── Topics diff helper ────────────────────────────────────────────────────────


def _topics_snapshot() -> set[str]:
    """Return current set of topic filenames in wiki/topics/."""
    topics_dir = wiki_root() / TOPICS_DIR
    if not topics_dir.is_dir():
        return set()
    return {f.name for f in topics_dir.iterdir() if f.is_file() and f.suffix == ".md"}


# ── LLM synthesis ─────────────────────────────────────────────────────────────


async def _synthesise_session(
    agent: "Agent",
    db: AsyncSession,
    session: ChatSession,
) -> list[str]:
    """Run the dream agent over one session. Returns list of new topic slugs."""
    from app.agent.schemas.agent import RunConfig
    from app.agent.schemas.chat import HumanMessage

    transcript = await _fetch_session_transcript(db, session)
    if transcript == "(empty session)":
        logger.debug("dream_session_empty session_id={}", session.id)
        return []

    prompt = (
        "Process the following conversation session and update the wiki accordingly.\n\n"
        f"{transcript}"
    )

    before = _topics_snapshot()
    try:
        await agent.run(
            [HumanMessage(content=prompt)],
            config=RunConfig(session_id=str(session.id)),
        )
    except Exception as exc:
        logger.warning(
            "dream_session_llm_failed session_id={} error={}", session.id, exc
        )
        return []

    after = _topics_snapshot()
    return sorted(Path(f).stem for f in after - before)


async def _synthesise_note(agent: "Agent", filename: str) -> list[str]:
    """Run the dream agent over one note file. Returns list of new topic slugs."""
    from app.agent.schemas.agent import RunConfig
    from app.agent.schemas.chat import HumanMessage

    note_path = wiki_root() / NOTES_DIR / filename
    try:
        content = note_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("dream_note_read_failed filename={} error={}", filename, exc)
        return []

    if not content.strip():
        return []

    prompt = (
        "Process the following note and update the wiki accordingly.\n\n"
        f"Note file: {filename}\n\n"
        f"{content}"
    )

    before = _topics_snapshot()
    try:
        await agent.run(
            [HumanMessage(content=prompt)],
            config=RunConfig(),
        )
    except Exception as exc:
        logger.warning("dream_note_llm_failed filename={} error={}", filename, exc)
        return []

    after = _topics_snapshot()
    return sorted(Path(f).stem for f in after - before)


# ── Main entry point ──────────────────────────────────────────────────────────


async def run_dream(db: AsyncSession) -> dict:
    """Process up to ``batch_size`` unprocessed items (sessions then notes).

    Each item gets its own fresh agent instance so no conversation history
    bleeds between items.  Sessions are drained before notes.

    Returns::

        {
            "sessions_processed": N,
            "notes_processed": M,
            "remaining": R,   # unprocessed items still pending after this run
        }
    """
    from app.core.config import settings

    # Parse dream.md once — used for batch_size here and agent config inside
    # _load_dream_agent().  Gracefully falls back to batch_size=1 if unavailable.
    batch_size = 1
    config_path = Path(settings.OPENAGENTD_CONFIG_DIR) / "dream.md"
    if config_path.exists():
        try:
            dream_cfg = parse_dream_md(config_path)
            batch_size = max(1, dream_cfg.batch_size)
        except ValueError:
            pass

    unprocessed_sessions = await get_unprocessed_sessions(db)
    unprocessed_notes = await get_unprocessed_notes(db)
    total_remaining = len(unprocessed_sessions) + len(unprocessed_notes)

    if total_remaining == 0:
        logger.info("dream_run_nothing_to_process")
        return {"sessions_processed": 0, "notes_processed": 0, "remaining": 0}

    logger.info(
        "dream_run_start sessions={} notes={} batch_size={}",
        len(unprocessed_sessions),
        len(unprocessed_notes),
        batch_size,
    )

    sessions_processed = 0
    notes_processed = 0

    # Sessions first, then notes fill the remaining budget.
    session_batch = unprocessed_sessions[:batch_size]
    note_budget = batch_size - len(session_batch)
    note_batch = unprocessed_notes[:note_budget]

    for session in session_batch:
        agent = _load_dream_agent()
        try:
            topics_written = (
                await _synthesise_session(agent, db, session)
                if agent is not None
                else []
            )
            await mark_session_processed(
                db,
                session_id=session.id,
                agent_name=session.agent_name or "unknown",
                topics_written=topics_written,
            )
            sessions_processed += 1
            logger.info(
                "dream_session_processed session_id={} agent={} topics={}",
                session.id,
                session.agent_name,
                topics_written,
            )
        except Exception as exc:
            logger.warning(
                "dream_session_failed session_id={} error={}", session.id, exc
            )

    for filename in note_batch:
        agent = _load_dream_agent()
        try:
            topics_written = (
                await _synthesise_note(agent, filename) if agent is not None else []
            )
            await mark_note_processed(db, filename)
            notes_processed += 1
            logger.info(
                "dream_note_processed filename={} topics={}", filename, topics_written
            )
        except Exception as exc:
            logger.warning("dream_note_failed filename={} error={}", filename, exc)

    await db.commit()

    remaining = total_remaining - sessions_processed - notes_processed
    result = {
        "sessions_processed": sessions_processed,
        "notes_processed": notes_processed,
        "remaining": remaining,
    }
    logger.info("dream_run_complete result={}", result)
    return result
