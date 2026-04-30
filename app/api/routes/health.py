"""Health probes.

Two separate endpoints so orchestrators can distinguish "is the process
alive?" from "is it ready to serve traffic?":

- ``GET /api/health/live``   → always 200 if the process is up.
- ``GET /api/health/ready``  → 200 only when DB + team are ready; 503 otherwise.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_session
from app.core.version import VERSION
from app.services import team_manager

router = APIRouter()


@router.get("/live")
async def health_live() -> dict:
    """Liveness probe — returns 200 as long as the event loop is alive.

    Never touches the DB; safe for high-frequency orchestrator polling.
    """
    return {"status": "ok", "version": VERSION}


async def _check_ready(session: AsyncSession) -> dict:
    checks: dict[str, str] = {}

    # ── DB ────────────────────────────────────────────────────────────────
    # ``session.exec`` overloads only cover Select/UpdateBase, so a raw
    # ``text(...)`` SELECT 1 ping doesn't match — works at runtime via the
    # SQLAlchemy passthrough but the type checker can't see it.
    try:
        await session.exec(text("SELECT 1"))  # ty: ignore[no-matching-overload]
        checks["db"] = "ok"
    except SQLAlchemyError as exc:
        logger.warning("health_ready_db_failed error={}", exc)
        checks["db"] = "fail"

    # ── Team ──────────────────────────────────────────────────────────────
    checks["team"] = "ok" if team_manager.current_team() is not None else "missing"

    ready = checks["db"] == "ok"  # team "missing" is tolerable (empty agents dir)
    return {
        "status": "ok" if ready else "degraded",
        "version": VERSION,
        "checks": checks,
    }


@router.get("/ready")
async def health_ready(session: AsyncSession = Depends(get_session)) -> dict:
    """Readiness probe — 200 when dependencies are healthy, 503 otherwise."""
    result = await _check_ready(session)
    if result["status"] != "ok":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result,
        )
    return result
