"""Quote of the day endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.services.quote_service import get_quote_of_the_day

router = APIRouter()


@router.get("")
async def quote_of_the_day():
    """Return today's quote, cached for the whole day."""
    q = await get_quote_of_the_day()
    return {"quote": q.quote, "author": q.author}
