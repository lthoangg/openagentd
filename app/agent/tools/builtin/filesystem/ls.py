"""list_directory tool — list directory contents."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from app.agent.sandbox import get_sandbox
from app.agent.tools.registry import Tool


async def _list_directory(
    path: Annotated[
        str,
        Field(description="Directory path (default '.' = workspace root)."),
    ] = ".",
) -> str:
    """List immediate children of a directory with type and size."""
    sandbox = get_sandbox()
    resolved = sandbox.validate_path(path)
    rel = sandbox.display_path(resolved)
    if not resolved.exists():
        raise FileNotFoundError(f"Directory not found: {rel}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {rel}")

    entries = sorted(resolved.iterdir(), key=lambda p: (p.is_file(), p.name))
    lines = []
    for entry in entries:
        indicator = "d" if entry.is_dir() else "f"
        lines.append(
            f"[{indicator}] {entry.name}  ({entry.stat().st_size} bytes)"
            if entry.is_file()
            else f"[{indicator}] {entry.name}/"
        )
    return "\n".join(lines) if lines else "(empty directory)"


list_directory = Tool(
    _list_directory,
    name="ls",
    description="List immediate children of a directory with type and size.",
)
