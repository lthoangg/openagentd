"""Generic ``/api/settings`` endpoints.

Currently exposes the user-editable sandbox deny-list (``sandbox.yaml``).
The list is enforced by :class:`app.agent.sandbox.SandboxConfig`, which
re-loads ``sandbox.yaml`` for each new sandbox instance — so PUTs take
effect on the next agent run without needing a restart.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.agent.sandbox_config import SandboxFileConfig, load_config, save_config

router = APIRouter()


class SandboxSettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    denied_patterns: list[str] = Field(default_factory=list)


@router.get("/sandbox")
async def get_sandbox_settings() -> SandboxSettingsBody:
    """Return the current sandbox deny-list.

    On first run this seeds ``sandbox.yaml`` with sensible defaults
    (``**/.env``, ``**/.env.*``).
    """
    try:
        cfg = load_config()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SandboxSettingsBody(denied_patterns=list(cfg.denied_patterns))


@router.put("/sandbox")
async def update_sandbox_settings(body: SandboxSettingsBody) -> SandboxSettingsBody:
    """Replace the sandbox deny-list with the supplied glob patterns."""
    cleaned = [p.strip() for p in body.denied_patterns if p.strip()]
    save_config(SandboxFileConfig(denied_patterns=cleaned))
    return SandboxSettingsBody(denied_patterns=cleaned)
