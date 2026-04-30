"""GitHub Copilot provider.

Subclass of :class:`OpenAIProvider` that delegates wire conversion,
streaming, and parsing to the canonical OpenAI handlers.

The Copilot gateway is OpenAI-compatible: messages, tools, and stream
events match the OpenAI Chat Completions and Responses formats. Only a
few facets differ:

* **Headers.** Copilot expects ``Openai-Intent``, ``x-initiator``, and a
  ``User-Agent`` alongside the OAuth bearer.
* **Per-model endpoint routing.** Some Copilot-hosted models accept only
  ``/chat/completions``; others accept only ``/responses``. The mapping
  is hardcoded in :data:`_MODEL_ENDPOINT_MAP`.
* **Reasoning gating.** ``reasoning_effort`` (Chat Completions) is
  accepted only by a whitelisted subset of OpenAI models served via
  Copilot; Claude / Gemini / Grok reject it. Other reasoning fields
  flow through unchanged.
* **Responses request body.** Copilot's gateway accepts ``temperature``
  and ``top_p`` on ``/responses`` (it ignores them); OpenAI's strict
  endpoint rejects them. The Copilot subclass adds them.

Token resolution order (preserved from the previous implementation):

1. Explicit ``github_token`` constructor arg.
2. ``{CACHE_DIR}/copilot_oauth.json`` (written by ``openagentd auth copilot``).
3. ``GITHUB_COPILOT_TOKEN`` env var.
"""

from __future__ import annotations

from typing import Any

from pydantic.types import SecretStr

from app.agent.providers.copilot.oauth import CopilotOAuth
from app.agent.providers.openai import OpenAIProvider
from app.agent.providers.openai.completions import CompletionsHandler
from app.agent.providers.openai.responses import ResponsesHandler
from app.agent.schemas.chat import ChatMessage, Usage

COPILOT_API_BASE = "https://api.githubcopilot.com"

_DEFAULT_HEADERS: dict[str, str] = {
    "Content-Type": "application/json",
    "User-Agent": "openagentd/1.0.0",
    "Openai-Intent": "conversation-edits",
    "x-initiator": "user",
}

# Models that accept ``reasoning_effort`` on /chat/completions. Other
# Copilot-hosted models reject the field outright.
_REASONING_EFFORT_MODELS: frozenset[str] = frozenset(
    {
        "gpt-5-mini",
        "gpt-5.1",
        "gpt-5.2",
        "gpt-5.4-mini",
    }
)

# Per-model endpoint preference. Models not listed default to "completions".
# "completions" → /chat/completions, "responses" → /responses.
_MODEL_ENDPOINT_MAP: dict[str, str] = {
    "gpt-5-mini": "completions",
    "gpt-5.1": "completions",
    "gpt-5.2": "completions",
    "claude-sonnet-4": "completions",
    "claude-sonnet-4.5": "completions",
    "claude-opus-4.5": "completions",
    "claude-haiku-4.5": "completions",
    "gemini-3.1-pro-preview": "completions",
    "gemini-3-flash-preview": "completions",
    "gemini-2.5-pro": "completions",
    "grok-code-fast-1": "completions",
    "gpt-5.4-mini": "responses",
    "gpt-5.4": "responses",
    "gpt-5.2-codex": "responses",
    "gpt-5.3-codex": "responses",
}


def _endpoint_for_model(model: str) -> str:
    """Return ``"completions"`` or ``"responses"`` for ``model``."""
    return _MODEL_ENDPOINT_MAP.get(model, "completions")


def _resolve_github_token(explicit: str | SecretStr | None) -> str | None:
    """Resolve a GitHub token: explicit arg → oauth file → env var."""
    if explicit:
        return (
            explicit.get_secret_value() if isinstance(explicit, SecretStr) else explicit
        )
    oauth = CopilotOAuth.load()
    if oauth:
        return oauth.github_token.get_secret_value()
    import os

    return os.getenv("GITHUB_COPILOT_TOKEN") or None


