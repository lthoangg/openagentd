"""OpenAI Codex provider — ChatGPT subscription-based access via OAuth.

Hits the Codex-specific Responses API endpoint used by the Codex CLI and
opencode, authenticating with a ChatGPT OAuth access token.

Endpoint:  https://chatgpt.com/backend-api/codex/responses
Auth:      Bearer {access_token} + ChatGPT-Account-Id header

Token resolution order:
    1. ``{CACHE_DIR}/codex_oauth.json`` (written by ``openagentd auth codex``)

Usage::

    # After running: openagentd auth codex
    provider = CodexProvider(model="gpt-5.4")
    msg = await provider.chat([HumanMessage(content="Hi")])
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.agent.providers.base import LLMProviderBase
from app.agent.providers.codex.oauth import CodexOAuth
from app.agent.providers.openai.responses import ResponsesHandler
from app.agent.schemas.chat import AssistantMessage, ChatMessage, SystemMessage

CODEX_API_BASE = "https://chatgpt.com/backend-api/codex"

_DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "openagentd/1.0.0",
    "originator": "openagentd",
}


class _CodexResponsesHandler(ResponsesHandler):
    """ResponsesHandler variant for the Codex endpoint.

    The Codex endpoint requires a non-empty ``instructions`` field and rejects
    system messages embedded inside ``input``.  This subclass extracts any
    leading SystemMessage into ``instructions`` before building the request.
    """

    def build_request(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None,
        stream: bool,
        merged: dict[str, Any],
    ) -> dict[str, Any]:
        # Separate system messages from the rest
        system_parts: list[str] = []
        non_system: list[ChatMessage] = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                if msg.content:
                    system_parts.append(msg.content)
            else:
                non_system.append(msg)

        body = super().build_request(non_system, tools, stream, merged)

        # instructions is required and must be non-empty
        body["instructions"] = "\n\n".join(system_parts)
        # Codex endpoint requires store=false explicitly
        body["store"] = False
        return body


def _load_token() -> tuple[str, str | None]:
    """Return (access_token, account_id) from cached oauth credentials.

    Refreshes the token if it is expired.
    Raises ValueError if no credentials are found.
    """
    oauth = CodexOAuth.load()
    if not oauth:
        raise ValueError(
            "Codex OAuth credentials not found. Run:\n"
            "  openagentd auth codex\n"
            "to authenticate with your ChatGPT account."
        )
    if oauth.is_expired():
        logger.info("codex_token_expired refreshing")
        try:
            oauth = oauth.refresh()
        except Exception as exc:
            raise ValueError(
                f"Codex token refresh failed: {exc}\nRun: openagentd auth codex"
            ) from exc
    return oauth.access_token.get_secret_value(), oauth.account_id


class CodexProvider(LLMProviderBase):
    """OpenAI Codex provider (ChatGPT subscription).

    Uses the Responses API endpoint at chatgpt.com, authenticated with a
    ChatGPT OAuth token obtained via ``openagentd auth codex``.

    Args:
        model: Model name, e.g. ``"gpt-5.4"``, ``"gpt-5.1-codex"``.
        temperature: Ignored by Responses API (accepted for API compatibility).
        top_p: Ignored by Responses API (accepted for API compatibility).
        max_tokens: Hard cap on completion tokens.
        model_kwargs: Extra request body fields passed as-is.
    """

    def __init__(
        self,
        model: str,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        model_kwargs: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            model_kwargs=model_kwargs,
        )

        access_token, account_id = _load_token()
        self.model = model

        headers = {
            **_DEFAULT_HEADERS,
            "Authorization": f"Bearer {access_token}",
        }
        if account_id:
            headers["ChatGPT-Account-Id"] = account_id

        self._responses = _CodexResponsesHandler(model, CODEX_API_BASE, headers)

        logger.debug("codex_provider model={}", model)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        **kwargs: Any,
    ) -> AssistantMessage:
        merged = self._merged_kwargs(**kwargs)
        return await self._responses.chat(messages, tools, merged)

    async def stream(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        **kwargs: Any,
    ):
        merged = self._merged_kwargs(**kwargs)
        async for chunk in self._responses.stream(messages, tools, merged):
            yield chunk
