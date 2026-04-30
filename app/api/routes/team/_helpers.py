"""Shared helpers for the /team route package.

File upload and team-dispatch logic live in ``app.services.agent_service``
(transport-neutral, shared with future channel adapters).  The route
modules only handle HTTP concerns.
"""

from __future__ import annotations

from fastapi import HTTPException, UploadFile

from app.agent.mode.team.team import AgentTeam
from app.api.schemas.sessions import MessageResponse
from app.services import agent_service
from app.services.agent_service import NoTeamConfigured, RawAttachment


# Server-internal attachment fields that must never leak to clients:
# - ``converted_text``: extracted document body, sent to the LLM only.
# - ``path``: absolute on-disk path, used for rehydration; clients fetch
#   bytes via ``GET /api/team/{sid}/uploads/{filename}`` instead.
_INTERNAL_ATTACHMENT_FIELDS = frozenset({"converted_text", "path"})


def _message_response(m) -> MessageResponse:
    resp = MessageResponse.model_validate(m)
    if m.extra and isinstance(m.extra.get("attachments"), list):
        resp.attachments = [
            {k: v for k, v in att.items() if k not in _INTERNAL_ATTACHMENT_FIELDS}
            for att in m.extra["attachments"]
        ]
        resp.file_message = True
    return resp


def _require_team(team: AgentTeam | None) -> AgentTeam:
    try:
        return agent_service.require_team(team)
    except NoTeamConfigured as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _read_upload_as_attachment(file: UploadFile) -> RawAttachment | None:
    """Materialise an ``UploadFile`` into a transport-neutral ``RawAttachment``.

    Returns ``None`` for files with no filename (skipped, matches prior
    behaviour).
    """
    if not file.filename:
        return None
    data = await file.read()
    return RawAttachment(
        filename=file.filename,
        content_type=file.content_type,
        data=data,
    )
