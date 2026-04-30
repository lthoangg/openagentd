"""grep_files tool — search file contents by regex."""

from __future__ import annotations

import asyncio
import fnmatch
import os
import re
from pathlib import Path
from typing import Annotated

from pydantic import Field

from app.agent.sandbox import get_sandbox
from app.agent.tools.registry import Tool

# Me cap regex pattern length — prevents catastrophically complex patterns
_MAX_PATTERN_LEN = 500
# Me timeout for the entire scan in seconds
_SCAN_TIMEOUT_S = 10


async def _grep_files(
    pattern: Annotated[
        str,
        Field(description="Regex to match per line (e.g. 'def main', 'TODO|FIXME')."),
    ],
    directory: Annotated[
        str,
        Field(description="Search root (default '.' = workspace root)."),
    ] = ".",
    include: Annotated[
        str,
        Field(description="Filename glob to filter files (e.g. '*.py'). Default '*'."),
    ] = "*",
    max_results: Annotated[
        int,
        Field(description="Maximum matching lines to return (default 100)."),
    ] = 100,
) -> str:
    """Search file contents by regex. Returns 'file:line: content'."""
    sandbox = get_sandbox()
    resolved = sandbox.validate_path(directory)
    if not resolved.is_dir():
        raise NotADirectoryError(f"Not a directory: {sandbox.display_path(resolved)}")

    # Me reject patterns that are too long — prevents crafted ReDoS payloads
    if len(pattern) > _MAX_PATTERN_LEN:
        raise ValueError(
            f"Pattern too long ({len(pattern)} chars, max {_MAX_PATTERN_LEN})"
        )

    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid regex: {exc}") from exc

    def _scan() -> list[str]:
        hits: list[str] = []
        for root, dirs, files in os.walk(resolved):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in files:
                if not fnmatch.fnmatch(fname, include):
                    continue
                fpath = Path(root) / fname
                try:
                    text = fpath.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                rel = sandbox.display_path(fpath)
                for lineno, line in enumerate(text.splitlines(), start=1):
                    if compiled.search(line):
                        hits.append(f"{rel}:{lineno}: {line[:200]}")
                        if len(hits) >= max_results:
                            return hits
        return hits

    # Me run scan with timeout to prevent ReDoS from locking the thread pool
    try:
        matches = await asyncio.wait_for(
            asyncio.to_thread(_scan), timeout=_SCAN_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        raise TimeoutError(
            f"grep_files scan timed out after {_SCAN_TIMEOUT_S}s — "
            "pattern may be too complex or directory too large"
        )
    if not matches:
        return f"No matches for pattern '{pattern}' in {sandbox.display_path(resolved)} (include={include})"
    return "\n".join(matches)


grep_files = Tool(
    _grep_files,
    name="grep",
    description="Search file contents by regex. Returns 'file:line: content'.",
)
