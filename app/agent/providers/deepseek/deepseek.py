"""DeepSeek provider — OpenAI-compatible API.

Thin wrapper around ``OpenAIProvider`` that points at the DeepSeek
inference endpoint and reads ``DEEPSEEK_API_KEY`` from settings or
environment.

Endpoint:  https://api.deepseek.com/v1
Auth:      Bearer {DEEPSEEK_API_KEY}
Docs:      https://api-docs.deepseek.com/

Models:
    deepseek-v4-flash  — fast general-purpose chat
    deepseek-v4-pro    — higher-quality variant

Reasoning-model outputs via ``reasoning_content`` are already supported
by the OpenAI schema layer (see ``app/agent/providers/openai/schemas.py``),
so no extra wiring is required here.

Token resolution order:
    1. ``Settings.DEEPSEEK_API_KEY`` (from ``.env`` or environment)
    2. ``DEEPSEEK_API_KEY`` environment variable

Usage::

    model: deepseek:deepseek-v4-flash
    model: deepseek:deepseek-v4-pro
"""

from __future__ import annotations

from typing import Any

from app.agent.providers.openai import OpenAIProvider

DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"


class DeepSeekProvider(OpenAIProvider):
    """DeepSeek provider (OpenAI-compatible).

    Delegates entirely to ``OpenAIProvider`` with the DeepSeek base URL.
    Vision is not supported by current DeepSeek models.

    Args:
        api_key: DeepSeek API key from https://platform.deepseek.com.
        model: Model name, e.g. ``"deepseek-v4-flash"``, ``"deepseek-v4-pro"``.
        temperature: Sampling temperature (0-2).
        top_p: Nucleus sampling probability mass cutoff.
        max_tokens: Hard cap on completion tokens.
        model_kwargs: Extra request body fields passed as-is.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        model_kwargs: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=DEEPSEEK_API_BASE,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            model_kwargs=model_kwargs,
        )
