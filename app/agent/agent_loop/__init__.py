"""Agent loop package.

Public surface:

- :class:`Agent` — the core class that orchestrates one ``run()`` per turn.
- :data:`MAX_AGENT_ITERATIONS` — the per-run iteration cap.
- :data:`MAX_CONCURRENT_TOOLS` — the parallel-dispatch cap.
- :data:`MAX_RETRIES` — the retry budget per provider, used by tests.
- :func:`sanitize_error` — sandbox-path redaction in tool error messages,
  used by tests.

Lower-level helpers (``stream_and_assemble``, ``stream_with_retry``,
``parse_retry_after``, ``make_tool_executor``, ``gather_or_cancel``)
live in their respective sub-modules and are imported directly when
needed.
"""

from app.agent.agent_loop.core import (
    MAX_AGENT_ITERATIONS,
    MAX_CONCURRENT_TOOLS,
    Agent,
)
from app.agent.agent_loop.retry import MAX_RETRIES
from app.agent.agent_loop.tool_executor import sanitize_error

__all__ = [
    "Agent",
    "MAX_AGENT_ITERATIONS",
    "MAX_CONCURRENT_TOOLS",
    "MAX_RETRIES",
    "sanitize_error",
]
