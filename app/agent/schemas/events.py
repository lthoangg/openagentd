"""Native SSE event schemas for OpenAgentd streaming API.

Each event is serialised as::

    event: <type>
    data: <json>

The ``type`` field inside the JSON body mirrors the SSE ``event:`` line so
clients that parse only the ``data:`` payload can still distinguish events.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SessionEvent(BaseModel):
    """Emitted once at the start of a stream with the resolved session id."""

    type: Literal["session"] = "session"
    session_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ThinkingEvent(BaseModel):
    """A reasoning/thinking chunk from an agent."""

    type: Literal["thinking"] = "thinking"
    agent: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageEvent(BaseModel):
    """A content chunk from an agent."""

    type: Literal["message"] = "message"
    agent: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCallEvent(BaseModel):
    """First appearance of a tool call in the model delta stream.

    Emitted as soon as the LLM names a tool — before arguments are fully
    streamed and before execution begins.  Use this to show a pending tool
    card immediately.  Arguments may be absent or incomplete at this point.
    """

    type: Literal["tool_call"] = "tool_call"
    agent: str
    tool_call_id: str | None = None  # LLM-assigned call ID
    name: str  # internal function name
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolStartEvent(BaseModel):
    """Tool execution is about to begin — arguments are fully assembled.

    Emitted immediately before the tool function is called.  At this point
    the full arguments JSON is available.
    """

    type: Literal["tool_start"] = "tool_start"
    agent: str
    tool_call_id: str | None = None  # matches the tool_call event
    name: str  # internal function name
    arguments: str | None = None  # complete JSON arguments string
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolEndEvent(BaseModel):
    """Tool execution has completed."""

    type: Literal["tool_end"] = "tool_end"
    agent: str
    tool_call_id: str | None = None  # matches tool_call / tool_start
    name: str  # internal function name
    result: str | None = (
        None  # tool output (full; large results handled by ToolResultOffloadHook)
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class UsageEvent(BaseModel):
    """Token usage for a model call or turn."""

    type: Literal["usage"] = "usage"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int | None = None
    thoughts_tokens: int | None = None
    tool_use_tokens: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DoneEvent(BaseModel):
    """Stream complete."""

    type: Literal["done"] = "done"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RateLimitEvent(BaseModel):
    """Provider is rate-limited; client should retry after ``retry_after`` seconds."""

    type: Literal["rate_limit"] = "rate_limit"
    retry_after: int  # seconds until quota resets
    attempt: int  # current attempt number (1-based)
    max_attempts: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class ErrorEvent(BaseModel):
    """An unrecoverable error occurred."""

    type: Literal["error"] = "error"
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentStatusEvent(BaseModel):
    """An agent changed lifecycle state (working / available / error)."""

    type: Literal["agent_status"] = "agent_status"
    agent: str
    status: Literal["working", "available", "error"]
    metadata: dict[str, Any] = Field(default_factory=dict)


class TitleUpdateEvent(BaseModel):
    """Session title was generated and saved."""

    type: Literal["title_update"] = "title_update"
    title: str


class PermissionAskedEvent(BaseModel):
    """An agent is requesting permission to run a tool call.

    The frontend should display an approval UI and POST a reply to
    ``/team/{session_id}/permissions/{request_id}/reply``.
    """

    type: Literal["permission_asked"] = "permission_asked"
    request_id: str  # UUID — use as key in the reply endpoint
    session_id: str
    tool: str  # tool name (e.g. "shell", "bash")
    patterns: list[str]  # command fragments / path globs being requested
    metadata: dict[str, Any] = Field(default_factory=dict)


class PermissionRepliedEvent(BaseModel):
    """A permission request was resolved (by user or auto-allow)."""

    type: Literal["permission_replied"] = "permission_replied"
    request_id: str
    session_id: str
    reply: str  # "once" | "always" | "reject"
    metadata: dict[str, Any] = Field(default_factory=dict)
