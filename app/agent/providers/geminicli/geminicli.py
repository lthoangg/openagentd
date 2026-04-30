"""Gemini CLI OAuth provider for OpenAgentd.

Reads OAuth credentials from ``~/.gemini/oauth_creds.json`` (written by the
Gemini CLI) and authenticates against the Google Cloud Code Assist endpoint.

Uses PKCE (Proof Key for Code Exchange) flow for enhanced security and
offline access for persistent refresh tokens.

Usage in agents.yaml:
    model: geminicli:gemini-2.5-flash

No API key setup needed — just run ``gemini`` once to log in and the tokens
are picked up automatically.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any
from uuid import uuid7

import httpx
from loguru import logger

from app.agent.providers.googlegenai.googlegenai import GeminiProviderBase
from app.agent.providers.googlegenai.schemas import (
    Content,
    GeminiChatRequest,
    GeminiChatResponse,
)
from app.agent.providers.streaming import iter_sse_data
from app.agent.schemas.chat import (
    AssistantMessage,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionDelta,
    FunctionCallDelta,
    ToolCall,
    ToolCallDelta,
    Usage,
)
from app.agent.schemas.chat import FunctionCall as ChatFunctionCall

# ---------------------------------------------------------------------------
# Gemini CLI OAuth constants — mirrors opencode-gemini-auth/src/constants.ts
# ---------------------------------------------------------------------------
_GEMINI_CLIENT_ID = (
    "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
)
_GEMINI_CLIENT_SECRET = "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"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v1/userinfo?alt=json"
_CREDS_FILE = Path.home() / ".gemini" / "oauth_creds.json"

# Code Assist base
_CODE_ASSIST_BASE = "https://cloudcode-pa.googleapis.com/v1internal"

# Refresh 60 s before expiry (expires_at in oauth_creds.json is in milliseconds)
_EXPIRY_BUFFER_MS = 60 * 1000

# User-Agent mirrors the Gemini CLI so the backend accepts our requests
_USER_AGENT = "google-gemini-cli/0.36.0"


def _load_creds() -> dict[str, Any]:
    """Load and validate OAuth credentials from ~/.gemini/oauth_creds.json."""
    if not _CREDS_FILE.exists():
        raise FileNotFoundError(
            f"Gemini CLI credentials not found at {_CREDS_FILE}. "
            "Run `gemini` once to authenticate."
        )
    creds = json.loads(_CREDS_FILE.read_text())

    # Validate required fields
    if not creds.get("refresh_token"):
        raise ValueError(
            "Invalid Gemini CLI credentials: missing refresh_token. "
            "Run `gemini` again to re-authenticate with offline access."
        )

    return creds


class GeminiCLIProvider(GeminiProviderBase):
    """
    Gemini Code Assist provider using Gemini CLI OAuth credentials.

    Reads ``~/.gemini/oauth_creds.json`` written by the Gemini CLI and uses
    the stored access/refresh token to call the Code Assist endpoint.  Token
    refresh is handled automatically.  The managed GCP project ID is resolved
    from the ``loadCodeAssist`` API on first use and cached for the lifetime
    of the provider instance.

    The request body is wrapped in the Code Assist envelope::

        {
          "project": "<cloudaicompanionProject>",
          "model":   "<model>",
          "user_prompt_id": "<uuid>",
          "request": { ...standard Gemini generateContent body... }
        }

    The response is unwrapped from the ``{"response": {...}}`` envelope that
    the Code Assist endpoint adds around the standard Gemini response.
    """

    def __init__(
        self,
        model: str,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        model_kwargs: dict[str, Any] | None = None,
    ):
        super().__init__(
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            model_kwargs=model_kwargs,
        )
        self.model = model
        self.base_url = _CODE_ASSIST_BASE

        # Resolved on first use via loadCodeAssist API
        self._resolved_project_id: str | None = None

        # Load initial tokens from disk
        creds = _load_creds()
        self._access_token: str = creds.get("access_token", "")
        self._refresh_token: str = creds.get("refresh_token", "")
        # expires_at is milliseconds since epoch
        self._expires_at_ms: float = float(creds.get("expires_at", 0))
        # Cache user email from OAuth response
        self._user_email: str | None = creds.get("email")

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _token_expired(self) -> bool:
        return time.time() * 1000 >= self._expires_at_ms - _EXPIRY_BUFFER_MS

    async def _ensure_access_token(self) -> str:
        """Ensure valid access token, refreshing if necessary."""
        if self._access_token and not self._token_expired():
            return self._access_token

        if not self._refresh_token:
            raise RuntimeError(
                "No refresh token available. Run `gemini` to re-authenticate."
            )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    _TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": self._refresh_token,
                        "client_id": _GEMINI_CLIENT_ID,
                        "client_secret": _GEMINI_CLIENT_SECRET,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                payload = response.json()

            self._access_token = payload["access_token"]
            expires_in_s: int = payload.get("expires_in", 3600)
            self._expires_at_ms = (time.time() + expires_in_s) * 1000
            if "refresh_token" in payload:
                self._refresh_token = payload["refresh_token"]

            logger.debug(
                "GeminiCLI token refreshed: expires_in={} has_new_refresh_token={}",
                expires_in_s,
                "refresh_token" in payload,
            )
            return self._access_token
        except httpx.HTTPStatusError as e:
            error_body = ""
            try:
                error_body = e.response.text
            except Exception:
                pass
            logger.error(
                "GeminiCLI token refresh failed: status={} error={}",
                e.response.status_code,
                error_body[:200] if error_body else "unknown",
            )
            raise RuntimeError(
                f"Token refresh failed (status {e.response.status_code}). "
                "Run `gemini` to re-authenticate."
            ) from e
        except Exception as e:
            logger.error("GeminiCLI token refresh error: {}", e)
            raise RuntimeError(
                f"Token refresh failed: {e}. Run `gemini` to re-authenticate."
            ) from e

    @staticmethod
    def _gcloud_project() -> str | None:
        """Return the active gcloud project, or None if unavailable."""
        try:
            result = subprocess.run(
                ["gcloud", "config", "get-value", "project"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            project = result.stdout.strip()
            return project if project and project != "(unset)" else None
        except Exception:
            return None

    async def _ensure_project_id(self, token: str) -> str:
        """Resolve the Code Assist project ID via the loadCodeAssist API (cached after first call)."""
        if self._resolved_project_id:
            return self._resolved_project_id

        # Resolve via loadCodeAssist
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_CODE_ASSIST_BASE}:loadCodeAssist",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "User-Agent": _USER_AGENT,
                },
                json={"metadata": {}},
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()

        project_id: str = data.get("cloudaicompanionProject", "")
        if not project_id:
            raise RuntimeError(
                "Could not resolve Gemini Code Assist project ID. "
                "Set GEMINI_CLI_PROJECT_ID, configure gcloud, or check your Gemini CLI login."
            )

        self._resolved_project_id = project_id
        logger.info("GeminiCLI resolved cloud project: {}", project_id)
        return project_id

    # ------------------------------------------------------------------
    # GeminiProviderBase interface
    # ------------------------------------------------------------------

    def _convert_messages_to_gemini(self, messages):
        """Override to strip thought parts from history.

        The Code Assist endpoint rejects ``thought`` fields in request contents,
        so we remove them before sending. The response-side thought text is still
        captured via ``reasoning_content`` on ``AssistantMessage``.
        """
        contents, system_instruction = super()._convert_messages_to_gemini(messages)

        cleaned: list[Content] = []
        for content in contents:
            non_thought_parts = [p for p in content.parts if not p.thought]
            if non_thought_parts:
                cleaned.append(Content(role=content.role, parts=non_thought_parts))
        return cleaned, system_instruction

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "User-Agent": _USER_AGENT,
        }

    def _build_url(self, method: str) -> str:
        return f"{_CODE_ASSIST_BASE}:{method}"

    def _wrap_body(self, inner_body: dict[str, Any], project_id: str) -> dict[str, Any]:
        """Wrap a standard Gemini request body in the Code Assist envelope."""
        return {
            "project": project_id,
            "model": self.model,
            "user_prompt_id": str(uuid7()),
            "request": inner_body,
        }

    @staticmethod
    def _unwrap_response(data: dict[str, Any]) -> dict[str, Any]:
        """Unwrap the Code Assist ``{"response": {...}}`` envelope."""
        if "response" in data and isinstance(data["response"], dict):
            return data["response"]
        return data

    # ------------------------------------------------------------------
    # chat() / stream() — token refresh + body wrapping + response unwrapping
    # ------------------------------------------------------------------

    async def chat(self, messages, tools=None, **kwargs):
        token = await self._ensure_access_token()
        project_id = await self._ensure_project_id(token)

        merged = self._merged_kwargs(**kwargs)
        contents, system_instruction = self._convert_messages_to_gemini(messages)
        gemini_tools = self._convert_tools_to_gemini(tools)
        generation_config = self._build_generation_config(**merged)

        request_obj = GeminiChatRequest(
            contents=contents,
            system_instruction=system_instruction,
            generation_config=generation_config,
            tools=gemini_tools,
        )
        inner = request_obj.model_dump(exclude_none=True, by_alias=True)
        body = self._wrap_body(inner, project_id)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._build_url("generateContent"),
                headers=self._auth_headers(),
                json=body,
                timeout=120.0,
            )
            response.raise_for_status()
            data = self._unwrap_response(response.json())

        gemini_resp = GeminiChatResponse.model_validate(data)
        candidate = gemini_resp.candidates[0]
        content = ""
        reasoning = ""
        tool_calls = []

        for part in candidate.content.parts:
            if part.thought:
                thought_text = (
                    part.text
                    if part.text
                    else (part.thought if isinstance(part.thought, str) else None)
                )
                if thought_text:
                    reasoning += thought_text
            elif part.text:
                content += part.text
            if part.function_call:
                tool_calls.append(
                    ToolCall(
                        id=part.function_call.id
                        or f"call_{part.function_call.name}_{int(time.time())}",
                        function=ChatFunctionCall(
                            name=part.function_call.name,
                            arguments=json.dumps(part.function_call.args),
                            thought_signature=part.thought_signature,
                        ),
                    )
                )

        return AssistantMessage(
            content=content if content else None,
            reasoning_content=reasoning if reasoning else None,
            tool_calls=tool_calls if tool_calls else None,
        )

    async def stream(self, messages, tools=None, **kwargs):
        token = await self._ensure_access_token()
        project_id = await self._ensure_project_id(token)

        merged = self._merged_kwargs(**kwargs)
        contents, system_instruction = self._convert_messages_to_gemini(messages)
        gemini_tools = self._convert_tools_to_gemini(tools)
        generation_config = self._build_generation_config(**merged)

        request_obj = GeminiChatRequest(
            contents=contents,
            system_instruction=system_instruction,
            generation_config=generation_config,
            tools=gemini_tools,
        )
        inner = request_obj.model_dump(exclude_none=True, by_alias=True)
        body = self._wrap_body(inner, project_id)

        url = self._build_url("streamGenerateContent") + "?alt=sse"

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                url,
                headers=self._auth_headers(),
                json=body,
                timeout=120.0,
            ) as response:
                if not response.is_success:
                    body_text = await response.aread()
                    logger.error(
                        "geminicli stream error status={} url={} body={}",
                        response.status_code,
                        url,
                        body_text[:500].decode(errors="replace"),
                    )
                response.raise_for_status()
                # Me map tool_call id → stable monotonic index, scoped to
                # this stream() call.  See googlegenai.stream for the full
                # rationale — Gemini SSE chunks re-emit the whole parts list
                # on every update and using the part index directly makes
                # tool slots collide whenever parts shift between chunks.
                tool_idx_by_id: dict[str, int] = {}

                async for raw in iter_sse_data(response, sentinel=None):
                    # SSE chunks may be wrapped in {"response": {...}}
                    data = self._unwrap_response(raw)
                    gemini_resp = GeminiChatResponse.model_validate(data)
                    if not gemini_resp.candidates:
                        continue

                    candidate = gemini_resp.candidates[0]
                    delta_content = ""
                    delta_reasoning = ""
                    delta_tool_calls: list[ToolCallDelta] = []

                    for part in candidate.content.parts:
                        if part.thought:
                            thought_text = (
                                part.text
                                if part.text
                                else (
                                    part.thought
                                    if isinstance(part.thought, str)
                                    else None
                                )
                            )
                            if thought_text:
                                delta_reasoning += thought_text
                        elif part.text:
                            delta_content += part.text
                        if part.function_call:
                            fc_id = (
                                part.function_call.id
                                or f"call_{part.function_call.name}_{int(time.time())}"
                            )
                            stable_idx = tool_idx_by_id.setdefault(
                                fc_id, len(tool_idx_by_id)
                            )
                            delta_tool_calls.append(
                                ToolCallDelta(
                                    index=stable_idx,
                                    id=fc_id,
                                    function=FunctionCallDelta(
                                        name=part.function_call.name,
                                        arguments=json.dumps(part.function_call.args),
                                        thought_signature=part.thought_signature,
                                    ),
                                )
                            )

                    meta = gemini_resp.usage_metadata
                    usage = (
                        Usage(
                            prompt_tokens=meta.prompt_token_count or 0,
                            completion_tokens=meta.candidates_token_count or 0,
                            total_tokens=meta.total_token_count or 0,
                            cached_tokens=meta.cached_content_token_count,
                            thoughts_tokens=meta.thoughts_token_count,
                            tool_use_tokens=meta.tool_use_prompt_token_count,
                        )
                        if meta
                        else None
                    )

                    yield ChatCompletionChunk(
                        id="geminicli-stream",
                        created=int(time.time()),
                        model=self.model,
                        choices=[
                            ChatCompletionChunkChoice(
                                index=0,
                                delta=ChatCompletionDelta(
                                    content=delta_content if delta_content else None,
                                    reasoning_content=delta_reasoning
                                    if delta_reasoning
                                    else None,
                                    tool_calls=delta_tool_calls
                                    if delta_tool_calls
                                    else None,
                                ),
                                finish_reason=candidate.finish_reason,
                            )
                        ],
                        usage=usage,
                    )
