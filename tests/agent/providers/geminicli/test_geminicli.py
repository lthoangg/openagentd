"""Tests for app/providers/geminicli/geminicli.py — GeminiCLIProvider."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from app.agent.providers.geminicli.geminicli import (
    GeminiCLIProvider,
    _CODE_ASSIST_BASE,
    _TOKEN_URL,
    _load_creds,
)
from app.agent.schemas.chat import (
    AssistantMessage,
    HumanMessage,
    SystemMessage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_CREDS = {
    "access_token": "fake-access-token",
    "refresh_token": "fake-refresh-token",
    "expires_at": int((time.time() + 7200) * 1000),  # 2 h from now
}

_EXPIRED_CREDS = {
    "access_token": "stale-token",
    "refresh_token": "fake-refresh-token",
    "expires_at": int((time.time() - 3600) * 1000),  # 1 h ago
}

_PROJECT_ID = "test-project-123"

_LOAD_CODE_ASSIST_URL = f"{_CODE_ASSIST_BASE}:loadCodeAssist"
_GENERATE_URL = f"{_CODE_ASSIST_BASE}:generateContent"
_STREAM_URL = f"{_CODE_ASSIST_BASE}:streamGenerateContent?alt=sse"


def _make_provider(creds: dict | None = None) -> GeminiCLIProvider:
    """Create a provider with mocked credential file."""
    if creds is None:
        creds = _FAKE_CREDS
    with patch("app.agent.providers.geminicli.geminicli._CREDS_FILE") as mock_path:
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = json.dumps(creds)
        provider = GeminiCLIProvider(model="gemini-2.5-flash")
    # Pre-set the project so most tests don't need to mock loadCodeAssist
    provider._resolved_project_id = _PROJECT_ID
    return provider


def _gemini_response(parts: list[dict]) -> dict:
    return {
        "candidates": [
            {
                "content": {"parts": parts, "role": "model"},
                "finishReason": "STOP",
                "index": 0,
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 10,
            "candidatesTokenCount": 20,
            "totalTokenCount": 30,
        },
    }


def _code_assist_response(inner: dict) -> dict:
    """Wrap a standard Gemini response in the Code Assist envelope."""
    return {"response": inner}


# ---------------------------------------------------------------------------
# _load_creds
# ---------------------------------------------------------------------------


def test_load_creds_missing_file(tmp_path):
    missing = tmp_path / "no_such_file.json"
    with patch("app.agent.providers.geminicli.geminicli._CREDS_FILE", missing):
        with pytest.raises(FileNotFoundError, match="Gemini CLI credentials not found"):
            _load_creds()


def test_load_creds_reads_json(tmp_path):
    creds_file = tmp_path / "oauth_creds.json"
    creds_file.write_text(json.dumps(_FAKE_CREDS))
    with patch("app.agent.providers.geminicli.geminicli._CREDS_FILE", creds_file):
        result = _load_creds()
    assert result["access_token"] == "fake-access-token"
    assert result["refresh_token"] == "fake-refresh-token"


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


def test_init_stores_model_and_tokens():
    provider = _make_provider()
    provider._resolved_project_id = None  # clear helper override
    assert provider.model == "gemini-2.5-flash"
    assert provider._access_token == "fake-access-token"
    assert provider._refresh_token == "fake-refresh-token"
    assert provider.base_url == _CODE_ASSIST_BASE


def test_init_raises_when_creds_missing(tmp_path):
    missing = tmp_path / "no_creds.json"
    with patch("app.agent.providers.geminicli.geminicli._CREDS_FILE", missing):
        with pytest.raises(FileNotFoundError):
            GeminiCLIProvider(model="gemini-2.5-flash")


# ---------------------------------------------------------------------------
# _token_expired
# ---------------------------------------------------------------------------


def test_token_not_expired():
    provider = _make_provider(_FAKE_CREDS)
    assert provider._token_expired() is False


def test_token_expired():
    provider = _make_provider(_EXPIRED_CREDS)
    assert provider._token_expired() is True


# ---------------------------------------------------------------------------
# _ensure_access_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_access_token_valid_returns_cached():
    provider = _make_provider(_FAKE_CREDS)
    token = await provider._ensure_access_token()
    assert token == "fake-access-token"


@pytest.mark.asyncio
@respx.mock
async def test_ensure_access_token_refreshes_when_expired():
    provider = _make_provider(_EXPIRED_CREDS)
    new_expiry = int((time.time() + 3600) * 1000)

    respx.post(_TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "new-access-token",
                "expires_in": 3600,
                "refresh_token": "new-refresh-token",
            },
        )
    )

    token = await provider._ensure_access_token()

    assert token == "new-access-token"
    assert provider._access_token == "new-access-token"
    assert provider._refresh_token == "new-refresh-token"
    assert provider._expires_at_ms > new_expiry - 5000  # within a few ms


@pytest.mark.asyncio
async def test_ensure_access_token_no_refresh_token_raises():
    provider = _make_provider(_EXPIRED_CREDS)
    provider._refresh_token = ""

    with pytest.raises(RuntimeError, match="No refresh token available"):
        await provider._ensure_access_token()


@pytest.mark.asyncio
@respx.mock
async def test_ensure_access_token_refresh_without_new_refresh_token():
    """When refresh response omits refresh_token, the old one is retained."""
    provider = _make_provider(_EXPIRED_CREDS)

    respx.post(_TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "refreshed-token", "expires_in": 3600},
        )
    )

    await provider._ensure_access_token()
    assert provider._refresh_token == "fake-refresh-token"


# ---------------------------------------------------------------------------
# _gcloud_project
# ---------------------------------------------------------------------------


def test_gcloud_project_returns_value():
    mock_result = MagicMock()
    mock_result.stdout = "my-gcloud-project\n"
    with patch("subprocess.run", return_value=mock_result):
        result = GeminiCLIProvider._gcloud_project()
    assert result == "my-gcloud-project"


def test_gcloud_project_returns_none_when_unset():
    mock_result = MagicMock()
    mock_result.stdout = "(unset)"
    with patch("subprocess.run", return_value=mock_result):
        result = GeminiCLIProvider._gcloud_project()
    assert result is None


def test_gcloud_project_returns_none_on_exception():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        result = GeminiCLIProvider._gcloud_project()
    assert result is None


def test_gcloud_project_returns_none_for_empty():
    mock_result = MagicMock()
    mock_result.stdout = "   "
    with patch("subprocess.run", return_value=mock_result):
        result = GeminiCLIProvider._gcloud_project()
    assert result is None


# ---------------------------------------------------------------------------
# _ensure_project_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_project_id_returns_cached():
    provider = _make_provider()
    # Already set in _make_provider
    result = await provider._ensure_project_id("any-token")
    assert result == _PROJECT_ID


@pytest.mark.asyncio
@respx.mock
async def test_ensure_project_id_resolves_via_api():
    provider = _make_provider()
    provider._resolved_project_id = None  # clear cache

    respx.post(_LOAD_CODE_ASSIST_URL).mock(
        return_value=httpx.Response(
            200,
            json={"cloudaicompanionProject": "resolved-project-id"},
        )
    )

    result = await provider._ensure_project_id("fake-access-token")
    assert result == "resolved-project-id"
    assert provider._resolved_project_id == "resolved-project-id"


@pytest.mark.asyncio
@respx.mock
async def test_ensure_project_id_raises_when_empty():
    provider = _make_provider()
    provider._resolved_project_id = None

    respx.post(_LOAD_CODE_ASSIST_URL).mock(
        return_value=httpx.Response(200, json={"cloudaicompanionProject": ""})
    )

    with pytest.raises(
        RuntimeError, match="Could not resolve Gemini Code Assist project ID"
    ):
        await provider._ensure_project_id("token")


# ---------------------------------------------------------------------------
# _auth_headers
# ---------------------------------------------------------------------------


def test_auth_headers_contain_bearer_and_user_agent():
    provider = _make_provider()
    headers = provider._auth_headers()
    assert headers["Authorization"] == "Bearer fake-access-token"
    assert "User-Agent" in headers
    assert "google-gemini-cli" in headers["User-Agent"]


# ---------------------------------------------------------------------------
# _build_url
# ---------------------------------------------------------------------------


def test_build_url():
    provider = _make_provider()
    url = provider._build_url("generateContent")
    assert url == f"{_CODE_ASSIST_BASE}:generateContent"


# ---------------------------------------------------------------------------
# _wrap_body / _unwrap_response
# ---------------------------------------------------------------------------


def test_wrap_body_structure():
    provider = _make_provider()
    inner = {"contents": [], "generationConfig": {}}
    wrapped = provider._wrap_body(inner, "my-project")
    assert wrapped["project"] == "my-project"
    assert wrapped["model"] == "gemini-2.5-flash"
    assert "user_prompt_id" in wrapped
    assert wrapped["request"] == inner


def test_unwrap_response_with_envelope():
    inner = {"candidates": []}
    data = {"response": inner}
    assert GeminiCLIProvider._unwrap_response(data) == inner


def test_unwrap_response_without_envelope():
    data = {"candidates": []}
    assert GeminiCLIProvider._unwrap_response(data) == data


def test_unwrap_response_non_dict_envelope():
    """If 'response' is not a dict, return original data."""
    data = {"response": "unexpected-string", "candidates": []}
    assert GeminiCLIProvider._unwrap_response(data) == data


# ---------------------------------------------------------------------------
# _convert_messages_to_gemini — thought stripping
# ---------------------------------------------------------------------------


def test_convert_messages_strips_thought_parts():
    """Thought parts must be removed before sending to Code Assist."""
    from app.agent.schemas.chat import ChatMessage

    provider = _make_provider()
    messages: list[ChatMessage] = [
        AssistantMessage(content="Hello", reasoning_content="hidden thought"),
    ]
    contents, _ = provider._convert_messages_to_gemini(messages)
    # The thought part should be stripped; only the text part remains
    assert len(contents) == 1
    assert all(not p.thought for p in contents[0].parts)
    assert contents[0].parts[0].text == "Hello"


def test_convert_messages_drops_thought_only_message():
    """If an AssistantMessage has only reasoning_content, it is dropped entirely."""
    from app.agent.schemas.chat import ChatMessage

    provider = _make_provider()
    messages: list[ChatMessage] = [
        AssistantMessage(content=None, reasoning_content="pure thought, no content"),
    ]
    contents, _ = provider._convert_messages_to_gemini(messages)
    assert contents == []


def test_convert_messages_keeps_non_thought_parts():
    provider = _make_provider()
    messages = [
        HumanMessage(content="hi"),
        AssistantMessage(content="hello"),
    ]
    contents, _ = provider._convert_messages_to_gemini(messages)
    assert len(contents) == 2
    assert contents[0].parts[0].text == "hi"
    assert contents[1].parts[0].text == "hello"


# ---------------------------------------------------------------------------
# chat()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_chat_success_text_response():
    provider = _make_provider()

    respx.post(_GENERATE_URL).mock(
        return_value=httpx.Response(
            200,
            json=_code_assist_response(_gemini_response([{"text": "Hello from CLI!"}])),
        )
    )

    resp = await provider.chat(messages=[HumanMessage(content="hi")])

    assert isinstance(resp, AssistantMessage)
    assert resp.content == "Hello from CLI!"
    assert resp.tool_calls is None
    assert resp.reasoning_content is None


@pytest.mark.asyncio
@respx.mock
async def test_chat_with_reasoning_in_thought_field():
    """Thought content in thought field (no text) is captured as reasoning_content."""
    provider = _make_provider()

    respx.post(_GENERATE_URL).mock(
        return_value=httpx.Response(
            200,
            json=_code_assist_response(
                _gemini_response(
                    [
                        {"text": "Hello there!"},
                        {"text": "Thinking hard.", "thought": True},
                    ]
                )
            ),
        )
    )

    resp = await provider.chat(messages=[HumanMessage(content="hi")])
    assert resp.content == "Hello there!"
    assert resp.reasoning_content == "Thinking hard."


@pytest.mark.asyncio
@respx.mock
async def test_chat_with_tool_call():
    provider = _make_provider()

    respx.post(_GENERATE_URL).mock(
        return_value=httpx.Response(
            200,
            json=_code_assist_response(
                _gemini_response(
                    [
                        {
                            "functionCall": {
                                "name": "get_weather",
                                "args": {"location": "Paris"},
                            }
                        }
                    ]
                )
            ),
        )
    )

    resp = await provider.chat(
        messages=[HumanMessage(content="weather?")],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "get weather",
                    "parameters": {
                        "type": "object",
                        "properties": {"location": {"type": "string"}},
                    },
                },
            }
        ],
    )

    assert isinstance(resp, AssistantMessage)
    assert resp.tool_calls is not None
    assert resp.tool_calls[0].function.name == "get_weather"
    assert "Paris" in resp.tool_calls[0].function.arguments


@pytest.mark.asyncio
@respx.mock
async def test_chat_passes_system_message():
    provider = _make_provider()
    sent_bodies: list[dict] = []

    def capture(request: httpx.Request) -> httpx.Response:
        sent_bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=_code_assist_response(_gemini_response([{"text": "ok"}])),
        )

    respx.post(_GENERATE_URL).mock(side_effect=capture)

    await provider.chat(
        messages=[
            SystemMessage(content="You are helpful."),
            HumanMessage(content="hello"),
        ]
    )

    inner = sent_bodies[0]["request"]
    assert "systemInstruction" in inner


@pytest.mark.asyncio
@respx.mock
async def test_chat_response_not_wrapped():
    """If the response has no 'response' envelope, it is used as-is."""
    provider = _make_provider()

    respx.post(_GENERATE_URL).mock(
        return_value=httpx.Response(
            200,
            json=_gemini_response([{"text": "Direct response"}]),
        )
    )

    resp = await provider.chat(messages=[HumanMessage(content="hi")])
    assert resp.content == "Direct response"


@pytest.mark.asyncio
@respx.mock
async def test_chat_http_error_raises():
    provider = _make_provider()

    respx.post(_GENERATE_URL).mock(
        return_value=httpx.Response(429, json={"error": "rate limited"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        await provider.chat(messages=[HumanMessage(content="hi")])


@pytest.mark.asyncio
@respx.mock
async def test_chat_refreshes_token_when_expired():
    """chat() calls _ensure_access_token which refreshes when expired."""
    provider = _make_provider(_EXPIRED_CREDS)

    respx.post(_TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "refreshed", "expires_in": 3600},
        )
    )
    respx.post(_GENERATE_URL).mock(
        return_value=httpx.Response(
            200,
            json=_code_assist_response(_gemini_response([{"text": "ok"}])),
        )
    )

    resp = await provider.chat(messages=[HumanMessage(content="hi")])
    assert resp.content == "ok"
    assert provider._access_token == "refreshed"


@pytest.mark.asyncio
@respx.mock
async def test_chat_wraps_body_with_project_and_model():
    provider = _make_provider()
    sent_bodies: list[dict] = []

    def capture(request: httpx.Request) -> httpx.Response:
        sent_bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=_code_assist_response(_gemini_response([{"text": "ok"}])),
        )

    respx.post(_GENERATE_URL).mock(side_effect=capture)

    await provider.chat(messages=[HumanMessage(content="hi")])

    body = sent_bodies[0]
    assert body["project"] == _PROJECT_ID
    assert body["model"] == "gemini-2.5-flash"
    assert "user_prompt_id" in body
    assert "request" in body


# ---------------------------------------------------------------------------
# stream()
# ---------------------------------------------------------------------------


def _sse_line(data: dict) -> str:
    return f"data: {json.dumps(data)}\n"


@pytest.mark.asyncio
@respx.mock
async def test_stream_text_chunks():
    provider = _make_provider()

    chunk1 = _code_assist_response(
        {
            "candidates": [
                {"content": {"parts": [{"text": "Hello"}]}, "finishReason": "STOP"}
            ],
            "usageMetadata": {
                "promptTokenCount": 1,
                "candidatesTokenCount": 1,
                "totalTokenCount": 2,
            },
        }
    )
    chunk2 = _code_assist_response(
        {
            "candidates": [
                {"content": {"parts": [{"text": " world!"}]}, "finishReason": "STOP"}
            ],
            "usageMetadata": {
                "promptTokenCount": 1,
                "candidatesTokenCount": 1,
                "totalTokenCount": 2,
            },
        }
    )
    stream_content = _sse_line(chunk1) + _sse_line(chunk2)

    respx.post(_STREAM_URL).mock(
        return_value=httpx.Response(200, content=stream_content)
    )

    chunks = []
    async for chunk in provider.stream(messages=[HumanMessage(content="hi")]):
        chunks.append(chunk)

    assert len(chunks) == 2
    assert chunks[0].choices[0].delta.content == "Hello"
    assert chunks[1].choices[0].delta.content == " world!"


@pytest.mark.asyncio
@respx.mock
async def test_stream_includes_usage():
    provider = _make_provider()

    data = _code_assist_response(
        {
            "candidates": [
                {"content": {"parts": [{"text": "Hi"}]}, "finishReason": "STOP"}
            ],
            "usageMetadata": {
                "promptTokenCount": 5,
                "candidatesTokenCount": 10,
                "totalTokenCount": 15,
            },
        }
    )

    respx.post(_STREAM_URL).mock(
        return_value=httpx.Response(200, content=_sse_line(data))
    )

    chunks = []
    async for chunk in provider.stream(messages=[HumanMessage(content="hi")]):
        chunks.append(chunk)

    assert chunks[0].usage is not None
    assert chunks[0].usage.prompt_tokens == 5
    assert chunks[0].usage.completion_tokens == 10
    assert chunks[0].usage.total_tokens == 15


@pytest.mark.asyncio
@respx.mock
async def test_stream_with_reasoning():
    provider = _make_provider()

    data = _code_assist_response(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Answer"},
                            {"text": "Reasoning text", "thought": True},
                        ]
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 1,
                "candidatesTokenCount": 1,
                "totalTokenCount": 2,
            },
        }
    )

    respx.post(_STREAM_URL).mock(
        return_value=httpx.Response(200, content=_sse_line(data))
    )

    chunks = []
    async for chunk in provider.stream(messages=[HumanMessage(content="think")]):
        chunks.append(chunk)

    assert chunks[0].choices[0].delta.content == "Answer"
    assert chunks[0].choices[0].delta.reasoning_content == "Reasoning text"


@pytest.mark.asyncio
@respx.mock
async def test_stream_with_tool_call():
    provider = _make_provider()

    data = _code_assist_response(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"functionCall": {"name": "search", "args": {"q": "test"}}}
                        ]
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 1,
                "candidatesTokenCount": 1,
                "totalTokenCount": 2,
            },
        }
    )

    respx.post(_STREAM_URL).mock(
        return_value=httpx.Response(200, content=_sse_line(data))
    )

    chunks = []
    async for chunk in provider.stream(messages=[HumanMessage(content="search")]):
        chunks.append(chunk)

    delta = chunks[0].choices[0].delta
    assert delta.tool_calls is not None
    assert delta.tool_calls[0].function.name == "search"
    assert "test" in delta.tool_calls[0].function.arguments


@pytest.mark.asyncio
@respx.mock
async def test_stream_tool_call_index_stable_when_parts_shift():
    """Same function_call id keeps the same index across chunks even when
    a thought part shows up in a later chunk and shifts the function_call's
    part position.  Without the stable id→index map, the agent_loop would
    treat the second chunk's delta as a new slot and the publisher hook
    would emit a duplicate tool_call SSE event that never completes.
    """
    provider = _make_provider()

    chunk_a = _code_assist_response(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "id": "fc-A",
                                    "name": "read",
                                    "args": {},
                                }
                            }
                        ]
                    },
                    "finishReason": None,
                }
            ],
            "usageMetadata": None,
        }
    )
    chunk_b = _code_assist_response(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"thought": True, "text": "pondering"},
                            {
                                "functionCall": {
                                    "id": "fc-A",
                                    "name": "read",
                                    "args": {"path": "x"},
                                }
                            },
                        ]
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": None,
        }
    )

    respx.post(_STREAM_URL).mock(
        return_value=httpx.Response(
            200, content=_sse_line(chunk_a) + _sse_line(chunk_b)
        )
    )

    chunks = []
    async for c in provider.stream(messages=[HumanMessage(content="hi")]):
        chunks.append(c)

    tc_a = chunks[0].choices[0].delta.tool_calls
    tc_b = chunks[1].choices[0].delta.tool_calls
    assert tc_a is not None and tc_b is not None
    assert tc_a[0].id == "fc-A" and tc_b[0].id == "fc-A"
    # Me stable index across chunks despite thought part shifting layout
    assert tc_a[0].index == tc_b[0].index == 0


@pytest.mark.asyncio
@respx.mock
async def test_stream_tool_call_without_id_gets_fallback_index():
    """A function_call with id=None gets a fallback id and stable index."""
    provider = _make_provider()

    chunk_a = _code_assist_response(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "id": None,
                                    "name": "read",
                                    "args": {},
                                }
                            },
                            {
                                "functionCall": {
                                    "id": "fc-B",
                                    "name": "write",
                                    "args": {},
                                }
                            },
                        ]
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": None,
        }
    )

    respx.post(_STREAM_URL).mock(
        return_value=httpx.Response(200, content=_sse_line(chunk_a))
    )

    chunks = []
    async for c in provider.stream(messages=[HumanMessage(content="hi")]):
        chunks.append(c)

    tcs = chunks[0].choices[0].delta.tool_calls
    assert tcs is not None and len(tcs) == 2
    # Me first tool call (no id) gets fallback and index 0
    assert tcs[0].id.startswith("call_read_")
    assert tcs[0].index == 0
    # Me second tool call gets index 1
    assert tcs[1].id == "fc-B" and tcs[1].index == 1


@pytest.mark.asyncio
@respx.mock
async def test_stream_empty_stream_no_tool_calls():
    """An empty stream (no tool calls) doesn't crash."""
    provider = _make_provider()

    chunk = _code_assist_response(
        {
            "candidates": [
                {"content": {"parts": [{"text": "hello"}]}, "finishReason": "STOP"}
            ],
            "usageMetadata": None,
        }
    )

    respx.post(_STREAM_URL).mock(
        return_value=httpx.Response(200, content=_sse_line(chunk))
    )

    chunks = []
    async for c in provider.stream(messages=[HumanMessage(content="hi")]):
        chunks.append(c)

    # Me should have one chunk with text but no tool calls
    assert len(chunks) == 1
    assert chunks[0].choices[0].delta.content == "hello"
    assert (
        chunks[0].choices[0].delta.tool_calls is None
        or len(chunks[0].choices[0].delta.tool_calls) == 0
    )


