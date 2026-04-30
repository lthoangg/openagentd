"""Response/request models for /team endpoints.

Covers: history, workspace files, todos, and permission requests.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.api.schemas.sessions import MessageResponse, SessionDetailResponse


# ── History ──────────────────────────────────────────────────────────────────


class TeamHistoryMember(BaseModel):
    name: str
    session_id: str
    messages: list[MessageResponse]


class TeamHistoryResponse(BaseModel):
    lead: SessionDetailResponse
    members: list[TeamHistoryMember]


# ── Workspace files ──────────────────────────────────────────────────────────


class WorkspaceFileInfo(BaseModel):
    """One file in the agent workspace."""

    path: str  # Relative, POSIX-separated (e.g. "output/chart.png")
    name: str  # Basename (e.g. "chart.png")
    size: int  # Bytes
    mtime: float  # Seconds since epoch
    mime: str  # Guessed MIME type


class WorkspaceFilesResponse(BaseModel):
    """Flat recursive listing of a session's agent workspace."""

    session_id: str
    files: list[WorkspaceFileInfo]
    truncated: bool = False  # True when the walk hit the max-files cap


# ── Todos ────────────────────────────────────────────────────────────────────


class TodoItemResponse(BaseModel):
    task_id: str
    content: str
    status: str
    priority: str


class TodosResponse(BaseModel):
    todos: list[TodoItemResponse]


# ── Permissions ──────────────────────────────────────────────────────────────


class PermissionReplyRequest(BaseModel):
    """Body for replying to a pending permission request."""

    reply: str = Field(description="'once', 'always', or 'reject'")
    message: str | None = Field(
        default=None, description="Optional feedback message when rejecting."
    )


class PermissionRequestResponse(BaseModel):
    """Serialised form of a pending PermissionRequest."""

    id: str
    session_id: str
    tool: str
    patterns: list[str]
    metadata: dict
