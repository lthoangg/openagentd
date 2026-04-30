"""write_file tool — create or overwrite a file."""

from __future__ import annotations

from typing import Annotated

from loguru import logger
from pydantic import Field

from app.agent.sandbox import get_sandbox
from app.agent.tools.registry import Tool


async def _write_file(
    path: Annotated[
        str,
        Field(description="Relative path for the file to create or overwrite."),
    ],
    content: Annotated[
        str,
        Field(description="UTF-8 text content to write."),
    ],
    overwrite: Annotated[
        bool,
        Field(description="Fail if file exists when false (default true)."),
    ] = True,
) -> str:
    """Create or overwrite a file with text content. Parent directories are created automatically."""
    sandbox = get_sandbox()
    resolved = sandbox.validate_path(path)
    rel = sandbox.display_path(resolved)
    if not overwrite and resolved.exists():
        raise FileExistsError(f"File already exists: {rel}")

    resolved.parent.mkdir(parents=True, exist_ok=True)
    encoded = content.encode("utf-8")
    resolved.write_bytes(encoded)
    logger.info("file_written path={} bytes={}", resolved, len(encoded))
    return f"Written {len(encoded)} bytes to {rel}"


write_file = Tool(
    _write_file,
    name="write",
    description=(
        "Create or overwrite a file with text content. "
        "Parent directories are created automatically."
    ),
)
