"""Wiki HTTP API — tree view and single-file CRUD over the wiki store.

All routes operate on relative paths under ``{OPENAGENTD_WIKI_DIR}/``.
Path validation happens inside :mod:`app.services.wiki`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_session
from app.services.dream import get_unprocessed_notes
from app.services.wiki import (
    WikiFileInfo,
    WikiPathError,
    read_file,
    write_file,
    delete_file,
    list_tree,
)

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────


class WikiFileInfoResponse(BaseModel):
    path: str
    description: str = ""
    updated: str | None = None
    tags: list[str] = Field(default_factory=list)


class WikiTreeResponse(BaseModel):
    system: list[WikiFileInfoResponse]
    notes: list[WikiFileInfoResponse]
    topics: list[WikiFileInfoResponse]


class WikiFileResponse(BaseModel):
    path: str
    content: str
    description: str = ""
    updated: str | None = None
    tags: list[str] = Field(default_factory=list)


class WikiWriteRequest(BaseModel):
    path: str
    content: str


# ── Routes ───────────────────────────────────────────────────────────────────


def _info(i: WikiFileInfo) -> WikiFileInfoResponse:
    return WikiFileInfoResponse(
        path=i.path,
        description=i.description,
        updated=i.updated,
        tags=list(i.tags),
    )


@router.get("/tree", response_model=WikiTreeResponse)
async def get_wiki_tree(
    unprocessed_only: bool = Query(
        False,
        description="When true, notes/ is filtered to files not yet processed by the dream agent.",
    ),
    db: AsyncSession = Depends(get_session),
) -> WikiTreeResponse:
    """Return the full wiki tree (system + notes + topics)."""
    unprocessed: set[str] | None = None
    if unprocessed_only:
        unprocessed = set(await get_unprocessed_notes(db))

    tree = list_tree(unprocessed_notes=unprocessed)
    return WikiTreeResponse(
        system=[_info(i) for i in tree.system],
        notes=[_info(i) for i in tree.notes],
        topics=[_info(i) for i in tree.topics],
    )


@router.get("/file", response_model=WikiFileResponse)
async def get_wiki_file(
    path: str = Query(description="Relative path under OPENAGENTD_WIKI_DIR."),
) -> WikiFileResponse:
    """Return raw contents of a wiki file."""
    try:
        f = read_file(path)
    except WikiPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WikiFileResponse(
        path=f.path,
        content=f.content,
        description=f.description,
        updated=f.updated,
        tags=list(f.tags),
    )


@router.put("/file", response_model=WikiFileResponse)
async def put_wiki_file(body: WikiWriteRequest) -> WikiFileResponse:
    """Create or overwrite a wiki file."""
    try:
        f = write_file(body.path, body.content)
    except WikiPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return WikiFileResponse(
        path=f.path,
        content=f.content,
        description=f.description,
        updated=f.updated,
        tags=list(f.tags),
    )


@router.delete("/file")
async def delete_wiki_file(
    path: str = Query(description="Relative path under OPENAGENTD_WIKI_DIR."),
) -> dict[str, str]:
    """Delete a wiki file."""
    try:
        delete_file(path)
    except WikiPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "ok", "path": path}