@pytest.mark.asyncio
@respx.mock
async def test_stream_tool_idx_resets_per_stream_call():
    """tool_idx_by_id is scoped to a single stream() call and resets on new stream."""
    provider = _make_provider()

    chunk_a = _code_assist_response(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "id": "fc-A",
                                    "name": "read",
                                    "args": {},
                                }
                            }
                        ]
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": None,
        }
    )

    chunk_b = _code_assist_response(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "id": "fc-B",
                                    "name": "write",
                                    "args": {},
                                }
                            }
                        ]
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": None,
        }
    )

    # Me first stream: fc-A gets index 0
    respx.post(_STREAM_URL).mock(
        return_value=httpx.Response(200, content=_sse_line(chunk_a))
    )
    chunks1 = []
    async for c in provider.stream(messages=[HumanMessage(content="hi")]):
        chunks1.append(c)
    assert chunks1[0].choices[0].delta.tool_calls[0].index == 0

    # Me second stream: reset tool_idx_by_id, so fc-B also gets index 0
    respx.post(_STREAM_URL).mock(
        return_value=httpx.Response(200, content=_sse_line(chunk_b))
    )
    chunks2 = []
    async for c in provider.stream(messages=[HumanMessage(content="hi")]):
        chunks2.append(c)
    assert chunks2[0].choices[0].delta.tool_calls[0].index == 0


