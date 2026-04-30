"""Request and response schemas for ``/api/skills`` endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SkillSummary(BaseModel):
    name: str
    description: str = ""
    valid: bool = True
    error: str | None = None


class SkillDetail(BaseModel):
    name: str
    path: str
    content: str
    description: str = ""
    error: str | None = None


class SkillWriteRequest(BaseModel):
    name: str = Field(description="Skill name (directory name).")
    content: str = Field(description="Full SKILL.md contents.")


class SkillListResponse(BaseModel):
    skills: list[SkillSummary]


class SkillDeleteResponse(BaseModel):
    name: str
