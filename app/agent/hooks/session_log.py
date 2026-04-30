"""SessionLogHook — writes a verbose JSONL event log per chat session.

Each line in the log file is a self-contained JSON object describing one event
in the agent conversation.  The file lives in
``{OPENAGENTD_STATE_DIR}/logs/sessions/<session_id>/<agent_name>.jsonl``
(under ``SESSION_LOG_DIR`` from ``app.core.logging_config``).

Event types
-----------
``agent_start``
    Before the agent's first model call (trigger message, context size, tools).
``model_call``
    Before each LLM call — records the number of messages and their roles.
``assistant_message``
    A text response from the LLM (full content, not truncated).
``tool_call``
    A tool call dispatched by the LLM (name, parsed args).
``tool_result``
    The result returned by the tool (up to 5000 chars).
``usage``
    Token usage after each model response.
``agent_done``
    After the agent's final response for this run (elapsed time, iterations).

Usage
-----
::

    from app.agent.hooks.session_log import SessionLogHook

    hook = SessionLogHook(session_id="abc123", agent_name="mybot")
    agent = Agent(llm_provider=provider, hooks=[hook])
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.agent.hooks.base import BaseAgentHook
from app.agent.schemas.chat import HumanMessage
from app.core.logging_config import SESSION_LOG_DIR

if TYPE_CHECKING:
    from app.agent.state import AgentState, ModelRequest, RunContext
    from app.agent.schemas.chat import AssistantMessage, ChatCompletionChunk


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _truncate(text: str | None, max_len: int = 5000) -> str | None:
    if text is None:
        return None
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"…[+{len(text) - max_len}]"


class SessionLogHook(BaseAgentHook):
    """Appends structured JSONL events to ``{OPENAGENTD_STATE_DIR}/logs/sessions/<session_id>/<agent>.jsonl``.

    Thread-safe within a single asyncio event loop (writes are synchronous and
    asyncio is single-threaded).  The log directory is created on first write.

    Args:
        session_id: Unique identifier for the chat session.  Used as a
            subdirectory name so all session logs are grouped together.
        agent_name: Name of the agent this hook is attached to.  Appears in
            every log entry so entries from different agents are distinguishable.
    """

    def __init__(self, session_id: str, agent_name: str) -> None:
        self._session_id = session_id
        self._agent_name = agent_name
        self._log_dir = SESSION_LOG_DIR / session_id
        self._path = self._log_dir / f"{agent_name}.jsonl"
        self._path_created = False
        self._run_start: float = 0.0
        self._iteration: int = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_dir(self) -> None:
        if not self._path_created:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            self._path_created = True

    def _write(self, event: str, **fields: Any) -> None:
        """Append one JSON line to the log file."""
        self._ensure_dir()
        entry: dict[str, Any] = {
            "ts": _now_iso(),
            "session": self._session_id,
            "agent": self._agent_name,
            "event": event,
        }
        entry.update({k: v for k, v in fields.items() if v is not None})
        try:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            # Never crash the agent because of a logging failure.
            logging.getLogger(__name__).warning("session_log write failed: %s", exc)

    # ------------------------------------------------------------------
    # BaseAgentHook overrides
    # ------------------------------------------------------------------

    async def before_agent(self, ctx: "RunContext", state: "AgentState") -> None:
        """Log full context at run start — trigger message, tools, message count."""
        self._run_start = time.monotonic()
        self._iteration = 0

        # Find the last HumanMessage — that's what triggered this run.
        trigger: str | None = None
        for m in reversed(state.messages):
            if isinstance(m, HumanMessage) and m.content:
                trigger = m.content
                break

        # Gather message role distribution
        role_counts: dict[str, int] = {}
        for m in state.messages:
            role = getattr(m, "role", "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1

        self._write(
            "agent_start",
            trigger=trigger,
            context_messages=len(state.messages),
            role_distribution=role_counts,
            tools=state.tool_names,
        )

    async def after_agent(
        self, ctx: "RunContext", state: "AgentState", response: "AssistantMessage"
    ) -> None:
        elapsed = time.monotonic() - self._run_start if self._run_start else 0
        self._write(
            "agent_done",
            content=response.content,
            elapsed_seconds=round(elapsed, 3),
            iterations=self._iteration,
            total_tokens=state.metadata.get("total_tokens", 0),
        )

    async def before_model(
        self,
        ctx: "RunContext",
        state: "AgentState",
        request: "ModelRequest | None" = None,
    ) -> None:
        self._iteration += 1

        # Role summary for this model call
        role_counts: dict[str, int] = {}
        for m in state.messages:
            role = getattr(m, "role", "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1

        self._write(
            "model_call",
            iteration=self._iteration,
            context_messages=len(state.messages),
            role_distribution=role_counts,
        )

    async def after_model(
        self, ctx: "RunContext", state: "AgentState", response: "AssistantMessage"
    ) -> None:
        self._write(
            "assistant_message",
            content=response.content,
            reasoning=_truncate(response.reasoning_content, 2000),
            has_tool_calls=bool(response.tool_calls),
            tool_call_count=len(response.tool_calls) if response.tool_calls else 0,
            tool_names=[tc.function.name for tc in (response.tool_calls or [])],
        )

    async def on_model_delta(
        self, ctx: "RunContext", state: "AgentState", chunk: "ChatCompletionChunk"
    ) -> None:
        # Log token usage when available in chunk
        if chunk.usage:
            self._write(
                "usage",
                prompt_tokens=chunk.usage.prompt_tokens,
                completion_tokens=chunk.usage.completion_tokens,
                total_tokens=chunk.usage.total_tokens,
                cached_tokens=getattr(chunk.usage, "cached_tokens", None),
                thoughts_tokens=getattr(chunk.usage, "thoughts_tokens", None),
                tool_use_tokens=getattr(chunk.usage, "tool_use_tokens", None),
                model=chunk.model,
            )
