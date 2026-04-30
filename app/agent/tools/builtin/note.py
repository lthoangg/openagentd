"""note tool — record a curated note during the session.

Appends to wiki/notes/{date}.md.
Each call adds a timestamped entry block — the file is readable when
the agent calls note() multiple times per session.
Dream agent reads these notes when synthesising wiki topics.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from app.agent.tools.registry import Tool
from app.services.wiki import write_note


async def _note(
    content: Annotated[str, Field(description="The note content to record.")],
) -> str:
    """Record a curated note during the session.

    Use this to capture something worth remembering across sessions:
    - A decision made and why
    - A user preference or working style learned
    - A non-obvious problem and how it was solved
    - Anything the user explicitly asks to remember

    Notes are appended to a daily file and later synthesised by
    the dream agent into wiki topics.  Write in clear, self-contained
    sentences — the dream agent reads each entry independently.
    """
    path = write_note(content)
    return f"Note recorded to {path.name}."


note_tool = Tool(
    _note,
    name="note",
    description=(
        "Record a curated note during the session. "
        "Use for decisions, user preferences, or facts worth remembering. "
        "Each call appends a timestamped entry — call multiple times if needed. "
        "Notes are synthesised by the dream agent into wiki topics."
    ),
)
