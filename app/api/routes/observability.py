"""Observability endpoints — summary, trace list, and trace detail.

All three endpoints read the same OTEL span JSONL files via DuckDB and share
the same 503 contract when the optional ``[otel]`` extra is missing.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.services.observability_service import (
    DuckDBUnavailable,
    get_trace,
    list_traces,
    summarize,
)

router = APIRouter()


def _duckdb_unavailable(exc: DuckDBUnavailable) -> HTTPException:
    """Shared 503 factory — identical payload across endpoints."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"reason": "duckdb_unavailable", "message": str(exc)},
    )


@router.get("/summary")
async def summary(days: int = Query(default=7, ge=1, le=90)) -> dict:
    """Return span-derived aggregates over the last ``days`` days.

    Returns 503 with ``detail.reason = "duckdb_unavailable"`` when the
    optional ``[otel]`` extra is not installed; the UI shows a dedicated
    empty state in that case.
    """
    try:
        result = summarize(days=days)
    except DuckDBUnavailable as exc:
        raise _duckdb_unavailable(exc)
    return result.to_dict()


@router.get("/traces")
async def traces(
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Return a newest-first list of ``agent_run`` spans (one row per turn).

    Each item identifies a trace (``trace_id``) plus summary metrics; the UI
    uses ``trace_id`` to fetch the full span tree via ``GET /traces/{id}``.
    """
    try:
        items = list_traces(days=days, limit=limit, offset=offset)
    except DuckDBUnavailable as exc:
        raise _duckdb_unavailable(exc)
    return {
        "traces": [t.to_dict() for t in items],
        "limit": limit,
        "offset": offset,
    }


@router.get("/traces/{trace_id}")
async def trace_detail(
    trace_id: str,
    days: int = Query(default=30, ge=1, le=90),
) -> dict:
    """Return every span belonging to ``trace_id`` (start-time ordered).

    The ``days`` bound exists only to cap the JSONL scan — set it high when
    a trace is expected to be old.  Returns 404 if the trace is not found
    in the window (expired by retention or typo).
    """
    try:
        detail = get_trace(trace_id=trace_id, days=days)
    except DuckDBUnavailable as exc:
        raise _duckdb_unavailable(exc)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"reason": "trace_not_found", "trace_id": trace_id},
        )
    return detail.to_dict()
