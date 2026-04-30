"""Uploads, workspace media proxy, and flat workspace file listing.

Two endpoints, one root (see :mod:`app.core.paths`):

- ``GET /api/team/{sid}/uploads/{filename}`` →
  ``{OPENAGENTD_WORKSPACE_DIR}/{sid}/uploads/{filename}``
  User-uploaded attachments. Flat namespace (UUID-named by the uploader).

- ``GET /api/team/{sid}/media/{path}`` → ``{OPENAGENTD_WORKSPACE_DIR}/{sid}/{path}``
  Agent workspace output (files written by the write/shell tools). Nested
  paths allowed. Target of bare markdown image refs rendered by the
  assistant: ``![alt](chart.png)`` → ``/api/team/{sid}/media/chart.png``.

``GET /api/team/{sid}/files`` provides a flat recursive listing of the
agent workspace — powers the "Artifacts" panel in the web UI.
"""

from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.api.schemas.team import WorkspaceFileInfo, WorkspaceFilesResponse
from app.core.paths import uploads_dir, workspace_dir

router = APIRouter()


# ── Path-safety helpers ───────────────────────────────────────────────────────


def _safe_resolve(root: Path, rel: str) -> Path:
    """Resolve ``rel`` under ``root`` with traversal protection.

    Raises ``HTTPException(400)`` on traversal attempts (``..``, absolute
    paths, symlink escapes) and on empty paths.  Raises ``HTTPException(404)``
    when the resolved target does not exist or is not a regular file.
    """
    if not rel or rel.strip() == "":
        raise HTTPException(status_code=400, detail="Empty media path.")

    # Reject absolute paths and Windows drive letters early.
    candidate = Path(rel)
    if candidate.is_absolute() or (len(rel) >= 2 and rel[1] == ":"):
        raise HTTPException(status_code=400, detail="Absolute media paths rejected.")

    try:
        resolved = (root / candidate).resolve(strict=False)
        root_resolved = root.resolve(strict=False)
    except (OSError, RuntimeError):
        raise HTTPException(status_code=400, detail="Invalid media path.")

    # Containment check — fails on ``..`` escapes and symlinks pointing outside.
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise HTTPException(status_code=400, detail="Media path escapes session root.")

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Media file not found.")

    return resolved


def _guess_media_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/{session_id}/uploads/{filename}")
async def get_uploaded_file(session_id: str, filename: str) -> FileResponse:
    """Serve a user-uploaded attachment from the session's uploads dir.

    Flat namespace — ``filename`` must not contain path separators.
    """
    # Reject anything that looks like a path — uploads are flat.
    if "/" in filename or "\\" in filename or filename in ("", ".", ".."):
        raise HTTPException(status_code=400, detail="Invalid upload filename.")

    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session id.")

    resolved = _safe_resolve(uploads_dir(session_id), filename)
    return FileResponse(
        path=str(resolved),
        media_type=_guess_media_type(resolved),
        filename=resolved.name,
    )


@router.get("/{session_id}/media/{file_path:path}")
async def get_workspace_media(session_id: str, file_path: str) -> FileResponse:
    """Serve a file from the session's agent workspace.

    Supports nested subpaths (e.g. ``output/chart.png``).  Path traversal is
    rejected; symlink escapes outside the workspace root are rejected via
    containment check on the resolved path.
    """
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session id.")

    resolved = _safe_resolve(workspace_dir(session_id), file_path)
    return FileResponse(
        path=str(resolved),
        media_type=_guess_media_type(resolved),
        filename=resolved.name,
    )


# ── Workspace file listing ────────────────────────────────────────────────────
#
# Flat recursive listing of the agent workspace.
# Design choices:
#   - Flat list (not tree) — the UI groups by directory, keeps payload simple.
#   - Regular files only (no dirs, no symlinks leaving the root).
#   - Paths are relative (POSIX separators) — safe to pass back to ``/media/``.
#   - Size cap on the walk to avoid pathological workspaces blowing up the
#     response.  Beyond the cap we truncate and flag it.

_MAX_FILES_LISTED = 500


@router.get("/{session_id}/files", response_model=WorkspaceFilesResponse)
async def list_workspace_files(session_id: str) -> WorkspaceFilesResponse:
    """List every file under the session's agent workspace, recursively.

    Returns an empty list when the workspace directory does not yet exist
    (fresh session — no tool has written anything).  Hidden dotfiles are
    skipped; symlinks pointing outside the workspace root are skipped.
    """
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session id.")

    root = workspace_dir(session_id)
    if not root.exists() or not root.is_dir():
        return WorkspaceFilesResponse(session_id=session_id, files=[], truncated=False)

    root_resolved = root.resolve(strict=False)
    files: list[WorkspaceFileInfo] = []
    truncated = False

    # ``Path.rglob`` follows into subdirs; we filter out dotfiles and skip any
    # entry whose resolved path escapes the workspace root (symlink guard).
    for entry in sorted(root.rglob("*")):
        if len(files) >= _MAX_FILES_LISTED:
            truncated = True
            break
        # Skip dotfiles/dotdirs at any depth.
        if any(part.startswith(".") for part in entry.relative_to(root).parts):
            continue
        if not entry.is_file():
            continue
        try:
            resolved = entry.resolve(strict=False)
            resolved.relative_to(root_resolved)
        except (OSError, ValueError):
            continue  # Symlink escape or broken entry — skip.
        try:
            stat = entry.stat()
        except OSError:
            continue
        rel = entry.relative_to(root).as_posix()
        mime, _ = mimetypes.guess_type(str(entry))
        files.append(
            WorkspaceFileInfo(
                path=rel,
                name=entry.name,
                size=stat.st_size,
                mtime=stat.st_mtime,
                mime=mime or "application/octet-stream",
            )
        )

    return WorkspaceFilesResponse(
        session_id=session_id, files=files, truncated=truncated
    )
