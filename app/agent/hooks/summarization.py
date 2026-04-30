"""SummarizationHook — keeps context windows small without losing history.

How it works
------------
At the start of each LLM call (``before_model``), the hook reads
``state.usage.last_prompt_tokens`` — written by the agent loop after each
model response.  If that count meets or exceeds ``prompt_token_threshold``,
the hook:

1. Reads all *visible* messages from ``state.messages``
   (``exclude_from_context=False``).
2. Finds the last ``keep_last_assistants`` assistant turns and protects all
   messages from the earliest of those turns onward.
3. Calls the LLM with a summarisation prompt to produce a compact summary of
   all older messages.
4. Inserts the summary ``HumanMessage`` (``is_summary=True``) into
   ``state.messages`` at the position of the first non-excluded message.
5. Marks summarised messages as ``exclude_from_context=True`` — retained in
   the list for audit but invisible to future LLM calls.

This is a **pure state transform**: no DB reads or writes occur here.
The checkpointer (called by the agent loop after ``before_model``) is
responsible for persisting the mutated ``state.messages``.

Usage::

    from app.agent.hooks.summarization import SummarizationHook

    mw = SummarizationHook(
        llm_provider=provider,
        prompt_token_threshold=30000,  # trigger when model reports 30k prompt tokens
        keep_last_assistants=3,        # keep last 3 assistant turns verbatim
    )
    agent = Agent(llm_provider=provider, hooks=[mw])
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from opentelemetry.trace import SpanKind, StatusCode

from app.agent.hooks.base import BaseAgentHook
from app.agent.providers.base import LLMProviderBase
from app.agent.providers.factory import build_provider
from app.agent.schemas.agent import SummarizationConfig
from app.agent.schemas.chat import (
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from app.core.config import settings
from app.core.otel import get_tracer

if TYPE_CHECKING:
    from app.agent.state import AgentState, ModelRequest, RunContext

# ── Module-level defaults (no env-var overrides) ──────────────────────────
# These were previously SUMMARIZATION_* settings in app.core.config. Per-agent
# ``summarization:`` blocks (in agent .md frontmatter) and the global
# ``.openagentd/config/summarization.md`` file remain the supported override
# surfaces — see ``build_summarization_hook`` for the resolution chain.
DEFAULT_PROMPT_TOKEN_THRESHOLD = 100000
DEFAULT_KEEP_LAST_ASSISTANTS = 3
DEFAULT_MAX_TOKEN_LENGTH = 10000
DEFAULT_MIN_MESSAGES_SINCE_LAST_SUMMARY = 4


def summarization_config_path() -> Path:
    """Return the path to the global summarization config file.

    Defaults to ``{OPENAGENTD_CONFIG_DIR}/summarization.md``.
    """
    return Path(settings.OPENAGENTD_CONFIG_DIR) / "summarization.md"


_SUMMARISE_REQUEST = (
    "Please summarise the conversation below according to your instructions."
)

_MERGE_REQUEST = (
    "The conversation below starts with an earlier summary followed by new messages. "
    "Merge them into a single, updated summary according to your instructions."
)


def _find_assistant_cutoff(msgs: list, keep_last: int) -> int:
    """Return the index of the Nth-from-last assistant message in *msgs*.

    Messages at or after this index are protected from summarisation.
    Returns 0 if there are fewer than *keep_last* assistant messages
    (nothing to summarise).
    """
    if keep_last <= 0:
        return len(msgs)
    remaining = keep_last
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i].role == "assistant":
            remaining -= 1
            if remaining == 0:
                return i
    return 0  # not enough assistant turns — protect everything


def build_summarization_hook(
    default_provider: LLMProviderBase,
    cfg: SummarizationConfig | None,
) -> "SummarizationHook | None":
    """Return a configured SummarizationHook, or ``None`` if disabled.

    ``None`` is returned (with a warning logged) for any of the following —
    the caller should simply not add the hook:

    * The per-agent config sets ``enabled: false``.
    * The resolved ``token_threshold`` is ``<= 0``.
    * ``.openagentd/config/summarization.md`` does not exist.
    * The config file exists but its body (the prompt) is empty.

    Missing-config paths log a warning so operators can spot the
    misconfiguration in ``app.log`` without the agent failing to respond.
    The warning includes a hint to copy ``seed/summarization.md`` or set
    per-agent ``enabled: false`` to silence it.

    Fallback chain for each setting (first non-None wins):
      1. Per-agent ``summarization:`` block in the agent's ``.md`` frontmatter
      2. Global ``.openagentd/config/summarization.md`` file
      3. Module-level ``DEFAULT_*`` constants in this module

    The model fallback chain:
      1. Per-agent ``summarization.model``
      2. Global file ``model``
      3. Agent's own provider (``default_provider``)
    """
    if cfg is not None and not cfg.enabled:
        return None

    from app.agent.loader import load_summarization_file_config

    file_cfg = load_summarization_file_config()

    threshold = (
        cfg.token_threshold
        if cfg and cfg.token_threshold is not None
        else (
            file_cfg.token_threshold
            if file_cfg and file_cfg.token_threshold is not None
            else DEFAULT_PROMPT_TOKEN_THRESHOLD
        )
    )
    if threshold <= 0:
        return None

    # Resolve provider: agent override → file override → agent's own provider
    provider = default_provider
    model_str = (
        cfg.model
        if cfg and cfg.model
        else (file_cfg.model if file_cfg and file_cfg.model else None)
    )
    if model_str:
        provider = build_provider(model_str)

    # Prompt is required — sourced from the file body. No bundled fallback:
    # we'd rather degrade to "no summarization, context window will fill up
    # eventually" than silently produce summaries from a stale or wrong
    # prompt the operator never saw. Both branches log a warning and return
    # None so the caller skips installing the hook (mirroring
    # ``build_title_generation_hook``'s contract).
    if file_cfg is None:
        logger.warning(
            "summarization_disabled reason=config_missing path={} hint='copy "
            "seed/summarization.md to this path or set per-agent "
            "summarization.enabled=false to silence this warning'",
            summarization_config_path(),
        )
        return None
    if not file_cfg.prompt:
        logger.warning(
            "summarization_disabled reason=empty_prompt path={} hint='the "
            "file body must contain the summariser system prompt'",
            summarization_config_path(),
        )
        return None

    return SummarizationHook(
        provider,
        summary_prompt=file_cfg.prompt,
        prompt_token_threshold=threshold,
        keep_last_assistants=(
            cfg.keep_last_assistants
            if cfg and cfg.keep_last_assistants is not None
            else (
                file_cfg.keep_last_assistants
                if file_cfg.keep_last_assistants is not None
                else DEFAULT_KEEP_LAST_ASSISTANTS
            )
        ),
        max_token_length=(
            cfg.max_token_length
            if cfg and cfg.max_token_length is not None
            else (
                file_cfg.max_token_length
                if file_cfg.max_token_length is not None
                else DEFAULT_MAX_TOKEN_LENGTH
            )
        ),
    )


class SummarizationHook(BaseAgentHook):
    """Summarises session history before an LLM call when the context is too large.

    Mutates ``state.messages`` — adds a summary message and marks old messages
    as ``exclude_from_context=True``.

    Parameters
    ----------
    llm_provider:
        LLM provider used to generate the summary.
    summary_prompt:
        System prompt given to the summariser LLM. Required — must be
        non-empty. Sourced from ``.openagentd/config/summarization.md`` body.
    prompt_token_threshold:
        Trigger when ``state.usage.last_prompt_tokens`` meets or exceeds this
        value.  Set to ``0`` to disable.
    keep_last_assistants:
        Number of most-recent *assistant turns* to keep verbatim alongside the
        summary.  All messages belonging to those turns (including the user
        messages that preceded them) are protected.
    max_token_length:
        Maximum tokens for the summarizer LLM response. Passed as ``max_tokens``
        to the LLM provider API call. Set to ``0`` to disable limit.
    min_messages_since_last_summary:
        Minimum number of new messages that must have been added since the last
        summarisation before another can fire.  Prevents thrashing when the
        kept window is already close to the threshold.  Set to ``0`` to disable.
    """

    def __init__(
        self,
        llm_provider: LLMProviderBase,
        summary_prompt: str,
        *,
        prompt_token_threshold: int = DEFAULT_PROMPT_TOKEN_THRESHOLD,
        keep_last_assistants: int = DEFAULT_KEEP_LAST_ASSISTANTS,
        max_token_length: int = DEFAULT_MAX_TOKEN_LENGTH,
        min_messages_since_last_summary: int = DEFAULT_MIN_MESSAGES_SINCE_LAST_SUMMARY,
    ) -> None:
        if not summary_prompt or not summary_prompt.strip():
            raise ValueError(
                "SummarizationHook requires a non-empty summary_prompt "
                "(configure .openagentd/config/summarization.md)."
            )
        self._llm_provider = llm_provider
        self._prompt_token_threshold = prompt_token_threshold
        self._keep_last_assistants = keep_last_assistants
        self._summary_prompt = summary_prompt
        self._max_token_length = max_token_length
        self._min_messages_since_last_summary = min_messages_since_last_summary
        # Me track message count at last summarisation to enforce the minimum delta guard
        self._messages_at_last_summary: int = 0

    @property
    def prompt_token_threshold(self) -> int:
        """Token count at which summarisation fires.  Public for peer hooks."""
        return self._prompt_token_threshold

    async def before_model(
        self,
        ctx: "RunContext",
        state: "AgentState",
        request: "ModelRequest | None" = None,
    ) -> "ModelRequest | None":
        """Trigger summarisation if the previous call's prompt tokens hit the threshold.

        Mutates ``state.messages`` then returns a new ``ModelRequest`` with the
        updated message window so the current LLM call sees the summary immediately.
        Returns ``None`` (pass-through) when summarisation does not fire.
        """
        if self._prompt_token_threshold <= 0:
            return None

        if state.usage.last_prompt_tokens < self._prompt_token_threshold:
            return None

        # Me enforce minimum message delta — skip if not enough new messages
        # since the last summarisation to avoid thrashing.
        if self._min_messages_since_last_summary > 0:
            messages_since = len(state.messages) - self._messages_at_last_summary
            if (
                self._messages_at_last_summary > 0
                and messages_since < self._min_messages_since_last_summary
            ):
                logger.debug(
                    "summarization_skipped_min_delta agent={} messages_since={} min={}",
                    ctx.agent_name,
                    messages_since,
                    self._min_messages_since_last_summary,
                )
                return None

        logger.info(
            "summarization_triggered agent={} last_prompt_tokens={}",
            ctx.agent_name,
            state.usage.last_prompt_tokens,
        )
        await self._summarise(ctx, state)

        # Me return updated request with fresh messages — loop no need to rebuild
        if request is not None:
            return request.override(messages=tuple(state.messages_for_llm))
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _summarise(self, ctx: "RunContext", state: "AgentState") -> None:
        """Generate summary and mutate state.messages — pure state transform + LLM call."""
        logger.info(
            "summarization_started session_id={} agent={}",
            ctx.session_id,
            ctx.agent_name,
        )

        tracer = get_tracer()
        with tracer.start_as_current_span(
            "summarization",
            kind=SpanKind.INTERNAL,
            attributes={
                "gen_ai.agent.name": ctx.agent_name or "",
                "gen_ai.conversation.id": ctx.session_id or "",
                "run_id": ctx.run_id,
                "summarization.prompt_tokens": state.usage.last_prompt_tokens,
                "summarization.threshold": self._prompt_token_threshold,
            },
        ) as span:
            await self._summarise_inner(ctx, state, span)

    async def _summarise_inner(
        self, ctx: "RunContext", state: "AgentState", span
    ) -> None:
        """Core summarisation logic, called inside the OTel span."""
        # Me read from state.messages, not DB — skip SystemMessage (handled separately by agent)
        eligible = [
            m
            for m in state.messages
            if not m.exclude_from_context and not isinstance(m, SystemMessage)
        ]

        if not eligible:
            logger.debug(
                "summarization_skipped_no_messages session_id={}", ctx.session_id
            )
            span.set_attribute("summarization.skipped", "no_messages")
            span.set_status(StatusCode.OK)
            return

        # Me find cutoff: protect last N assistant turns.
        # Walk backward, count assistant messages; cutoff is the index of the
        # Nth-from-last assistant message.  All messages from cutoff onward are kept.
        cutoff_idx = _find_assistant_cutoff(eligible, self._keep_last_assistants)
        if cutoff_idx > 0:
            to_summarise = eligible[:cutoff_idx]
        else:
            to_summarise = eligible

        if not to_summarise:
            logger.debug(
                "summarization_skipped_all_messages_in_keep_window session_id={}",
                ctx.session_id,
            )
            span.set_attribute("summarization.skipped", "all_in_keep_window")
            span.set_status(StatusCode.OK)
            return

        # Me build summariser call: System + HumanMessage(request + conversation).
        # Embedding to_summarise as text inside one HumanMessage avoids role-alternation
        # violations (ZAI/OpenAI reject system → assistant at position 0).
        #
        # Tool message content is replaced with a stub — the raw output (shell
        # output, file contents, JSON blobs) is noise for summarisation purposes;
        # the tool name is enough for the summariser to understand what happened.
        # Prior summaries in the window signal a merge rather than a fresh summary.
        has_prior_summary = any(m.is_summary for m in to_summarise)

        def _render(m) -> str:
            if isinstance(m, ToolMessage):
                name = f"/{m.name}" if m.name else ""
                return f"[tool{name}]: [tool result omitted]"
            return f"[{m.role}]: {m.content or ''}"

        convo_text = "\n\n".join(_render(m) for m in to_summarise)
        request_line = _MERGE_REQUEST if has_prior_summary else _SUMMARISE_REQUEST
        summariser_messages = [
            SystemMessage(content=self._summary_prompt),
            HumanMessage(content=f"{request_line}\n\n{convo_text}"),
        ]

        span.set_attribute("summarization.messages_to_summarise", len(to_summarise))
        span.set_attribute(
            "summarization.keep_last_assistants", self._keep_last_assistants
        )
        span.set_attribute("summarization.has_prior_summary", has_prior_summary)

        try:
            summary_text = await self._call_llm(summariser_messages)
        except Exception as exc:
            logger.error(
                "summarization_llm_failed session_id={} error={}",
                ctx.session_id,
                exc,
            )
            span.set_attribute("error.type", type(exc).__name__)
            span.set_status(StatusCode.ERROR, str(exc))
            return

        if not summary_text:
            logger.warning(
                "summarization_skipped_empty_response session_id={} agent={}",
                ctx.session_id,
                ctx.agent_name,
            )
            span.set_attribute("summarization.skipped", "empty_llm_response")
            span.set_status(StatusCode.OK)
            return

        # Me mark old messages as excluded — no DB write, just state mutation
        to_summarise_set = {id(m) for m in to_summarise}
        for m in state.messages:
            if id(m) in to_summarise_set:
                m.exclude_from_context = True

        # Me also exclude any prior summary messages in the kept window —
        # the new summary supersedes them, and keeping old summaries can cause
        # consecutive-assistant-message violations (ZAI code 1214).
        for m in state.messages:
            if m.is_summary and id(m) not in to_summarise_set:
                m.exclude_from_context = True

        # Me insert summary before first non-excluded message
        first_kept_idx = next(
            (i for i, m in enumerate(state.messages) if not m.exclude_from_context),
            len(state.messages),
        )

        # Me always use HumanMessage as the summary anchor.
        # ZAI (and most OpenAI-compat APIs) require system → user → ...
        # A HumanMessage summary is safe regardless of what the kept window starts with.
        summary_msg = HumanMessage(
            content="[Summary of earlier conversation]\n" + summary_text,
            is_summary=True,
        )
        state.messages.insert(first_kept_idx, summary_msg)
        # Loop will call checkpointer.sync() after before_model phase

        # Me record current message count so the minimum-delta guard works next turn
        self._messages_at_last_summary = len(state.messages)

        kept = len(eligible) - len(to_summarise)
        span.set_attribute("summarization.summary_length", len(summary_text))
        span.set_attribute("summarization.kept", kept)
        span.set_status(StatusCode.OK)

        logger.info(
            "summarization_complete session_id={} agent={} "
            "summarised={} kept={} keep_last_assistants={} summary_length={}",
            ctx.session_id,
            ctx.agent_name,
            len(to_summarise),
            kept,
            self._keep_last_assistants,
            len(summary_text),
        )

    async def _call_llm(self, messages) -> str:
        """Stream the summariser LLM and return the full text response.

        Passes max_token_length to the LLM provider if set.
        """
        kwargs = {}
        if self._max_token_length > 0:
            kwargs["max_tokens"] = self._max_token_length

        tracer = get_tracer()
        with tracer.start_as_current_span(
            "summarization_llm_call",
            kind=SpanKind.CLIENT,
        ) as span:
            t0 = time.monotonic()
            try:
                stream = self._llm_provider.stream(messages=messages, **kwargs)
                full_text = ""
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta.content:
                        full_text += delta.content
            except Exception as exc:
                span.set_attribute("error.type", type(exc).__name__)
                span.set_status(StatusCode.ERROR, str(exc))
                raise
            elapsed = time.monotonic() - t0
            span.set_attribute("summarization.llm_duration_s", round(elapsed, 3))
            span.set_attribute("summarization.response_length", len(full_text))
            span.set_status(StatusCode.OK)
            return full_text.strip()
