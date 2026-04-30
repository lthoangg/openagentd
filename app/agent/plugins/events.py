"""Event payload TypedDicts for the functional plugin contract.

Each event has an ``input`` (read-only metadata) and an ``output``
(mutable, in-place modification only).  The split is the part of the
opencode-inspired API that actually earns its keep — for tool events
``output["args"]`` and ``output["output"]`` are the things plugins want
to rewrite, and the input/output split makes the mutation contract
self-documenting at the call site.
"""

from __future__ import annotations

from typing import Any, TypedDict


class ToolBeforeInput(TypedDict):
    """Read-only metadata for ``tool.before``."""

    tool: str  # Tool name being invoked.
    session_id: str | None  # ``RunContext.session_id``.
    run_id: str  # ``RunContext.run_id``.
    agent_name: str
    call_id: str  # ``ToolCall.id``.


class ToolBeforeOutput(TypedDict):
    """Mutable output for ``tool.before``.

    Plugins may mutate ``args`` in place to rewrite the parsed tool
    arguments before execution; the loader re-serializes them back into
    the ``ToolCall`` JSON.  Raise any exception to abort execution — the
    exception's message becomes the tool result.
    """

    args: dict[str, Any]


class ToolAfterInput(TypedDict):
    """Read-only metadata for ``tool.after``."""

    tool: str
    session_id: str | None
    run_id: str
    agent_name: str
    call_id: str
    args: dict[str, Any]  # Args used for execution (post-before-mutation).


class ToolAfterOutput(TypedDict):
    """Mutable output for ``tool.after``.

    Plugins may mutate ``output`` to replace the tool result string the
    LLM will see (e.g. truncate, redact, append metadata).
    """

    output: str