class _CopilotCompletionsHandler(CompletionsHandler):
    """Copilot-specific overrides for /chat/completions.

    * Reasoning gating — only forward ``reasoning_effort`` for models the
      Copilot gateway accepts; Claude / Gemini / Grok reject the field.
    * Usage extraction — Copilot reports ``reasoning_tokens`` at the top
      level of the ``usage`` object (OpenAI nests it under
      ``completion_tokens_details``). Read both, top-level first.
    """

    def customize_thinking(self, merged: dict[str, Any], body: dict[str, Any]) -> None:
        thinking_level = merged.get("thinking_level")
        if (
            thinking_level
            and thinking_level not in ("none", "off")
            and self.model in _REASONING_EFFORT_MODELS
        ):
            body["reasoning_effort"] = thinking_level

    def _usage_from_openai(self, u: Any) -> Usage:
        cached = None
        if u.prompt_tokens_details:
            cached = u.prompt_tokens_details.cached_tokens or None
        # Copilot quirk: reasoning_tokens at the top level of usage.
        # Fall back to OpenAI's nested location if missing.
        thoughts = getattr(u, "reasoning_tokens", None) or None
        if not thoughts and u.completion_tokens_details:
            thoughts = u.completion_tokens_details.reasoning_tokens or None
        return Usage(
            prompt_tokens=u.prompt_tokens,
            completion_tokens=u.completion_tokens,
            total_tokens=u.total_tokens,
            cached_tokens=cached,
            thoughts_tokens=thoughts,
        )


class _CopilotResponsesHandler(ResponsesHandler):
    """Copilot-specific overrides for /responses.

    * Request shape — Copilot's Responses gateway accepts (and ignores)
      ``temperature`` and ``top_p``. Passing them through preserves the
      previous wire format. The strict OpenAI Responses endpoint rejects
      these fields, which is why the canonical handler omits them.
    * Streaming events — Copilot's gateway uses ``call_id`` (not
      ``item_id``) on ``response.function_call_arguments.delta`` /
      ``done`` and embeds the function ``name`` directly on those events.
      The canonical OpenAI parser only reads ``item_id`` and never
      expects an inline ``name``.
    """

    def build_request(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None,
        stream: bool,
        merged: dict[str, Any],
    ) -> dict[str, Any]:
        body = super().build_request(messages, tools, stream, merged)
        if merged.get("temperature") is not None:
            body["temperature"] = merged["temperature"]
        if merged.get("top_p") is not None:
            body["top_p"] = merged["top_p"]
        return body

    def _extract_call_id_and_name(self, event: dict[str, Any]) -> tuple[str, str]:
        call_id = event.get("item_id") or event.get("call_id", "")
        return call_id, event.get("name", "")


class CopilotProvider(OpenAIProvider):
    """GitHub Copilot provider (OpenAI-compatible).

    Auto-routes to ``/chat/completions`` or ``/responses`` based on the
    model (see :data:`_MODEL_ENDPOINT_MAP`).

    Args:
        model: Model name, e.g. ``"gpt-5-mini"``, ``"claude-sonnet-4"``.
        github_token: Optional explicit GitHub token. Falls back to the
            OAuth cache file and ``GITHUB_COPILOT_TOKEN`` env var.
        temperature: Sampling temperature (Chat Completions only; ignored
            by /responses on the strict OpenAI endpoint, accepted but
            ignored by the Copilot gateway).
        top_p: Nucleus sampling cutoff (same caveats as ``temperature``).
        max_tokens: Hard cap on completion tokens.
        model_kwargs: Extra request body fields. Notable keys:
            ``thinking_level`` (str) — only forwarded as
            ``reasoning_effort`` for models in
            :data:`_REASONING_EFFORT_MODELS`.
    """

    def __init__(
        self,
        model: str,
        github_token: str | SecretStr | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        model_kwargs: dict[str, Any] | None = None,
    ) -> None:
        token = _resolve_github_token(github_token)
        if not token:
            raise ValueError(
                "GitHub token not found.  Run:\n"
                "  openagentd auth copilot\n"
                "Or set GITHUB_COPILOT_TOKEN env var."
            )
        super().__init__(
            api_key=token,
            model=model,
            base_url=COPILOT_API_BASE,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            model_kwargs=model_kwargs,
        )

    # Convenience aliases for callers that think in Copilot-specific terms.
    @property
    def _github_token(self) -> str:
        return self.api_key

    @property
    def _endpoint_type(self) -> str:
        return "responses" if self._use_responses else "completions"

    @property
    def _request_url(self) -> str:
        return f"{COPILOT_API_BASE}/{'responses' if self._use_responses else 'chat/completions'}"

    def _build_headers(self) -> dict[str, str]:
        return {**_DEFAULT_HEADERS, "Authorization": f"Bearer {self.api_key}"}

    def _use_responses_for(self, model_kwargs: dict[str, Any]) -> bool:
        return _endpoint_for_model(self.model) == "responses"

    def _make_completions_handler(
        self, model: str, base_url: str, headers: dict[str, str]
    ) -> CompletionsHandler:
        return _CopilotCompletionsHandler(model, base_url, headers)

    def _make_responses_handler(
        self, model: str, base_url: str, headers: dict[str, str]
    ) -> ResponsesHandler:
        return _CopilotResponsesHandler(model, base_url, headers)