@pytest.mark.asyncio
@respx.mock
async def test_stream_skips_empty_candidates():
    provider = _make_provider()

    chunk_no_candidates = _code_assist_response(
        {"candidates": [], "usageMetadata": None}
    )
    chunk_with_content = _code_assist_response(
        {
            "candidates": [
                {"content": {"parts": [{"text": "Hi"}]}, "finishReason": "STOP"}
            ],
            "usageMetadata": {
                "promptTokenCount": 1,
                "candidatesTokenCount": 1,
                "totalTokenCount": 2,
            },
        }
    )
    stream_content = _sse_line(chunk_no_candidates) + _sse_line(chunk_with_content)

    respx.post(_STREAM_URL).mock(
        return_value=httpx.Response(200, content=stream_content)
    )

    chunks = []
    async for chunk in provider.stream(messages=[HumanMessage(content="hi")]):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0].choices[0].delta.content == "Hi"


@pytest.mark.asyncio
@respx.mock
async def test_stream_http_error_raises():
    provider = _make_provider()

    respx.post(_STREAM_URL).mock(
        return_value=httpx.Response(503, content=b"Service Unavailable")
    )

    with pytest.raises(httpx.HTTPStatusError):
        async for _ in provider.stream(messages=[HumanMessage(content="hi")]):
            pass


@pytest.mark.asyncio
@respx.mock
async def test_stream_model_name_in_chunk():
    provider = _make_provider()

    data = _code_assist_response(
        {
            "candidates": [
                {"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}
            ],
            "usageMetadata": {
                "promptTokenCount": 1,
                "candidatesTokenCount": 1,
                "totalTokenCount": 2,
            },
        }
    )

    respx.post(_STREAM_URL).mock(
        return_value=httpx.Response(200, content=_sse_line(data))
    )

    chunks = []
    async for chunk in provider.stream(messages=[HumanMessage(content="hi")]):
        chunks.append(chunk)

    assert chunks[0].model == "gemini-2.5-flash"
    assert chunks[0].id == "geminicli-stream"
