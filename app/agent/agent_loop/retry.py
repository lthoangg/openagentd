"""Retry + fallback streaming for LLM provider calls.

Wraps a provider's ``stream()`` so transient errors (429, 5xx,
connection errors) that surface mid-stream are retried from the
beginning.  Non-retryable HTTP errors (4xx except 429) are raised
immediately.

If a fallback provider is supplied and the primary exhausts its
retry budget, the fallback is tried with the same budget.

Lives outside the :class:`~app.agent.agent_loop.Agent` class because
none of this depends on instance state — only the provider, the
fallback (if any), and a couple of labels for logging.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import httpx
from loguru import logger

if TYPE_CHECKING:
    from app.agent.hooks import BaseAgentHook
    from app.agent.providers.base import LLMProviderBase
    from app.agent.state import AgentState, RunContext


# Public retry budget.  Tests reference this directly to assert that
# ``stream_with_retry`` performed exactly ``MAX_RETRIES`` attempts before
# falling back / raising.
MAX_RETRIES = 5

# Module-private timing knobs.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_BASE_DELAY = 1.0  # seconds — exponential base 3: 1, 3, 9, 27, 81
_MAX_DELAY = 60.0  # seconds


def parse_retry_after(exc: httpx.HTTPStatusError) -> int:
    """Extract ``retry_after`` seconds from a 429 response.

    Checks (in order):
    1. ``Retry-After`` HTTP header
    2. ``error.details[].metadata.retryDelay`` in the JSON body (Google API format)
    3. Regex match on the response text (e.g. "reset after 33s")
    Returns 0 if none found.
    """
    # 1. Standard header
    header = exc.response.headers.get("retry-after", "")
    if header.isdigit():
        return int(header)

    # 2 & 3. Parse body
    try:
        body = exc.response.text
    except Exception:
        return 0

    # Google API: {"error": {"details": [{"metadata": {"retryDelay": "33s"}}]}}
    for match in re.finditer(r'"retryDelay"\s*:\s*"(\d+)s"', body):
        return int(match.group(1))

    # Fallback: "reset after Ns"
    for match in re.finditer(r"reset after (\d+)s", body):
        return int(match.group(1))

    return 0


async def stream_with_retry(
    *,
    primary_provider: LLMProviderBase,
    primary_label: str,
    fallback_provider: LLMProviderBase | None,
    fallback_label: str,
    agent_name: str,
    ctx: RunContext | None,
    state: AgentState | None,
    hooks: list[BaseAgentHook] | None,
    **kwargs,
) -> AsyncIterator:
    """Stream from ``primary_provider`` with retry; fall back if exhausted.

    Wraps both the provider call *and* the full stream iteration so
    that transient errors surfacing mid-stream are retried from the
    beginning.

    When ``ctx``, ``state`` and ``hooks`` are supplied, fires
    ``on_rate_limit`` on each 429 so the streaming hook can push the
    event to the SSE consumer.
    """
    providers: list[tuple[LLMProviderBase, str]] = [(primary_provider, primary_label)]
    if fallback_provider is not None:
        providers.append((fallback_provider, fallback_label))

    last_exc: Exception | None = None
    for provider, provider_label in providers:
        for attempt in range(MAX_RETRIES):
            try:
                async for chunk in provider.stream(**kwargs):
                    yield chunk
                return  # successful completion — stop retry loop
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in _RETRYABLE_STATUS_CODES:
                    try:
                        await exc.response.aread()
                        body = exc.response.text[:500]
                    except Exception:
                        body = "<unreadable>"
                    logger.error(
                        "llm_provider_error model={} status={} body={}",
                        provider_label,
                        exc.response.status_code,
                        body,
                    )
                    raise
                last_exc = exc
                retry_after = 0
                if exc.response.status_code == 429:
                    try:
                        await exc.response.aread()
                    except Exception:
                        pass
                    retry_after = parse_retry_after(exc)
                    if state and ctx:
                        for hook in hooks or []:
                            await hook.on_rate_limit(
                                ctx,
                                state,
                                retry_after=retry_after,
                                attempt=attempt + 1,
                                max_attempts=MAX_RETRIES,
                            )
                # Skip sleep on the last attempt — move to fallback (or raise) immediately
                if attempt + 1 >= MAX_RETRIES:
                    logger.warning(
                        "llm_provider_exhausted model={} status={} attempts={}",
                        provider_label,
                        exc.response.status_code,
                        MAX_RETRIES,
                    )
                    break
                delay = min(
                    retry_after if retry_after > 0 else _BASE_DELAY * (3**attempt),
                    _MAX_DELAY,
                )
                logger.warning(
                    "llm_provider_retry model={} status={} attempt={}/{} delay={:.1f}s retry_after={}s",
                    provider_label,
                    exc.response.status_code,
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                    retry_after,
                )
                await asyncio.sleep(delay)
            except (httpx.ConnectError, httpx.ReadTimeout, TimeoutError) as exc:
                last_exc = exc
                # Skip sleep on the last attempt
                if attempt + 1 >= MAX_RETRIES:
                    logger.warning(
                        "llm_provider_exhausted model={} error={} attempts={}",
                        provider_label,
                        type(exc).__name__,
                        MAX_RETRIES,
                    )
                    break
                delay = min(_BASE_DELAY * (3**attempt), _MAX_DELAY)
                logger.warning(
                    "llm_provider_retry model={} error={} attempt={}/{} delay={:.1f}s",
                    provider_label,
                    type(exc).__name__,
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)

        # Primary model exhausted all retries — try fallback
        if fallback_provider is not None and provider is primary_provider:
            logger.warning(
                "llm_provider_fallback agent={} primary={} fallback={}",
                agent_name,
                primary_label,
                fallback_label,
            )

    assert last_exc is not None
    raise last_exc
