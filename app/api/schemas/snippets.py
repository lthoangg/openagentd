"""Request and response schemas for ``/api/snippets`` endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SnippetSummary(BaseModel):
    name: str
    description: str = ""
    source: str = Field(
        description=(
            "Origin root: project-openagentd / project-agents / "
            "global-openagentd / global-agents."
        ),
    )


class SnippetListResponse(BaseModel):
    snippets: list[SnippetSummary]


class SnippetRenderResponse(BaseModel):
    name: str
    content: str = Field(description="Snippet body, ready to insert into the composer.")
