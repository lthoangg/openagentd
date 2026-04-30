"""memory_flush — deprecated stub.

Notes are written exclusively by the ``note`` tool.
This module is kept only because ``member.py`` calls ``build_memory_flush_hook``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.providers.base import LLMProviderBase


def build_memory_flush_hook(
    llm_provider: "LLMProviderBase",
    prompt_token_threshold: int,
) -> None:
    """Deprecated — always returns None."""
    return None
