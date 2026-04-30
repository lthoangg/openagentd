"""glob tool — find files by glob pattern (full-path or filename-only)."""

from __future__ import annotations

import asyncio
import fnmatch
import os
from pathlib import Path
from typing import Annotated

from pydantic import Field

from app.agent.sandbox import get_sandbox
from app.agent.tools.registry import Tool


async def _glob_files(
    pattern: Annotated[
        str,
        Field(
            description=(
                "Glob pattern. Use '**/*.py' or 'src/**/*.ts' to match by full path, "
                "or '*.py' with match='name' to match filename only."
            )
        ),
    ],
    directory: Annotated[
        str,
        Field(description="Search root (default '.' = workspace root)."),
    ] = ".",
    match: Annotated[
        str,
        Field(description="Match against 'path' (default) or 'name' (filename only)."),
    ] = "path",
    max_results: Annotated[
        int,
        Field(description="Maximum number of results to return (default 200)."),
    ] = 200,
) -> str:
    """Find files by glob pattern. match='path' matches the full relative path (supports **); match='name' matches filename only."""
    sandbox = get_sandbox()
    resolved = sandbox.validate_path(directory)
    if not resolved.is_dir():
        raise NotADirectoryError(f"Not a directory: {sandbox.display_path(resolved)}")

    if match == "name":

        def _scan_name() -> list[str]:
            hits: list[str] = []
            for root, dirs, files in os.walk(resolved):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for fname in files:
                    if fnmatch.fnmatch(fname, pattern):
                        hits.append(sandbox.display_path(Path(root) / fname))
                        if len(hits) >= max_results:
                            return hits
            return hits

        matches = await asyncio.to_thread(_scan_name)
    else:

        def _scan_path() -> list[str]:
            hits: list[str] = []
            for m in sorted(resolved.glob(pattern)):
                if m.is_file() and not any(
                    p.startswith(".") for p in m.relative_to(resolved).parts
                ):
                    hits.append(sandbox.display_path(m))
                    if len(hits) >= max_results:
                        break
            return hits

        matches = await asyncio.to_thread(_scan_path)

    if not matches:
        return f"No files matching '{pattern}' in {sandbox.display_path(resolved)}"
    return "\n".join(matches)


glob_files = Tool(
    _glob_files,
    name="glob",
    description=(
        "Find files by glob pattern. Use match='path' (default) for full-path patterns "
        "like 'src/**/*.ts', or match='name' for filename-only like '*.py'."
    ),
)
