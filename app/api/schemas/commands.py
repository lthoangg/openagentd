"""Request and response schemas for ``/api/commands`` endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CommandSummary(BaseModel):
    name: str
    description: str = ""
    source: str = Field(
        description=(
            "Origin root: project-openagentd / project-agents / project-opencode / "
            "global-openagentd / global-agents / global-opencode."
        ),
    )


class CommandListResponse(BaseModel):
    commands: list[CommandSummary]


class CommandRenderRequest(BaseModel):
    arguments: str = Field(default="", description="Text typed after the command name.")


class CommandRenderResponse(BaseModel):
    name: str
    content: str = Field(
        description="Rendered command body, ready to send as a user message."
    )
