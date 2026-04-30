"""Shared helpers for provider test scripts.

Each try_*.py script tests a provider directly (no server needed).
These helpers print streaming output in a consistent format.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.providers.base import LLMProviderBase

from app.agent.schemas.chat import HumanMessage

# Me: hard problem so model actually reasons
REASONING_PROMPT = (
    "What is the sum of all prime numbers less than 50? Show your work step by step."
)
SIMPLE_PROMPT = "Write a haiku about Python programming."


async def run_stream(
    provider: LLMProviderBase,
    prompt: str,
    *,
    label: str = "",
):
    """Stream and print reasoning + content deltas."""
    endpoint_info = ""
    if hasattr(provider, "_endpoint_type"):
        endpoint_info = f" endpoint={provider._endpoint_type}"
    elif hasattr(provider, "_use_responses"):
        endpoint_info = (
            f" endpoint={'responses' if provider._use_responses else 'completions'}"
        )

    print(f"\n{'=' * 60}")
    print(f"[{label}] model={provider.model}{endpoint_info}")
    print(f"{'=' * 60}")

    messages = [HumanMessage(content=prompt)]
    reasoning_len = 0
    content_len = 0
    usage = None
    start = time.monotonic()

    try:
        async for chunk in provider.stream(messages):
            for choice in chunk.choices:
                delta = choice.delta
                if delta.reasoning_content:
                    if reasoning_len == 0:
                        print("\n  [thinking] ", end="", flush=True)
                    print(delta.reasoning_content, end="", flush=True)
                    reasoning_len += len(delta.reasoning_content)
                if delta.content:
                    if content_len == 0:
                        if reasoning_len > 0:
                            print(f"\n  [thinking done] {reasoning_len} chars")
                        print("\n  [content]  ", end="", flush=True)
                    print(delta.content, end="", flush=True)
                    content_len += len(delta.content)
            if chunk.usage:
                usage = chunk.usage
    except Exception as e:
        print(f"\n  [ERROR] {type(e).__name__}: {e}")
        return

    elapsed = time.monotonic() - start
    print("\n\n  --- results ---")
    print(f"  reasoning chars: {reasoning_len}")
    print(f"  content chars:   {content_len}")
    print(f"  elapsed:         {elapsed:.1f}s")
    if usage:
        parts = [
            f"in={usage.prompt_tokens}",
            f"out={usage.completion_tokens}",
            f"total={usage.total_tokens}",
        ]
        if usage.cached_tokens:
            parts.append(f"cached={usage.cached_tokens}")
        if usage.thoughts_tokens:
            parts.append(f"thoughts={usage.thoughts_tokens}")
        print(f"  usage: {' '.join(parts)}")
    else:
        print("  usage: (none)")


async def run_chat(
    provider: LLMProviderBase,
    prompt: str,
    *,
    label: str = "",
):
    """Non-streaming chat call."""
    endpoint_info = ""
    if hasattr(provider, "_endpoint_type"):
        endpoint_info = f" endpoint={provider._endpoint_type}"
    elif hasattr(provider, "_use_responses"):
        endpoint_info = (
            f" endpoint={'responses' if provider._use_responses else 'completions'}"
        )

    print(f"\n{'=' * 60}")
    print(f"[{label}] model={provider.model}{endpoint_info} (non-streaming)")
    print(f"{'=' * 60}")

    messages = [HumanMessage(content=prompt)]
    start = time.monotonic()

    try:
        result = await provider.chat(messages)
    except Exception as e:
        print(f"\n  [ERROR] {type(e).__name__}: {e}")
        return

    elapsed = time.monotonic() - start
    reasoning = result.reasoning_content or ""
    content = result.content or ""

    if reasoning:
        preview = reasoning[:200] + ("..." if len(reasoning) > 200 else "")
        print(f"\n  [thinking] {preview}")
    preview = content[:300] + ("..." if len(content) > 300 else "")
    print(f"\n  [content]  {preview}")
    print("\n  --- results ---")
    print(f"  reasoning chars: {len(reasoning)}")
    print(f"  content chars:   {len(content)}")
    print(f"  elapsed:         {elapsed:.1f}s")
