"""TelemetryHook — dumps full LLM context to JSONL after each agent run.

After the agent completes (``after_agent``), writes one JSONL file containing:

- Line 0: ``{"type": "system", "content": "<system_prompt>"}``
- Line 1…N: one JSON object per visible ``ChatMessage`` in ``state.messages``

File path::

    {STATE_DIR}/telemetry/<session_id>/<user_msg_id>.jsonl

Configurable via the ``OPENAGENTD_STATE_DIR`` env var.

Where ``user_msg_id`` is the ``db_id`` of the last ``HumanMessage`` that
triggered this run.  Falls back to ``run_id`` when ``db_id`` is not set.

Usage::

    from app.agent.hooks.telemetry import TelemetryHook

    hook = TelemetryHook()
    agent = Agent(llm_provider=provider, hooks=[hook])
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from app.agent.hooks.base import BaseAgentHook
from app.agent.schemas.chat import AssistantMessage, HumanMessage, SystemMessage
from app.core.config import settings

if TYPE_CHECKING:
    from app.agent.state import AgentState, ModelCallHandler, ModelRequest, RunContext

_TELEMETRY_DIR = Path(settings.OPENAGENTD_STATE_DIR) / "telemetry"

logger = logging.getLogger(__name__)


class TelemetryHook(BaseAgentHook):
    """Dumps system prompt + full message context to JSONL after each run.

    One file per agent turn, named by the triggering user message's ``db_id``.
    Useful for debugging context window state, summarization effects, and
    provider payload inspection without touching live traffic.

    Args:
        base_dir: Root directory for telemetry files. Defaults to
            ``{STATE_DIR}/telemetry``.
    """

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir else _TELEMETRY_DIR
        self._last_system_prompt: str = ""  # Me sniff from wrap_model_call

    async def wrap_model_call(
        self,
        ctx: "RunContext",
        state: "AgentState",
        request: "ModelRequest",
        handler: "ModelCallHandler",
    ) -> "AssistantMessage":
        """Sniff the fully-built system prompt before each LLM call."""
        self._last_system_prompt = request.system_prompt
        return await handler(request)

    async def after_agent(
        self,
        ctx: "RunContext",
        state: "AgentState",
        response: "AssistantMessage",
    ) -> None:
        """Write system prompt + visible messages as JSONL after agent completes."""
        # Me find triggering user message db_id — use run_id as fallback
        user_msg_id: str = ctx.run_id
        for m in reversed(state.messages):
            if isinstance(m, HumanMessage) and not m.is_summary:
                if m.db_id is not None:
                    user_msg_id = str(m.db_id)
                break

        session_id = ctx.session_id or "no-session"
        out_dir = self._base_dir / session_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{user_msg_id}.jsonl"

        lines: list[str] = []

        # Me line 0 — actual system prompt sent to provider (captured from last wrap_model_call)
        lines.append(
            json.dumps(
                {
                    "type": "system",
                    "content": self._last_system_prompt or state.system_prompt,
                },
                ensure_ascii=False,
            )
        )

        # Me line 1…N — all messages via model_dump_full() — captures every field
        for m in state.messages:
            if isinstance(m, SystemMessage):
                continue  # Me system prompt already written above
            lines.append(json.dumps(m.model_dump_full(), ensure_ascii=False))

        try:
            out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as exc:
            logger.warning("telemetry_write_failed path=%s error=%s", out_path, exc)
