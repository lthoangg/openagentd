"""Dream API routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.services.dream import run_dream

router = APIRouter(prefix="/dream", tags=["dream"])


# ── Config schemas ────────────────────────────────────────────────────────────


class DreamConfigResponse(BaseModel):
    content: str
    """Raw markdown content of dream.md (frontmatter + body)."""
    exists: bool
    """False when dream.md has not been created yet."""


class DreamConfigWriteRequest(BaseModel):
    content: str


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/config", response_model=DreamConfigResponse)
async def get_dream_config() -> DreamConfigResponse:
    """Return the raw contents of dream.md."""
    path = Path(settings.OPENAGENTD_CONFIG_DIR) / "dream.md"
    if not path.exists():
        return DreamConfigResponse(content="", exists=False)
    return DreamConfigResponse(content=path.read_text(encoding="utf-8"), exists=True)


@router.put("/config", response_model=DreamConfigResponse)
async def put_dream_config(
    body: DreamConfigWriteRequest,
    request: Request,
) -> DreamConfigResponse:
    """Overwrite dream.md and reload the scheduler without a restart."""
    path = Path(settings.OPENAGENTD_CONFIG_DIR) / "dream.md"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body.content, encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to write dream.md: {exc}"
        ) from exc

    # Reload the live scheduler so the new schedule / enabled flag takes
    # effect immediately — no server restart required.
    scheduler = getattr(request.app.state, "dream_scheduler", None)
    if scheduler is not None:
        await scheduler.reload()

    return DreamConfigResponse(content=body.content, exists=True)


@router.post("/run")
async def run_dream_now(db: AsyncSession = Depends(get_session)) -> dict:
    """Manually trigger the dream agent to process unprocessed sessions and notes."""
    return await run_dream(db)
