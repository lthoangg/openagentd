"""Automatic chat session title generation.

Generates a short, descriptive title for a chat session from the user's
first message, using a lightweight LLM call with the agent's existing provider.

Intended to be called as a fire-and-forget ``asyncio.create_task`` immediately
after the first user message is saved — before the agent runs. Failures are
logged and swallowed; the session keeps its raw-truncation fallback title.

The system prompt is *required* and must be provided by the caller — it is
resolved from ``.openagentd/config/title_generation.md`` by
:func:`~app.agent.hooks.title_generation.build_title_generation_hook`.
"""

from __future__ import annotations

import asyncio
import time
from uuid import UUID

from loguru import logger
from opentelemetry.trace import SpanKind, StatusCode

from app.agent.providers.base import LLMProviderBase
from app.agent.schemas.chat import ChatMessage, HumanMessage, SystemMessage
from app.agent.schemas.events import TitleUpdateEvent
from app.core.db import DbFactory
from app.core.otel import get_tracer
from app.models.chat import ChatSession
from app.services import memory_stream_store as stream_store

# ── Config ────────────────────────────────────────────────────────────────────

_MAX_CONTENT_CHARS = (
    500  # cap sent to title LLM — long messages don't improve title quality
)
_TITLE_TIMEOUT = 15  # seconds


# ── Helpers ───────────────────────────────────────────────────────────────────


def _clean_title(raw: str) -> str:
    """Strip surrounding quotes, trailing punctuation, and whitespace."""
    return raw.strip().strip("\"'").rstrip(".").strip()[:255]


# ── Public API ────────────────────────────────────────────────────────────────


async def generate_and_save_title(
    *,
    session_id: UUID,
    user_message: str,
    provider: LLMProviderBase,
    db_factory: DbFactory,
    system_prompt: str,
) -> None:
    """Generate a title from the user's first message and persist it.

    Safe to call as ``asyncio.create_task(generate_and_save_title(...))``.
    All exceptions are caught and logged — never propagated.

    ``system_prompt`` is required and sourced from
    ``.openagentd/config/title_generation.md``. Passing an empty string raises
    ``ValueError``.
    """
    if not system_prompt or not system_prompt.strip():
        raise ValueError(
            "generate_and_save_title requires a non-empty system_prompt "
            "(configure .openagentd/config/title_generation.md)."
        )

    session_id_str = str(session_id)
    user_text = user_message[:_MAX_CONTENT_CHARS]

    tracer = get_tracer()
    with tracer.start_as_current_span(
        "title_generation",
        kind=SpanKind.INTERNAL,
        attributes={
            "gen_ai.conversation.id": session_id_str,
            "title_generation.user_message_length": len(user_text),
        },
    ) as span:
        try:
            # Annotated as ``list[ChatMessage]`` (the discriminated union) to
            # satisfy ``LLMProviderBase.chat`` — ``list`` is invariant in its
            # element type, so an inferred ``list[SystemMessage | HumanMessage]``
            # is not assignable to ``list[ChatMessage]``.
            messages: list[ChatMessage] = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_text),
            ]

            t0 = time.monotonic()
            try:
                async with asyncio.timeout(_TITLE_TIMEOUT):
                    result = await provider.chat(
                        messages,
                        max_tokens=20,
                        temperature=0.2,
                        thinking_level="none",
                    )
            except TimeoutError:
                logger.warning("title_generation_timeout session_id={}", session_id_str)
                span.set_attribute("error.type", "TimeoutError")
                span.set_status(StatusCode.ERROR, "timeout")
                return
            except Exception as e:
                logger.warning(
                    "title_generation_llm_error session_id={}", session_id_str
                )
                logger.warning("LLM error details: {}", e)
                span.set_attribute("error.type", type(e).__name__)
                span.set_status(StatusCode.ERROR, str(e))
                return
            finally:
                span.set_attribute(
                    "title_generation.llm_duration_s", round(time.monotonic() - t0, 3)
                )

            title = _clean_title(result.content or "")
            if not title:
                logger.debug("title_generation_empty session_id={}", session_id_str)
                span.set_attribute("title_generation.skipped", "empty_response")
                span.set_status(StatusCode.OK)
                return

            async with db_factory() as db:
                session = await db.get(ChatSession, session_id)
                if session is None:
                    span.set_attribute("title_generation.skipped", "session_not_found")
                    span.set_status(StatusCode.OK)
                    return
                session.title = title
                db.add(session)
                await db.commit()

            from app.services.stream_envelope import StreamEnvelope

            await stream_store.push_event(
                session_id_str,
                StreamEnvelope.from_event(TitleUpdateEvent(title=title)),
            )

            span.set_attribute("title_generation.title_length", len(title))
            span.set_status(StatusCode.OK)
            logger.info(
                "title_generated session_id={} title={!r}", session_id_str, title
            )

        except Exception:
            logger.warning("title_generation_failed session_id={}", session_id_str)
            span.set_status(StatusCode.ERROR, "unexpected error")
