"""Team chat, SSE stream, agent listing, session CRUD, and history."""

from __future__ import annotations

from typing import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.agent.agent_loop import Agent
from app.agent.mode.team.member import TeamMemberBase
from app.agent.tools.builtin.skill import discover_skills
from app.api.deps import ChatFormDep, DbSession, TeamDep
from app.api.routes.team._helpers import (
    _message_response,
    _read_upload_as_attachment,
    _require_team,
)
from app.api.schemas.sessions import (
    SessionDetailResponse,
    SessionPageResponse,
    SessionResponse,
)
from app.api.schemas.team import TeamHistoryMember, TeamHistoryResponse
from app.services import (
    agent_service,
    memory_stream_store as stream_store,
    team_manager,
)
from app.services.agent_service import AttachmentError, RawAttachment
from app.services.chat_service import (
    delete_session,
    get_team_history,
    list_sessions_page,
)

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _serialize_agent(agent: Agent, *, is_lead: bool = False) -> dict:
    """Serialize an Agent into the /team/agents response shape."""
    skill_names: list[str] = agent.skills or []
    skills: list[dict] = []
    if skill_names:
        try:
            available = discover_skills()
        except Exception:
            available = {}
        skills = [
            {"name": n, "description": available.get(n, {}).get("description", "")}
            for n in skill_names
        ]

    return {
        "name": agent.name,
        "description": agent.description or "",
        "model": agent.model_id,
        "tools": [
            {"name": t.name, "description": t.description or ""}
            for t in agent._tools.values()
        ],
        # MCP servers configured on the agent. The UI groups tools by name
        # prefix (`mcp_<server>_<tool>`) using this list. Includes servers that
        # exist in config but aren't ready (zero tools), so the UI can show
        # them as "not ready" instead of silently hiding the section.
        "mcp_servers": list(agent.mcp_servers),
        "skills": skills,
        "is_lead": is_lead,
        "capabilities": agent.capabilities.to_dict(),
    }


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/chat", status_code=202)
async def team_chat(
    team: TeamDep,
    body: ChatFormDep,
    files: list[UploadFile] = File(default=[]),
) -> dict:
    """Deliver a message to the team lead (202). Accepts multipart/form-data.

    Modes:
    - **Normal send** (``interrupt=false``, ``message`` required):
      Deliver message to team lead and start a new turn.
    - **Interrupt-only** (``interrupt=true``, ``message`` omitted):
      Cancel all working members. Partial output already saved by checkpointer.
    - **Interrupt + follow-up** (``interrupt=true``, ``message`` provided):
      Cancel working members, then deliver new message to the team lead.

    Returns the session_id. Subscribe to GET /team/stream/{session_id} to
    receive the SSE event stream (supports reconnect + replay).
    """
    team_obj = _require_team(team)

    message = body.message
    session_id = body.session_id
    interrupt = body.interrupt

    # ── Interrupt (mutually exclusive with message) ─────────────────────────
    if interrupt:
        await agent_service.interrupt_team(team_obj, session_id)
        return {"status": "interrupted", "session_id": session_id}

    # At this point message is guaranteed non-None by ChatForm validator
    assert message is not None

    # Materialise the multipart uploads into transport-neutral attachments
    # so agent_service can validate + persist them without knowing about
    # FastAPI ``UploadFile``.
    attachments: list[RawAttachment] = []
    for file in files:
        raw = await _read_upload_as_attachment(file)
        if raw is not None:
            attachments.append(raw)

    try:
        sid, n_attachments = await agent_service.dispatch_user_message(
            team_obj,
            content=message,
            session_id=session_id,
            attachments=attachments,
        )
    except AttachmentError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc

    logger.info(
        "team_chat_received session_id={} attachments={}",
        sid,
        n_attachments,
    )
    return {"status": "accepted", "session_id": sid}


@router.get("/{session_id}/stream")
async def team_stream(session_id: str, request: Request):
    """SSE stream for all team agent events.

    Replays buffered events from the current turn then delivers live events.
    Safe to reconnect — resumes from where you left off within the TTL window.
    """

    async def _gen() -> AsyncGenerator[dict, None]:
        try:
            async for event in stream_store.attach(session_id):
                if await request.is_disconnected():
                    break
                yield {
                    "event": event.get("event", "message"),
                    "data": event.get("data", "{}"),
                }
        except Exception as exc:
            logger.exception("team_stream_error type={}", type(exc).__name__)
            yield {
                "event": "error",
                "data": f'{{"type":"error","message":"stream_error:{type(exc).__name__}"}}',
            }

    return EventSourceResponse(_gen())


@router.get("/agents")
async def list_team_agents(team: TeamDep) -> dict:
    """Return info on all configured team agents (lead first, then members).

    Refreshes drifted-but-idle agents from disk before serializing so the
    capabilities panel reflects what the *next* turn will use, not the
    config that was loaded the last time the agent woke up.  Without this
    nudge the UI keeps showing the previously-active model after the user
    edits ``model:`` / ``tools:`` / ``skills:`` in the settings page until
    they happen to send another message.

    Working agents are skipped — refreshing them would race ``agent.run()``
    swapping ``self.agent`` mid-execution.  Those will pick up their edits
    via the regular start-of-turn path.
    """
    team_obj = _require_team(team)
    team_manager.refresh_idle_agents(team_obj)
    all_members: list[TeamMemberBase] = [team_obj.lead, *team_obj.members.values()]
    return {
        "agents": [
            _serialize_agent(m.agent, is_lead=(m is team_obj.lead)) for m in all_members
        ]
    }


@router.get("/sessions")
async def list_team_sessions(
    db: DbSession,
    before: str | None = Query(
        None,
        description="ISO 8601 created_at cursor — return sessions older than this.",
    ),
    limit: int = Query(20, ge=1, le=100),
) -> SessionPageResponse:
    """List team lead sessions newest-first, cursor-paginated by created_at.

    Pass ``before=<created_at_iso>`` (the ``next_cursor`` from the previous
    page) to retrieve the next batch.  Omit to start from the newest.
    """
    try:
        sessions, next_cursor, has_more = await list_sessions_page(
            db, before=before, limit=limit
        )
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Invalid 'before' cursor — expected ISO 8601 datetime.",
        )

    return SessionPageResponse(
        data=[SessionResponse.model_validate(s) for s in sessions],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_team_session(session_id: UUID, db: DbSession) -> None:
    """Delete a team session, all its messages, and uploaded files."""
    found = await delete_session(db, session_id)
    if not found:
        raise HTTPException(status_code=404, detail="Session not found.")


@router.get("/{session_id}/history")
async def team_history(
    db: DbSession,
    team: TeamDep,
    session_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
) -> TeamHistoryResponse:
    """Return full turn history: lead messages + all member messages (paginated)."""
    _require_team(team)

    history = await get_team_history(db, session_id, offset=offset, limit=limit)
    if history is None:
        raise HTTPException(status_code=404, detail="Lead session not found.")

    lead_resp = SessionResponse.model_validate(history.lead_session)
    lead_detail = SessionDetailResponse(
        **lead_resp.model_dump(),
        messages=[_message_response(m) for m in history.lead_messages],
    )

    member_histories = [
        TeamHistoryMember(
            name=member.session.agent_name or str(member.session.id),
            session_id=str(member.session.id),
            messages=[_message_response(m) for m in member.messages],
        )
        for member in history.members
    ]

    return TeamHistoryResponse(lead=lead_detail, members=member_histories)
